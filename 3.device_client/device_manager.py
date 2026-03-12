from __future__ import annotations

import time

from info_manager import InfoManager
from transmission_manager import TransmissionManager
from esp32_gate_server import Esp32GateServer

ENTRY_GATE_GUID = "DEV-GATE-1"
MANUAL_GATE_RESEND_INTERVAL_SEC = 2.0


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
        self._gate_motor_status: dict[str, object] = {
            "state": "UNKNOWN",
            "source": "",
            "detail": "",
            "updated_at": 0.0,
        }
        self._last_exit_lcd_signature: tuple[bool, int, int, int, str] | None = None
        self._last_manual_gate_cmd_at: float = 0.0
        # parking_slots, device 등록 정보 등을 위한 내부 상태
        self._parking_state: dict[str, bool] = {}
        # 입구/출구 플로우용 플래그 (케이스 1/3: LPR 번호판을 한 번만 서버에 보낼 때 사용)
        self._pending_entry_trigger: bool = False
        self._pending_exit_trigger: bool = False
        # 입구 자동 모드용 상태 (등록 차량 입차 후 차량 통과 시 닫기)
        self._entry_gate_pending_close: bool = False
        self._last_operation_mode_on: bool = True
        self._last_gate_sensor_state: int = 1
        self._last_gate_auto_state: int = 0
        self._last_entry_sensor_detected: bool = False
        self._last_exit_sensor_detected: bool = False

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
                on_gate_motor_event=self._on_gate_motor_event,
                on_gate_event=self._on_gate_event,
            )
            self._gate_server.start()

        # 앱 기동 직후에는 DB 에 남아있던 이전 연결 상태를 신뢰하지 않고,
        # gate_controller / street_parking_controller 를 모두 끊김으로 초기화한다.
        # 이후 실제 소켓 연결/keep-alive 기준으로만 is_connected 를 다시 세팅.
        try:
            self._tx.set_gate_connected(False)
            self._tx.set_street_parking_connected(False)
            self._tx.set_tower_slots_inactive()
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
            self._tx.set_entry_exit_sensor_connected(connected)
            if guid == ENTRY_GATE_GUID:
                # 보드1_1 연결 정책:
                # - 연결됨: 기본 '열림(2)' 상태로 서버/UI 동기화
                # - 끊김: '연결 안됨(0)' 상태로 서버/UI 동기화
                self._tx.set_gate_state(
                    gate_sensor_state=2 if connected else 0,
                    gate_auto_state=0 if not connected else None,
                )
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
            if device_guid == ENTRY_GATE_GUID:
                self._tx.set_gate_state(gate_sensor_state=2)
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

    def _on_gate_motor_event(self, state: str, src: str, detail: str) -> None:
        self._gate_motor_status = {
            "state": state,
            "source": src,
            "detail": detail,
            "updated_at": time.time(),
        }

    def _on_gate_event(self, ev: int, src: str, ext: str) -> None:
        """게이트 이벤트를 받아 입/출구 APDS 감지 기반 OCR 플래그를 갱신한다."""
        if ev in (1, 2):  # EV_ENTRY / EV_EXIT
            # 테스트 단계에서는 APDS 감지가 어느 쪽에서 오더라도
            # 입구/출구 OCR 모두 실행 가능하도록 플래그를 동시에 갱신한다.
            self._tx.mark_lpr_apds_detected(is_exit=False)
            self._tx.mark_lpr_apds_detected(is_exit=True)
            self._tx.pulse_entry_exit_sensor_detected(is_exit=(ev == 2))
            # EV_ENTRY(1) 감지 시, 다음에 들어오는 입구 LPR 번호판을
            # parking_entry_event 로 서버에 기록할 수 있도록 플래그 설정
            if ev == 1:
                self._pending_entry_trigger = True
            # EV_EXIT(2) 감지 시, 다음에 들어오는 출구 LPR 번호판을
            # parking_exit_event 로 서버에 기록할 수 있도록 플래그 설정
            if ev == 2:
                self._pending_exit_trigger = True

    # ───────── 입구 LPR 번호판 콜백 (케이스 1: 등록 차량 입차 기록) ─────────
    def on_entry_lpr_plate(self, plate: str) -> None:
        """
        MainWindow 의 입구 LPR 워커에서 번호판이 안정적으로 인식되었을 때 호출.
        - 직전에 EV_ENTRY 트리거가 있었을 때만 서버에 입차 이벤트를 전송한다.
        """
        if not self._pending_entry_trigger:
            return
        self._pending_entry_trigger = False
        try:
            rec = self._tx.send_parking_entry_event(plate, entry_img_path=None)
            is_reg = int(rec.get("is_registered") or 0)
            self._append_gate_log(
                f"[ENTRY] plate={plate} record_id={rec.get('record_id')} is_registered={is_reg}"
            )

            # ----- 케이스 1: 등록 차량 + 자동 모드일 때 입구 게이트 자동 개방 -----
            if (
                is_reg == 1
                and self._last_operation_mode_on
                and int(self._last_gate_sensor_state) == 3  # 3: 자동 모드
            ):
                self._append_gate_log(
                    "[ENTRY] 등록 차량 + 자동 모드 → 게이트 자동 개방 시도"
                )
                result = self.open_gate()
                if result.get("ok"):
                    # 차량이 통과한 뒤(entry_sensor_detected=False로 떨어질 때) 자동으로 닫기
                    self._entry_gate_pending_close = True
                else:
                    self._append_gate_log(
                        f"[ENTRY] open_gate 실패 state={result.get('state')} detail={result.get('detail')}"
                    )
        except Exception as exc:  # noqa: BLE001
            self._append_gate_log(f"[ENTRY] parking_entry_event 실패 plate={plate} ({exc})")

    # ───────── 출구 LPR 번호판 콜백 (케이스 3: 등록 차량 출차 기록) ─────────
    def on_exit_lpr_plate(self, plate: str) -> None:
        """
        MainWindow 의 출구 LPR 워커에서 번호판이 안정적으로 인식되었을 때 호출.
        - 직전에 EV_EXIT 트리거가 있었을 때만 서버에 출차 이벤트를 전송한다.
        """
        if not self._pending_exit_trigger:
            return
        self._pending_exit_trigger = False
        try:
            rec = self._tx.send_parking_exit_event(plate, exit_img_path=None, rfid_card_uid=None)
            self._append_gate_log(
                f"[EXIT] plate={plate} record_id={rec.get('record_id')} is_registered={rec.get('is_registered')} "
                f"charge={rec.get('charge_amount')}"
            )
        except Exception as exc:  # noqa: BLE001
            self._append_gate_log(f"[EXIT] parking_exit_event 실패 plate={plate} ({exc})")

    def get_gate_motor_status(self) -> dict[str, object]:
        return dict(self._gate_motor_status)

    def open_gate(self) -> dict[str, object]:
        if not self._gate_server:
            return {"ok": False, "state": "UNKNOWN", "detail": "NO_SERVER"}
        result = self._gate_server.send_open_gate()
        self._gate_motor_status = self._gate_server.get_gate_motor_status()
        self._append_gate_log(
            f"[CMD-RESULT] OPEN ok={result.get('ok')} state={result.get('state')} detail={result.get('detail')}"
        )
        return result

    def close_gate(self) -> dict[str, object]:
        if not self._gate_server:
            return {"ok": False, "state": "UNKNOWN", "detail": "NO_SERVER"}
        result = self._gate_server.send_close_gate()
        self._gate_motor_status = self._gate_server.get_gate_motor_status()
        self._append_gate_log(
            f"[CMD-RESULT] CLOSE ok={result.get('ok')} state={result.get('state')} detail={result.get('detail')}"
        )
        return result

    def sync_entry_gate_mode(
        self,
        gate_connected: bool,
        gate_sensor_state: int,
        entry_sensor_detected: bool,
        exit_sensor_detected: bool,
    ) -> None:
        """
        대시보드의 차단기 상태(닫힘/열림/자동)를 실제 보드1_1 모터 상태와 동기화한다.

        - 연결 해제 시: 서버 상태를 0(연결 안됨)으로 강제
        - 연결 시 0이면: 기본값 2(열림)으로 복구
        - 수동(1/2) 선택 시: 해당 상태를 유지하도록 주기적으로 재명령
        - 자동(3) 선택 시: 이제 LPR/입출차 플로우(on_entry_lpr_plate 등)에서만
          게이트를 여닫고, 여기서는 자동 닫힘 조건만 처리한다.
        """
        # 최근 스냅샷 저장 (입출차 플로우에서 참조)
        self._last_operation_mode_on = True  # 운영 모드는 2.client 대시보드에서만 변경, 단순 ON 기준
        self._last_gate_sensor_state = int(gate_sensor_state)
        self._last_entry_sensor_detected = bool(entry_sensor_detected)
        self._last_exit_sensor_detected = bool(exit_sensor_detected)
        if not gate_connected:
            self._tx.set_gate_state(gate_sensor_state=0, gate_auto_state=0)
            return

        target_state = int(gate_sensor_state)
        if target_state == 0:
            self._tx.set_gate_state(gate_sensor_state=2)
            target_state = 2

        # 수동 모드(1/2)에서는 기존 로직 유지
        if target_state in (1, 2):
            desired_motor_state = "CLOSED" if target_state == 1 else "OPEN"
            desired_auto_state = 2 if target_state == 1 else 1
        elif target_state == 3:
            # 자동 모드(3)에서는 여기서 더 이상 감지 센서만으로 자동 개폐하지 않는다.
            # 대신 입출차 플로우(on_entry_lpr_plate/on_exit_lpr_plate)에서 open_gate 를 호출하고,
            # 여기서는 "언제 닫을지"만 판단한다.
            current_motor_state = str(self._gate_motor_status.get("state") or "").upper()
            # 입구 게이트를 열어둔 상태에서, 차량이 통과해 entry_sensor_detected 가 False 로 떨어지면 닫기
            if self._entry_gate_pending_close and not entry_sensor_detected:
                self._append_gate_log("[ENTRY] 차량 통과 감지 → 게이트 자동 닫힘 시도")
                result = self.close_gate()
                if result.get("ok"):
                    self._entry_gate_pending_close = False
            # 자동 모드에서는 여기서 추가 open/close 명령을 보내지 않는다.
            return
        else:
            return

        current_motor_state = str(self._gate_motor_status.get("state") or "").upper()
        now = time.time()
        if (
            current_motor_state == desired_motor_state
            and (now - self._last_manual_gate_cmd_at) < MANUAL_GATE_RESEND_INTERVAL_SEC
        ):
            return
        if (now - self._last_manual_gate_cmd_at) < MANUAL_GATE_RESEND_INTERVAL_SEC:
            return

        if target_state == 3:
            result = self.open_gate() if desired_motor_state == "OPEN" else self.close_gate()
        else:
            result = self.close_gate() if target_state == 1 else self.open_gate()
        self._last_manual_gate_cmd_at = now
        if result.get("ok"):
            if target_state in (1, 2):
                self._tx.set_gate_state(gate_sensor_state=target_state)
            self._tx.set_gate_auto_state(desired_auto_state)

    def write_siteid(self, site_id: str) -> None:
        if self._gate_server:
            self._gate_server.send_write_siteid(site_id)

    def send_exit_display(self, line1: str, line2: str) -> bool:
        """출구 차단기(esp32_board1_2, DEV-GATE-2) LCD 2줄 출력 명령."""
        if self._gate_server:
            return self._gate_server.send_display(line1, line2)
        return False

    def sync_exit_lcd_base(
        self,
        operation_mode_on: bool,
        free_slots: int,
        gate_sensor_state: int,
        gate_auto_state: int,
        message_type: str = "default",
    ) -> None:
        """
        출구 보드 LCD 기본 메시지 동기화.
        - message_type 으로 향후 입차 상황별 메시지 분기 확장 가능
        """
        signature = (operation_mode_on, int(free_slots), int(gate_sensor_state), int(gate_auto_state), message_type)
        if self._last_exit_lcd_signature == signature:
            return

        # 0: 연결안됨, 1: 닫힘, 2: 열림, 3: 자동
        # 자동(3)일 때도 이제는 gate_auto_state 를 주기적으로 강제로 바꾸지 않고,
        # LCD 메시지만 운영 상태에 맞게 표시한다.
        if int(gate_sensor_state) == 3:
            if operation_mode_on:
                line1 = "Welcom PARKING"
                line2 = f"empty {int(free_slots)}"
            else:
                line1 = "PARKING Closed."
                line2 = "Sorry."
        else:
            # 수동/미연결 모드에서는 기본 베이스만 제공(향후 타입별 확장 포인트)
            if int(gate_sensor_state) == 1:
                line1 = "GATE MANUAL"
                line2 = "CLOSED"
            elif int(gate_sensor_state) == 2:
                line1 = "GATE MANUAL"
                line2 = "OPEN"
            else:
                line1 = "GATE OFFLINE"
                line2 = "CHECK CONNECT"

        sent = self.send_exit_display(line1[:16], line2[:16])
        if sent:
            self._last_exit_lcd_signature = signature


