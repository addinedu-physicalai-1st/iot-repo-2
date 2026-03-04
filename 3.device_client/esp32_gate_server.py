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
TYPE_DEV_REGISTER = 6  # 장비 등록 패킷 (device_guid, device_name)

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
    ) -> None:
        super().__init__(daemon=True)
        self._host = host
        self._port = port
        self._on_log = on_log or (lambda msg: None)
        self._on_device_list = on_device_list or (lambda lst: None)
        self._on_state_change = on_state_change or (lambda connected: None)
        # device_guid, device_name, ip 를 전달하는 콜백
        self._on_register = on_register or (lambda guid, name, ip: None)

        self._device_list_buf: Dict[int, Dict[str, str]] = {}
        self._client: Optional[socket.socket] = None
        self._stop_flag = threading.Event()
        self._current_ip: Optional[str] = None

    # ───────── 외부 호출용 API (명령 전송) ─────────
    def send_open_gate(self) -> None:
        if not self._client:
            return
        try:
            self._client.sendall(struct.pack(STRUCT_FORMAT, TYPE_CMD_OPEN, b"\x00" * 32))
            self._on_log("[CMD] 게이트 열기 전송")
        except OSError:
            self._on_log("[CMD] 게이트 열기 전송 실패 (소켓 에러)")

    def send_close_gate(self) -> None:
        if not self._client:
            return
        try:
            self._client.sendall(struct.pack(STRUCT_FORMAT, TYPE_CMD_CLOSE, b"\x00" * 32))
            self._on_log("[CMD] 게이트 닫기 전송")
        except OSError:
            self._on_log("[CMD] 게이트 닫기 전송 실패 (소켓 에러)")

    def send_write_siteid(self, site_id: str) -> None:
        if not self._client:
            return
        # 첫 바이트는 예비(0), 이후 16바이트 SiteID, 나머지 패딩
        payload = b"\x00" + site_id.encode().ljust(16, b"\x00")[:16] + b"\x00" * 15
        try:
            self._client.sendall(struct.pack(STRUCT_FORMAT, TYPE_CMD_WRITE, payload))
            self._on_log(f"[CMD] 카드 SiteID 쓰기 명령 전송 (SiteID={site_id})")
        except OSError:
            self._on_log("[CMD] 카드 SiteID 쓰기 전송 실패 (소켓 에러)")

    # ───────── 스레드 메인 루프 ─────────
    def run(self) -> None:  # type: ignore[override]
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self._host, self._port))
        server.listen(5)
        self._on_log(f"[GATE] ESP32 게이트 서버 리슨 시작 ({self._host}:{self._port})")

        try:
            while not self._stop_flag.is_set():
                try:
                    server.settimeout(1.0)
                    conn, addr = server.accept()
                except socket.timeout:
                    continue

                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self._client = conn
                self._current_ip = addr[0]
                self._on_log(f"[GATE] ESP32 보드 연결됨 ({addr[0]}:{addr[1]})")
                self._on_state_change(True)
                self._handle_client(conn, addr)
                self._client = None
                self._current_ip = None
        finally:
            try:
                server.close()
            except Exception:
                pass

    def stop(self) -> None:
        self._stop_flag.set()
        try:
            if self._client:
                self._client.close()
        except Exception:
            pass

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

                    if ev == 99:
                        line = f"[ERROR] {src} 초기화 실패 ({ext})"
                    else:
                        name = EV_NAMES.get(ev, f"EV_{ev}")
                        line = f"[EVENT] {name} | {src}" + (f" | {ext}" if ext else "")
                    self._on_log(line)
                    continue

                # 3. RFID
                if typ == TYPE_RFID:
                    mode = payload[0]
                    uid = payload[1:17].decode("utf-8", errors="ignore").strip("\x00 ")
                    siteid = payload[17:32].decode("utf-8", errors="ignore").strip("\x00 ")
                    self._on_log(f"[RFID] mode={mode} UID={uid} SiteID={siteid}")
                    continue

                # 4. 장비 목록
                if typ == TYPE_DEVICE_LIST:
                    idx = payload[0]
                    total = payload[1]
                    guid = payload[2:18].decode("utf-8", errors="ignore").strip("\x00 ")
                    name = payload[18:32].decode("utf-8", errors="ignore").strip("\x00 ")
                    self._device_list_buf[idx] = {"guid": guid, "name": name}
                    if len(self._device_list_buf) >= total:
                        lst = [self._device_list_buf[i] for i in range(total)]
                        self._device_list_buf.clear()
                        self._on_device_list(lst)
                    continue

                # 5. 장비 등록 패킷 (device_guid, device_name, ip)
                if typ == TYPE_DEV_REGISTER:
                    guid = payload[0:16].decode("utf-8", errors="ignore").strip("\x00 ")
                    name = payload[16:32].decode("utf-8", errors="ignore").strip("\x00 ")
                    ip = addr[0]
                    self._on_log(
                        f"[REG] device_register 수신 guid={guid} name={name} ip={ip}"
                    )
                    self._on_register(guid, name, ip)
                    continue
        finally:
            try:
                conn.close()
            except Exception:
                pass
            self._device_list_buf.clear()
            # 연결 종료 시점의 IP를 사용해 상태 변경 알림
            self._on_log(f"[GATE] ESP32 보드 연결 종료 ({addr[0]}:{addr[1]})")
            self._on_state_change(False)

