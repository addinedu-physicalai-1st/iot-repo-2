from __future__ import annotations

import time
from typing import Dict, List

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
        self._gate_connected: bool = False
        
        # 입/출구 분리를 위해 GUID 별로 로그와 장치 구성을 관리
        self._per_device_logs: Dict[str, List[str]] = {}
        self._per_device_hw: Dict[str, List[Dict[str, str]]] = {}
        
        # GUID -> IP 매핑 (연결된 장치 추적용)
        self._guid_to_ip: Dict[str, str] = {}
        self._ip_to_guid: Dict[str, str] = {}
        self._gate_connected: bool = False
        # parking_slots, device 등록 정보 등을 위한 내부 상태
        self._parking_state: dict[str, bool] = {}

    def start(self) -> None:
        """
        - ESP32 보드1(입구 차단기) TCP 서버 스레드 시작
        - 향후 ESP32-CAM/시리얼 장치 스레드도 여기서 시작 예정
        """
        # 앱 기동 시, 현재 클라이언트가 관리하는 장비들의 연결 상태를 모두 초기화 
        self._tx.reset_device_connections(["gate_controller", "street_parking_controller"])

        if self._gate_server is None:
            self._gate_server = Esp32GateServer(
                host="0.0.0.0",
                port=8080,
                on_log=self._append_gate_log,
                on_device_list=self._on_device_list,
                on_state_change=self._on_gate_state_change,
                on_register=self._on_device_register,
                on_parking_event=self._on_parking_event,
                on_event=self._on_device_event,
            )
            self._gate_server.start()


    def stop(self) -> None:
        """start 에서 시작한 장치 관련 스레드를 종료."""
        if self._gate_server is not None:
            self._gate_server.stop()
            self._gate_server = None

    # ───────── ESP32 게이트 관련 헬퍼 (UI에서 사용) ─────────
    def _append_gate_log(self, msg: str, guid: str | None = None) -> None:
        # 특정 GUID 가 없으면 SYSTEM 로그로 분류
        target_guid = guid or "SYSTEM"
        if target_guid not in self._per_device_logs:
            self._per_device_logs[target_guid] = []
        
        timestamp = time.strftime("[%H:%M:%S]")
        self._per_device_logs[target_guid].append(f"{timestamp} {msg}")
        # 최대 100줄만 유지
        if len(self._per_device_logs[target_guid]) > 100:
            self._per_device_logs[target_guid].pop(0)
        
        # 콘솔 출력 (디버깅용)
        print(f"[{target_guid}] {msg}")

    def _on_gate_state_change(self, connected: bool, ip: str | None = None) -> None:
        # 서버(FastAPI)에 장비 연결 상태 반영
        try:
            if ip:
                self._tx.set_device_connected_by_ip(ip, connected)
                if not connected:
                    # 연결 해제 시 GUID 매핑 정리 (선택적)
                    guid = self._ip_to_guid.get(ip)
                    if guid:
                        self._append_gate_log(f"[GATE] {guid} ({ip}) 연결 해제", guid=guid)
                        # 연결 해제 시 해당 장치의 로그 및 HW 정보도 초기화 (선택적)
                        self._per_device_logs.pop(guid, None)
                        self._per_device_hw.pop(guid, None)
                        self._guid_to_ip.pop(guid, None)
                        self._ip_to_guid.pop(ip, None)
            else:
                pass
        except Exception:
            state = "연결" if connected else "해제"
            self._append_gate_log(f"[GATE] 서버 반영 실패 (상태={state}, IP={ip})")

    def _on_device_list(self, lst: List[Dict[str, str]], ip: str | None = None) -> None:
        """ESP32 로부터 장비 구성(센서/모듈) 목록을 받음."""
        guid = self._ip_to_guid.get(ip or "")
        if guid:
            self._per_device_hw[guid] = lst
            hw_str = ", ".join([f"{item['guid']}->{item['name']}" for item in lst])
            self._append_gate_log(f"[HW] 장치 구성 수신: {hw_str}", guid=guid)
        else:
            # GUID 를 아직 모르는 경우 IP 로 임시 저장하거나 무시
            pass

    # ───────── 장비 등록(DEVICE_GUID 기반 IP 갱신) ─────────
    def _on_device_register(self, device_guid: str, device_name: str, ip: str) -> None:
        """ESP32 가 등록 패킷을 보냄."""
        self._append_gate_log(
            f"[REG] device_register 수신 guid={device_guid} name={device_name} ip={ip}", 
            guid=device_guid
        )
        
        # IP 와 GUID 매핑 저장
        self._ip_to_guid[ip] = device_guid
        self._guid_to_ip[device_guid] = ip
        
        try:
            self._tx.update_device_ip_by_guid(device_guid, ip, device_name=device_name)
            # 등록 성공 시 연결 상태도 True 로 세팅
            self._tx.set_device_connected_by_guid(device_guid, True)
            self._append_gate_log(
                f"[REG] DB 등록 및 연결 완료 guid={device_guid} → {ip}",
                guid=device_guid
            )
        except Exception as exc:
            self._append_gate_log(
                f"[REG] DB 등록 실패 guid={device_guid}: {exc}",
                guid=device_guid
            )

    # ───────── 노상 주차면 이벤트 처리 (parking_slots 동기화) ─────────
    def _on_parking_event(self, spot: str, occupied: bool, ip: str | None = None) -> None:
        """ESP32 에서 노상 주차면(SPOT_x) 감지 이벤트 수신."""
        guid = self._ip_to_guid.get(ip or "")
        self._append_gate_log(f"[PARK] {spot} {'OCCUPIED' if occupied else 'EMPTY'}", guid=guid)
        # DB 동기화
        try:
            self._tx.set_parking_slot_occupied(spot, occupied)
            self._append_gate_log(
                f"[PARKING] DB 슬롯 갱신 완료 slot={spot} occupied={occupied}", guid=guid
            )
        except Exception as exc:  # noqa: BLE001
            self._append_gate_log(
                f"[PARKING] DB 슬롯 갱신 실패 slot={spot} ({exc})", guid=guid
            )

    def _on_device_event(self, ev: int, src: str, ext: str, ip: str | None = None) -> None:
        """ESP32 의 기타 이벤트 (ENTRY, EXIT, RFID 등)"""
        guid = self._ip_to_guid.get(ip or "")
        self._append_gate_log(f"[EVENT] ev={ev} src={src} ext={ext}", guid=guid)
        
        if ev == 2: # EV_EXIT
            # 출차 시 로그 전송
            self._tx.log_exit_event(src)

    def get_gate_logs(self, guid: str | None = None) -> List[str]:
        if not guid:
            # Fallback for general logs
            return self._per_device_logs.get("SYSTEM", [])
        return self._per_device_logs.get(guid, [])

    def get_gate_devices(self, guid: str | None = None) -> List[Dict[str, str]]:
        if not guid:
            return []
        return self._per_device_hw.get(guid, [])

    def open_gate(self, guid: str | None = None) -> None:
        if self._gate_server:
            self._gate_server.send_open_gate(target_guid=guid)

    def close_gate(self, guid: str | None = None) -> None:
        if self._gate_server:
            self._gate_server.send_close_gate(target_guid=guid)

    def write_siteid(self, site_id: str, guid: str | None = None) -> None:
        if self._gate_server:
            self._gate_server.send_write_siteid(site_id, target_guid=guid)

    def send_lcd_text(self, line1: str, line2: str = "", guid: str | None = None) -> None:
        if self._gate_server:
            self._gate_server.send_lcd_text(line1, line2, target_guid=guid)


