from __future__ import annotations

from queue import Empty, Queue
from typing import Any, Dict, List, Optional

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from api_client import DeviceApiClient
from esp32_receiver import Esp32UdpReceiver
from info_manager import InfoManager


class TransmissionManager:
    """
    - 서버(FastAPI)와의 HTTP 통신 담당 (DeviceApiClient 래핑)
    - 향후 아두이노/ESP32/UDP 등의 전송 스레드를 함께 관리하는 허브 역할
    """

    def __init__(self, info_manager: InfoManager) -> None:
        self._info = info_manager
        self._api = DeviceApiClient()
        # LPR 입구 카메라: 연결 = UDP 7070 패킷 수신 여부 (패킷 있으면 연결, 없으면 10초 후 끊김)
        self._lpr_last_seen: float = 0.0
        self._lpr_connected: bool = False
        self._lpr_command_queue: list[str] = []
        self._lpr_frame_queue: Queue = Queue(maxsize=5)
        self._lpr_last_frame_ts: float = 0.0
        self._lpr_udp_receiver: Optional[Esp32UdpReceiver] = None

        # LPR 용 REST 서버 (등록/config/command) — 연결 상태는 UDP 기준으로만 갱신
        self._start_lpr_rest_server()
        self._start_lpr_monitor()
        # LPR UDP 7070 수신 시작 → 패킷 들어오면 _mark_lpr_seen(), 프레임은 _lpr_frame_queue 에 적재
        self._lpr_udp_receiver = Esp32UdpReceiver(on_frame=self._on_lpr_udp_frame)
        self._lpr_udp_receiver.start()

    # ───────── 서버와의 통신 ─────────
    def refresh_from_server(self) -> None:
        """
        서버 /health, /devices 를 조회해서 InfoManager 에 반영.
        예외는 상위(UI)에서 처리할 수 있도록 그대로 올린다.
        """
        health: Dict[str, Any] = self._api.health()
        devices: List[Dict[str, Any]] = self._api.list_devices()
        self._info.update_from_server(health=health, devices=devices)

    # ───────── 디바이스 연결 상태 업데이트 ─────────
    def set_gate_connected(self, connected: bool) -> None:
        """
        gate_controller 타입 장비의 is_connected 플래그를 서버/DB 에 반영하고,
        InfoManager 상태도 갱신한다.
        """
        devices: List[Dict[str, Any]] = self._api.list_devices()
        changed = False
        for d in devices:
            if (d.get("type") or "").lower() == "gate_controller":
                if bool(d.get("is_connected")) != connected:
                    self._api.update_device_is_connected(d, connected)
                    d["is_connected"] = connected
                    changed = True
        if changed:
            # 변경된 devices 리스트를 바로 InfoManager 에 반영
            self._info.update_from_server(
                health=self._info.server_health,
                devices=devices,
            )

    def set_gate_connected_by_ip(self, ip: str, connected: bool) -> None:
        """
        gate_controller 타입 중 특정 IP 에 해당하는 장비만 is_connected 업데이트.
        """
        devices: List[Dict[str, Any]] = self._api.list_devices()
        changed = False
        for d in devices:
            if (d.get("type") or "").lower() == "gate_controller" and (d.get("ip_address") or "") == ip:
                if bool(d.get("is_connected")) != connected:
                    self._api.update_device_is_connected(d, connected)
                    d["is_connected"] = connected
                    changed = True
        if changed:
            self._info.update_from_server(
                health=self._info.server_health,
                devices=devices,
            )

    def set_street_parking_connected(self, connected: bool) -> None:
        """
        street_parking_controller 타입(esp32_board2) 장비의 is_connected 플래그를
        서버/DB 에 반영하고 InfoManager 상태도 갱신한다.
        """
        devices: List[Dict[str, Any]] = self._api.list_devices()
        changed = False
        for d in devices:
            if (d.get("type") or "").lower() == "street_parking_controller":
                if bool(d.get("is_connected")) != connected:
                    self._api.update_device_is_connected(d, connected)
                    d["is_connected"] = connected
                    changed = True
        if changed:
            self._info.update_from_server(
                health=self._info.server_health,
                devices=devices,
            )

    def set_street_parking_connected_by_ip(self, ip: str, connected: bool) -> None:
        """
        street_parking_controller 타입(esp32_board2) 중 특정 IP 장비만 업데이트.
        """
        devices: List[Dict[str, Any]] = self._api.list_devices()
        changed = False
        for d in devices:
            if (d.get("type") or "").lower() == "street_parking_controller" and (d.get("ip_address") or "") == ip:
                if bool(d.get("is_connected")) != connected:
                    self._api.update_device_is_connected(d, connected)
                    d["is_connected"] = connected
                    changed = True
        if changed:
            self._info.update_from_server(
                health=self._info.server_health,
                devices=devices,
            )

    # ───────── device_guid 기반 IP 업데이트 (등록 패킷 처리용) ─────────
    def update_device_ip_by_guid(
        self,
        device_guid: str,
        ip: str,
        device_name: str | None = None,
    ) -> None:
        """
        esp32_board1_1 / esp32_board2 / esp32_lpr_enter 에서
        TYPE_DEV_REGISTER 패킷 또는 REST 등록으로 device_guid 와 현재 IP 를 보내오면,
        해당 guid 를 가진 devices 행의 ip_address 를 최신 값으로 갱신한다.
        """
        if not device_guid and not device_name:
            print("[LPR-IP] skip: guid/name 모두 없음")
            return

        # 먼저 서버의 devices 목록에서 guid/name 이 모두 일치하는 장비가 있는지 확인한다.
        devices: List[Dict[str, Any]] = self._api.list_devices()
        target: Dict[str, Any] | None = None

        for d in devices:
            guid_in_db = (d.get("device_guid") or "").strip()
            name_in_db = (d.get("name") or "").strip()
            if device_guid and device_name:
                # guid 와 name 이 모두 일치해야만 유효한 등록으로 인정
                if guid_in_db == device_guid.strip() and name_in_db == (device_name or "").strip():
                    target = d
                    break
            elif device_guid:
                if guid_in_db == device_guid.strip():
                    target = d
                    break
            elif device_name:
                if name_in_db == (device_name or "").strip():
                    target = d
                    break

        if target is None:
            # 등록 정보와 매칭되는 devices 레코드가 없으면 IP 갱신을 하지 않는다.
            print(f"[LPR-IP] not found in devices: guid={device_guid!r}, name={device_name!r}")
            return

        # 1순위: device_guid 로 서버 전용 엔드포인트 호출
        before_ip = target.get("ip_address")
        print(f"[LPR-IP] updating: guid={device_guid!r}, name={device_name!r}, {before_ip} -> {ip}")
        if device_guid:
            self._api.update_device_ip_by_guid(device_guid, ip)
        else:
            # guid 가 비어 있고 device_name 만 있는 경우에는 기존 방식으로 fallback
            if (target.get("ip_address") or "") != ip:
                target["ip_address"] = ip
                self._api.update_device(target)

        # 갱신 후 최신 devices 목록을 다시 받아 InfoManager 에 반영
        devices_after: List[Dict[str, Any]] = self._api.list_devices()
        self._info.update_from_server(
            health=self._info.server_health,
            devices=devices_after,
        )

    # ───────── 주차면 점유 상태 업데이트 (parking_slots 동기화) ─────────
    def set_slot_occupied(
        self,
        slot_name: str,
        occupied: bool,
        plate: str | None = None,
    ) -> None:
        """
        parking_slots 테이블의 특정 슬롯(S1~S4, T1~T6 등)에 대해
        is_occupied / sensor_connected 상태를 업데이트한다.

        - esp32_board2 의 SPOT_1~4 이벤트를 DeviceManager 가 받아서 호출.
        - 2.client 는 /parking/dashboard 를 통해 이 정보를 읽어와
          주차 대수/빈자리/색상(UI)을 자동으로 갱신한다.
        """
        self._api.set_slot_occupied(slot_name, occupied, plate)

    # ───────── LPR 입구 카메라용 REST 서버/keep-alive ─────────
    def _start_lpr_rest_server(self) -> None:
        """esp32_lpr_enter 가 접속하는 소형 REST 서버를 백그라운드로 기동."""

        manager = self

        class LprHandler(BaseHTTPRequestHandler):
            def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self) -> None:  # noqa: N802
                if self.path == "/api/device/register":
                    length = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
                    try:
                        data = json.loads(raw)
                    except Exception:  # noqa: BLE001
                        data = {}
                    guid = str(data.get("guid") or "DEV-LPR-1")
                    name = str(data.get("name") or "입구 LPR 카메라")
                    ip = str(data.get("ip") or self.client_address[0])
                    manager._handle_lpr_register(guid, name, ip)
                    self._send_json(200, {"status": "ok"})
                else:
                    self.send_error(404)

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                path = parsed.path

                if path == "/api/device/config":
                    # 단순 설정 반환: 서버(host), REST 포트, UDP 포트 (연결 상태는 UDP 패킷 기준으로만 갱신)
                    from config import settings as _settings  # 로컬 import

                    host_header = self.headers.get("Host", "")
                    host_ip = host_header.split(":")[0] if host_header else ""
                    if not host_ip or host_ip in ("0.0.0.0", "127.0.0.1", "localhost"):
                        host_ip = self.client_address[0]

                    payload = {
                        "server_host": host_ip,
                        "rest_port": _settings.lpr_enter_rest_port,
                        "udp_port": _settings.lpr_enter_udp_port,
                    }
                    self._send_json(200, payload)
                    return

                if path == "/api/device/command":
                    qs = parse_qs(parsed.query or "")
                    guid = (qs.get("guid") or [""])[0]
                    # guid 를 기반으로 현재 클라이언트 IP 를 devices.ip_address 에 반영
                    if guid:
                        try:
                            manager.update_device_ip_by_guid(guid, self.client_address[0])
                        except Exception:
                            # IP 갱신 실패는 치명적이지 않으므로 무시
                            pass

                    cmd = manager._pop_lpr_command(guid)
                    # 디버그용 로그: 어떤 guid 에 어떤 명령이 내려갔는지 확인
                    print(f"[LPR-CMD] guid={guid!r}, ip={self.client_address[0]}, cmd={cmd!r}")
                    if cmd:
                        self._send_json(200, {"command": cmd})
                    else:
                        self._send_json(200, {"command": "none"})
                    return

                if path == "/api/devices":
                    try:
                        devices = manager._api.list_devices()
                    except Exception:  # noqa: BLE001
                        devices = []
                    self._send_json(200, {"devices": devices})
                    return

                self.send_error(404)

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                # 콘솔 로그는 너무 시끄러우니 무시
                return

        from config import settings

        server = HTTPServer(("0.0.0.0", settings.lpr_enter_rest_port), LprHandler)

        def _serve() -> None:
            server.serve_forever()

        thread = threading.Thread(target=_serve, daemon=True)
        thread.start()

    def _start_lpr_monitor(self) -> None:
        """LPR 카메라 연결 모니터: UDP 7070 패킷이 10초 동안 없으면 끊김으로 간주."""

        def _loop() -> None:
            while True:
                time.sleep(2.0)
                now = time.time()
                if self._lpr_connected and (now - self._lpr_last_seen > 10.0):
                    self._set_lpr_connected(False)

        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    def _on_lpr_udp_frame(self, fno: int, img: Any) -> None:
        """UDP 7070 으로 프레임 수신 시 호출. 연결 상태 갱신 + 테스트 다이얼로그용 큐에 적재."""
        self._mark_lpr_seen()
        self._lpr_last_frame_ts = time.time()
        try:
            if self._lpr_frame_queue.full():
                self._lpr_frame_queue.get_nowait()
            self._lpr_frame_queue.put((fno, img))
        except Exception:
            pass

    def get_lpr_frame(self) -> Optional[tuple[int, Any]]:
        """테스트 다이얼로그에서 호출: 수신된 LPR 프레임 1개 반환 (없으면 None)."""
        try:
            return self._lpr_frame_queue.get_nowait()
        except Empty:
            return None

    def has_recent_lpr_frame(self, timeout_sec: float = 5.0) -> bool:
        """최근 timeout_sec 초 이내에 LPR UDP 프레임을 받았는지."""
        if self._lpr_last_frame_ts <= 0:
            return False
        return (time.time() - self._lpr_last_frame_ts) <= timeout_sec

    def _mark_lpr_seen(self) -> None:
        self._lpr_last_seen = time.time()
        if not self._lpr_connected:
            self._set_lpr_connected(True)

    def _handle_lpr_register(self, device_guid: str, device_name: str, ip: str) -> None:
        """esp32_lpr_enter 가 POST /api/device/register 를 호출했을 때 처리."""
        print(f"[LPR-REST] /api/device/register guid={device_guid!r}, name={device_name!r}, ip={ip}")
        try:
            self.update_device_ip_by_guid(device_guid, ip, device_name=device_name)
        except Exception:
            # IP 갱신 실패는 치명적이지 않으므로 무시
            pass
        # 연결 상태는 UDP 7070 패킷 수신으로만 갱신 (여기서는 _mark_lpr_seen 호출 안 함)

    def _set_lpr_connected(self, connected: bool) -> None:
        """lpr_camera_server 타입 장비의 is_connected 플래그를 갱신."""
        if self._lpr_connected == connected:
            return
        self._lpr_connected = connected

        devices: List[Dict[str, Any]] = self._api.list_devices()
        changed = False
        for d in devices:
            typ = (d.get("type") or "").lower()
            # DB/init_manual.sql 기준 type 은 'lpr_camera' 로 저장되어 있음.
            if typ in ("lpr_camera", "lpr_camera_server"):
                if bool(d.get("is_connected")) != connected:
                    self._api.update_device_is_connected(d, connected)
                    d["is_connected"] = connected
                    changed = True
        if changed:
            self._info.update_from_server(
                health=self._info.server_health,
                devices=devices,
            )

    def enqueue_lpr_enter_command(self, command: str) -> None:
        """테스트 UI 에서 호출: 다음 /api/device/command 폴링 때 전달할 명령을 큐에 적재."""
        self._lpr_command_queue.append(command)

    def _pop_lpr_command(self, guid: str) -> str | None:
        if not self._lpr_command_queue:
            return None
        # guid 를 사용해 향후 여러 LPR 카메라 구분 가능하도록 확장 여지를 남긴다.
        return self._lpr_command_queue.pop(0)

    # ───────── 종료 처리 ─────────
    def close(self) -> None:
        if self._lpr_udp_receiver:
            self._lpr_udp_receiver.stop()
            self._lpr_udp_receiver = None
        self._api.close()


