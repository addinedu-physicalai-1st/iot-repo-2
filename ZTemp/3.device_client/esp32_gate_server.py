from __future__ import annotations

"""
ESP32 보드1(입구 차단기)와 TCP 소켓으로 통신하는 백엔드 서버 스레드.

- ESP32 스케치: 4.arduino/esp32_board1/esp32_board1_1.ino
- 포트: 8080 (ESP32 → device_client PC 192.168.0.149:8080 접속)

기능:
- PING/PONG(keepalive)
- IR/시스템 이벤트 수신
- RFID UID/SiteID 수신
- 장비 목록(TYPE_DEVICE_LIST) 수신
- 게이트 열기/닫기/카드 SiteID 쓰기 명령 전송

UI 와의 연결은 콜백(on_log, on_device_list) 으로만 처리한다.
"""

import socket
import struct
import threading
import time
from typing import Any, Callable, Dict, List, Optional

STRUCT_FORMAT = "<B 32s"  # type(1) + payload(32)
SIZE = struct.calcsize(STRUCT_FORMAT)

TYPE_PING = 0xFE
TYPE_PONG = 0xFD
TYPE_IR_EVENT = 0
TYPE_RFID = 1
TYPE_CMD_OPEN = 2
TYPE_CMD_CLOSE = 5
TYPE_CMD_WRITE = 3
TYPE_DEVICE_LIST = 4
TYPE_DEV_REGISTER = 6
TYPE_CMD_DISPLAY = 7  # New type for sending text to LCD

EV_NAMES = {
    1: "ENTRY_DETECTED",
    2: "EXIT_DETECTED",
    3: "RFID",
    4: "GATE_OPEN",
    5: "GATE_CLOSED",
    99: "H/W SENSOR ERROR",
}

KEEPALIVE_TIMEOUT_SEC = 12
RECV_CHECK_INTERVAL_SEC = 2


