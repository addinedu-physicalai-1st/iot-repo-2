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
        self._gate_connected_ips: set[str] = set()  # 연결된 보드 IP 목록
        # parking_slots, device 등록 정보 등을 위한 내부 상태
        self._parking_state: dict[str, bool] = {}

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
                on_register=self._on_device_register,
                on_parking_event=self._on_parking_event,
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
        try:
            self._tx.set_gate_connected(False)
            self._tx.set_street_parking_connected(False)
        except Exception:
            pass

    # ───────── ESP32 게이트 관련 헬퍼 (UI에서 사용) ─────────
    def _append_gate_log(self, msg: str) -> None:
        self._gate_logs.append(msg)
        # 로그 길이 무한 증가 방지
        if len(self._gate_logs) > 500:
            self._gate_logs = self._gate_logs[-200:]

    def _set_gate_devices(self, devices: list[dict]) -> None:
        self._gate_devices = devices

    def _on_gate_state_change(self, ip: str, connected: bool, guid: str | None = None) -> None:
        """ESP32 보드 연결/해제 시 GUID 기준으로 gate_controller 연결 상태 반영 (1/2 혼동 방지)."""
        if connected:
            self._gate_connected_ips.add(ip)
        else:
            self._gate_connected_ips.discard(ip)
        try:
            if guid:
                self._tx.set_gate_connected_by_guid(guid, connected)
            elif not connected:
                self._tx.set_gate_connected_by_ip(ip, False)
            self._tx.set_street_parking_connected_by_ip(ip, connected)
        except Exception:
            state = "연결" if connected else "해제"
            self._append_gate_log(f"[GATE] 서버 반영 실패 ip={ip} guid={guid} 상태={state}")

    # ───────── 장비 등록(DEVICE_GUID 기반 IP 갱신) ─────────
    def _on_device_register(self, device_guid: str, device_name: str, ip: str) -> None:
        """
        ESP32 보드에서 TYPE_DEV_REGISTER 패킷을 보냈을 때 호출된다.

        - device_guid / device_name / ip 를 받아서 TransmissionManager 에 전달
        - FastAPI → DB 의 devices.ip_address 를 갱신 (DHCP 대응)
        """
        self._append_gate_log(
            f"[REG] 등록 요청 수신 guid={device_guid} name={device_name} ip={ip}"
        )
        try:
            self._tx.update_device_ip_by_guid(device_guid, ip, device_name=device_name)
            self._tx.set_gate_connected_by_guid(device_guid, True)
            self._append_gate_log(
                f"[REG] DB ip_address 갱신 완료 guid={device_guid} → {ip}"
            )
        except Exception as exc:
            self._append_gate_log(
                f"[REG] DB ip_address 갱신 실패 guid={device_guid} ({exc})"
            )

    # ───────── 노상 주차면 이벤트 처리 (parking_slots 동기화) ─────────
    def _on_parking_event(self, spot_name: str, is_occupied: bool) -> None:
        """
        ESP32 보드2(노상 주차면 센서 컨트롤러)에서 SPOT_1~4 이벤트가 올 때 호출된다.

        - 내부 상태(self._parking_state)에 기록
        - TransmissionManager 를 통해 /parking/slots API 호출 → DB parking_slots 동기화
        """
        self._parking_state[spot_name] = is_occupied
        state_txt = "OCCUPIED" if is_occupied else "EMPTY"
        self._append_gate_log(f"[PARKING] {spot_name} -> {state_txt}")

        # SPOT_1~4 → S1~S4 로 매핑
        mapping = {
            "SPOT_1": "S1",
            "SPOT_2": "S2",
            "SPOT_3": "S3",
            "SPOT_4": "S4",
        }
        slot_name = mapping.get(spot_name)
        if not slot_name:
            return

        try:
            # 번호판 정보는 현재 없으므로 plate=None
            self._tx.set_slot_occupied(slot_name, is_occupied, plate=None)
            self._append_gate_log(
                f"[PARKING] DB 슬롯 갱신 완료 slot={slot_name} occupied={is_occupied}"
            )
        except Exception as exc:  # noqa: BLE001
            self._append_gate_log(
                f"[PARKING] DB 슬롯 갱신 실패 slot={slot_name} ({exc})"
            )

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

    def send_exit_display(self, line1: str, line2: str) -> None:
        """출구 차단기(esp32_board1_2, DEV-GATE-2) LCD 2줄 출력 명령."""
        if self._gate_server:
            self._gate_server.send_display(line1, line2)


