from __future__ import annotations

from typing import Any, Dict, List

from api_client import DeviceApiClient

from info_manager import InfoManager


class TransmissionManager:
    """
    - 서버(FastAPI)와의 HTTP 통신 담당 (DeviceApiClient 래핑)
    - 향후 아두이노/ESP32/UDP 등의 전송 스레드를 함께 관리하는 허브 역할
    """

    def __init__(self, info_manager: InfoManager) -> None:
        self._info = info_manager
        self._api = DeviceApiClient()

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

    # ───────── 종료 처리 ─────────
    def close(self) -> None:
        self._api.close()

