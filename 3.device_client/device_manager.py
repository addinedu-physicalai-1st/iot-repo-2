from __future__ import annotations

from info_manager import InfoManager
from transmission_manager import TransmissionManager
from esp32_gate_server import Esp32GateServer


class DeviceManager:
    """
    ESP32 / ESP32-CAM / 기타 장치를 관리하는 매니저의 뼈대.

    - 현재는 InfoManager / TransmissionManager 와의 연결만 잡아두고,
      실제 장치 제어 로직은 이후 단계에서 채워 넣는다.
    """

    def __init__(
        self,
        info_manager: InfoManager,
        transmission_manager: TransmissionManager,
    ) -> None:
        self._info = info_manager
        self._tx = transmission_manager
        self._gate_server: Esp32GateServer | None = None
        self._gate_logs: list[str] = []
        self._gate_devices: list[dict] = []
        self._gate_connected: bool = False

    def start(self) -> None:
        """
        - ESP32 보드1(입구 차단기) TCP 서버 스레드 시작
        - 향후 ESP32-CAM/시리얼 장치 스레드도 여기서 시작 예정
        """
        if self._gate_server is None:
            self._gate_server = Esp32GateServer(
                host="0.0.0.0",
                port=8080,
                on_log=self._append_gate_log,
                on_device_list=self._set_gate_devices,
                on_state_change=self._on_gate_state_change,
            )
            self._gate_server.start()

        # 앱 기동 직후에는 DB 에 남아있던 이전 연결 상태를 신뢰하지 않고,
        # gate_controller / street_parking_controller 를 모두 끊김으로 초기화한다.
        # 이후 실제 소켓 연결/keep-alive 기준으로만 is_connected 를 다시 세팅.
        try:
            self._tx.set_gate_connected(False)
            self._tx.set_street_parking_connected(False)
        except Exception:
            # 초기화 실패는 치명적이지 않으므로 로그만 남기고 무시
            self._append_gate_log("[GATE] 초기 연결 상태 리셋 실패 (DB)")

    def stop(self) -> None:
        """start 에서 시작한 장치 관련 스레드를 종료."""
        if self._gate_server is not None:
            self._gate_server.stop()
            self._gate_server = None

    # ───────── ESP32 게이트 관련 헬퍼 (UI에서 사용) ─────────
    def _append_gate_log(self, msg: str) -> None:
        self._gate_logs.append(msg)
        # 로그 길이 무한 증가 방지
        if len(self._gate_logs) > 500:
            self._gate_logs = self._gate_logs[-200:]

    def _set_gate_devices(self, devices: list[dict]) -> None:
        self._gate_devices = devices

    def _on_gate_state_change(self, connected: bool) -> None:
        # 중복 호출 방지
        if self._gate_connected == connected:
            return
        self._gate_connected = connected
        # 서버(FastAPI)에 gate_controller / street_parking_controller 장비 연결 상태 반영
        try:
            ip = None
            if self._gate_server is not None:
                # 최근 연결된 ESP32 보드의 IP
                ip = getattr(self._gate_server, "_current_ip", None)

            if ip:
                # 특정 IP 와 매칭되는 장비만 연결 상태 반영
                self._tx.set_gate_connected_by_ip(ip, connected)
                self._tx.set_street_parking_connected_by_ip(ip, connected)
            else:
                # IP 정보를 얻지 못한 경우, 타입 전체에 대해 fallback 처리
                self._tx.set_gate_connected(connected)
                self._tx.set_street_parking_connected(connected)
        except Exception:
            # 서버 반영 실패 시에도 로컬 로그는 남긴다.
            state = "연결" if connected else "해제"
            self._append_gate_log(f"[GATE] 서버 반영 실패 (상태={state})")

    def get_gate_logs(self) -> list[str]:
        return list(self._gate_logs)

    def get_gate_devices(self) -> list[dict]:
        return list(self._gate_devices)

    def open_gate(self) -> None:
        if self._gate_server:
            self._gate_server.send_open_gate()

    def close_gate(self) -> None:
        if self._gate_server:
            self._gate_server.send_close_gate()

    def write_siteid(self, site_id: str) -> None:
        if self._gate_server:
            self._gate_server.send_write_siteid(site_id)