class Esp32GateServer(threading.Thread):
    """
    ESP32 입구 차단기 보드와 통신하는 소켓 서버 스레드.

    - device_client PC 에서 0.0.0.0:8080 을 리슨하고,
      ESP32 가 클라이언트로 접속하는 구조.
    - 수신 이벤트는 on_log / on_device_list 콜백으로 전달한다.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        on_log: Optional[Callable[[str], None]] = None,
        on_device_list: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
        on_state_change: Optional[Callable[[bool], None]] = None,
        on_register: Optional[Callable[[str, str, str], None]] = None,
        on_parking_event: Optional[Callable[[str, bool], None]] = None,
        on_event: Optional[Callable[[int, str, str], None]] = None,
    ) -> None:
        super().__init__(daemon=True)
        self._host = host
        self._port = port
        self._on_log = on_log or (lambda msg, ip=None: None)
        self._on_device_list = on_device_list or (lambda lst, ip=None: None)
        self._on_state_change = on_state_change or (lambda connected, ip=None: None)
        self._on_register = on_register or (lambda guid, name, ip=None: None)
        self._on_parking_event = on_parking_event or (lambda spot, occ, ip=None: None)
        self._on_event = on_event or (lambda ev, src, ext, ip=None: None)
        
        # 추가: 다중 리스너 지원
        self._listeners: List[Dict[str, Any]] = []
        print(f"[DEBUG] Esp32GateServer initialized with _on_event: {self._on_event}")

        self._device_list_bufs: Dict[str, Dict[int, Dict[str, str]]] = {} # IP -> buffer
        self._clients: Dict[str, socket.socket] = {} # IP -> socket
        self._client_types: Dict[str, str] = {}    # IP -> board_id
        self._stop_flag = threading.Event()

    def add_listener(self, listener: Dict[str, Any]) -> None:
        """
        리스너 등록. listener 는 다음 콜백 중 일부를 가질 수 있음:
        on_log(msg, ip), on_device_list(lst, ip), on_state_change(conn, ip),
        on_register(guid, name, ip), on_parking_event(spot, occ, ip), on_event(ev, src, ext, ip)
        """
        self._listeners.append(listener)

    def remove_listener(self, listener: Dict[str, Any]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _notify_listeners(self, callback_name: str, *args, **kwargs) -> None:
        # 기존 단일 콜백 실행
        cb = getattr(self, f"_{callback_name}", None)
        if cb:
            try: cb(*args, **kwargs)
            except: pass
            
        # 다중 리스너 실행
        for l in self._listeners:
            f = l.get(callback_name)
            if f:
                try: f(*args, **kwargs)
                except: pass

    def _log(self, msg: str, ip: str | None = None) -> None:
        self._notify_listeners("on_log", msg, ip=ip)

    # ───────── 외부 호출용 API (명령 전송) ─────────
    def send_open_gate(self, target_guid: str | None = None) -> None:
        """게이트 열기 명령 전송."""
        payload = b"\x00" * 32
        if target_guid:
            self._send_targeted(target_guid, TYPE_CMD_OPEN, payload)
        else:
            self._broadcast(TYPE_CMD_OPEN, payload)
        self._on_log("[CMD] 게이트 열기 명령 전송")

    def send_close_gate(self, target_guid: str | None = None) -> None:
        """게이트 닫기 명령 전송."""
        payload = b"\x00" * 32
        if target_guid:
            self._send_targeted(target_guid, TYPE_CMD_CLOSE, payload)
        else:
            self._broadcast(TYPE_CMD_CLOSE, payload)
        self._on_log("[CMD] 게이트 닫기 명령 전송")

    def send_write_siteid(self, site_id: str, target_guid: str | None = None) -> None:
        payload = b"\x00" + site_id.encode().ljust(16, b"\x00")[:16] + b"\x00" * 15
        if target_guid:
            self._send_targeted(target_guid, TYPE_CMD_WRITE, payload)
        else:
            self._broadcast(TYPE_CMD_WRITE, payload)

    def _send_targeted(self, guid: str, typ: int, payload: bytes) -> None:
        target_ip = next((ip for ip, g in self._client_types.items() if g == guid), None)
        if target_ip and target_ip in self._clients:
            try:
                self._clients[target_ip].sendall(struct.pack(STRUCT_FORMAT, typ, payload))
            except OSError:
                pass
        else:
            # 타겟 없으면 전체 브로드캐스트
            self._broadcast(typ, payload)

    def send_lcd_text(self, line1: str, line2: str = "", target_guid: str | None = None) -> None:
        """ESP32 보드로 텍스트 전달."""
        payload = line1.encode().ljust(16, b"\x00")[:16] + line2.encode().ljust(16, b"\x00")[:16]
        
        target_ip = None
        if target_guid:
            # GUID 로 IP 찾기
            target_ip = next((ip for ip, g in self._client_types.items() if g == target_guid), None)
        
        if not target_ip:
            # Fallback: 보드 종류(EXIT)로 찾기
            target_ip = next((ip for ip, dev_id in self._client_types.items() if "EXIT" in dev_id or "DEV-GATE-2" in dev_id), None)

        if target_ip and target_ip in self._clients:
            try:
                self._clients[target_ip].sendall(struct.pack(STRUCT_FORMAT, TYPE_CMD_DISPLAY, payload))
            except OSError:
                pass
        else:
            # 타겟을 못 찾으면 전체 브로드캐스트
            self._broadcast(TYPE_CMD_DISPLAY, payload)

    def _broadcast(self, typ: int, payload: bytes) -> None:
        packet = struct.pack(STRUCT_FORMAT, typ, payload)
        for ip, conn in list(self._clients.items()):
            try:
                conn.sendall(packet)
            except OSError:
                self._remove_client(ip)

    # ───────── 스레드 메인 루프 ─────────
    def run(self) -> None:  # type: ignore[override]
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            print(f"[DEBUG] Attempting to bind TCP 8080 on {self._host}")
            server.bind((self._host, self._port))
            server.listen(5)
            self._on_log(f"[GATE] ESP32 게이트 서버 리슨 시작 ({self._host}:{self._port})")
            print(f"[DEBUG] TCP Server listening on {self._port} successfully")
        except Exception as e:
            print(f"[ERROR] TCP Server bind failed: {e}")
            self._on_log(f"[ERROR] TCP 서버 시작 실패: {e}")
            return

        try:
            while not self._stop_flag.is_set():
                try:
                    server.settimeout(1.0)
                    conn, addr = server.accept()
                except socket.timeout:
                    continue

                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                ip = addr[0]
                self._clients[ip] = conn
                self._log(f"[GATE] ESP32 보드 연결됨 ({addr[0]}:{addr[1]})", ip=ip)
                self._notify_listeners("on_state_change", True, ip=ip)
                
                # 핸들러를 별도 스레드로 분리 (여러 클라이언트 대응)
                threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()
        finally:
            try:
                server.close()
            except Exception:
                pass

    def _remove_client(self, ip: str) -> None:
        if ip in self._clients:
            try:
                self._clients[ip].close()
            except:
                pass
            del self._clients[ip]
            if ip in self._client_types:
                del self._client_types[ip]
            if ip in self._device_list_bufs:
                del self._device_list_bufs[ip]
        if not self._clients:
            self._notify_listeners("on_state_change", False, ip=ip)

    def stop(self) -> None:
        self._stop_flag.set()
        for ip, conn in list(self._clients.items()):
            try:
                conn.close()
            except:
                pass
        self._clients.clear()
        self._client_types.clear()

    # ───────── 내부 처리 ─────────
    def _handle_client(self, conn: socket.socket, addr: Any) -> None:
        conn.settimeout(RECV_CHECK_INTERVAL_SEC)
        last_activity = time.monotonic()

        try:
            while not self._stop_flag.is_set():
                try:
                    data = conn.recv(SIZE)
                except socket.timeout:
                    if time.monotonic() - last_activity > KEEPALIVE_TIMEOUT_SEC:
                        self._on_log("[GATE] keepalive 타임아웃, 연결 종료")
                        break
                    continue
                except OSError:
                    break

                if not data:
                    break

                last_activity = time.monotonic()
                typ = data[0]
                payload = data[1:33]

                # 1. PING → PONG
                if typ == TYPE_PING:
                    try:
                        conn.sendall(struct.pack(STRUCT_FORMAT, TYPE_PONG, b"\x00" * 32))
                    except OSError:
                        break
                    continue

                # 2. IR / 시스템 이벤트
                if typ == TYPE_IR_EVENT:
                    ev = payload[0]
                    src = payload[1:17].decode("utf-8", errors="ignore").strip("\x00 ")
                    ext = payload[17:32].decode("utf-8", errors="ignore").strip("\x00 ")
                    self._on_log(f"[EVENT] ev={ev} ({EV_NAMES.get(ev, 'UNKNOWN')}) src={src} ext={ext}")
                    
                    # LCD 보드로 이벤트 텍스트 전달 (Board 2 -> Board 1 LCD)
                    if ev == 1: # ENTRY
                        self.send_lcd_text("CAR DETECTED", "AT ENTRY")
                    elif ev == 2: # EXIT
                        # EXIT는 이미 본인 보드에서 출력하므로 굳이 안 보내도 되지만 동기화 차원에서 보낼 수 있음
                        pass
                    elif ev == 4: # GATE_OPEN
                        self.send_lcd_text("GATE OPENED", src)
                    elif ev == 5: # GATE_CLOSED
                        self.send_lcd_text("GATE CLOSED", src)
                    
                    self._on_event(ev, src, ext)

                    # 노상 주차면 센서 이벤트인 경우(SPOT_1~4, OCCUPIED/EMPTY),
                    # 상위(DeviceManager)로 콜백을 주어 parking_slots 와 동기화한다.
                    if src.startswith("SPOT_") and ext in ("OCCUPIED", "EMPTY"):
                        is_occupied = ext == "OCCUPIED"
                        self._on_parking_event(src, is_occupied)
                    continue

                # 3. RFID
                if typ == TYPE_RFID:
                    mode = payload[0]
                    uid = payload[1:17].decode("utf-8", errors="ignore").strip("\x00 ")
                    siteid = payload[17:32].decode("utf-8", errors="ignore").strip("\x00 ")
                    self._on_log(f"[RFID] mode={mode} UID={uid} SiteID={siteid}")
                    # LCD 보드로 즉시 전송
                    self.send_lcd_text("RFID READ", uid)
                    continue

                # 4. 장비 목록
                if typ == TYPE_DEVICE_LIST:
                    idx = payload[0]
                    total = payload[1]
                    guid = payload[2:18].decode("utf-8", errors="ignore").strip("\x00 ")
                    name = payload[18:32].decode("utf-8", errors="ignore").strip("\x00 ")
                    
                    ip = addr[0]
                    if ip not in self._device_list_bufs:
                        self._device_list_bufs[ip] = {}
                    buf = self._device_list_bufs[ip]
                    
                    buf[idx] = {"guid": guid, "name": name}
                    if len(buf) >= total:
                        lst = [buf[i] for i in range(total)]
                        buf.clear()
                        self._notify_listeners("on_device_list", lst, ip=ip)
                    continue

                # 5. 장비 등록 패킷 (device_guid, device_name, ip)
                if typ == TYPE_DEV_REGISTER:
                    guid = payload[0:16].decode("utf-8", errors="ignore").strip("\x00 ")
                    name = payload[16:32].decode("utf-8", errors="ignore").strip("\x00 ")
                    ip = addr[0]
                    self._client_types[ip] = guid 
                    self._log(
                        f"[REG] device_register 수신 guid={guid} name={name} ip={ip}", ip=ip
                    )
                    self._notify_listeners("on_register", guid, name, ip=ip)
                    continue
        finally:
            self._remove_client(addr[0])
            self._log(f"[GATE] ESP32 보드 연결 종료 ({addr[0]}:{addr[1]})", ip=addr[0])

