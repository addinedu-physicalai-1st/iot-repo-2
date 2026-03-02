from typing import Any, Dict

import httpx

from config import settings


class DeviceApiClient:
    """디바이스 PC에서 서버(FastAPI)로 상태를 올리는 용도."""

    def __init__(self) -> None:
        self._client = httpx.Client(base_url=settings.server_base_url, timeout=5.0)

    def health(self) -> Dict[str, Any]:
        resp = self._client.get("/health")
        resp.raise_for_status()
        return resp.json()

    def set_slot_occupied(self, slot_name: str, occupied: bool, plate: str | None = None) -> None:
        """슬롯 이름(S1~S4, T1~T6) 기준으로 점유 상태를 서버에 반영."""
        # 슬롯 id를 얻기 위해 이름으로 조회
        resp = self._client.get("/parking/slots")
        resp.raise_for_status()
        slots = resp.json()
        slot_id = None
        for s in slots:
            if s.get("name") == slot_name:
                slot_id = s.get("id")
                break
        if slot_id is None:
            return

        if occupied:
            params = {}
            if plate:
                params["plate"] = plate
            self._client.post(f"/parking/slots/{slot_id}/occupy", params=params)
        else:
            self._client.post(f"/parking/slots/{slot_id}/release")

    def log_event(self, event_type: str, message: str = "") -> None:
        # 서버에 EventLog 전용 엔드포인트를 아직 안 만들었으므로
        # TODO: 필요 시 /events API 추가
        print(f"[EVENT] {event_type}: {message}")

    # ─── devices / device_clients 연동 ─────────────────────────
    def list_device_clients(self) -> list[dict[str, Any]]:
        resp = self._client.get("/device-clients/")
        resp.raise_for_status()
        return resp.json()

    def list_devices(self) -> list[dict[str, Any]]:
        resp = self._client.get("/devices/")
        resp.raise_for_status()
        return resp.json()

    def update_device_is_connected(
        self,
        device: dict[str, Any],
        is_connected: bool,
    ) -> None:
        """
        devices 테이블의 is_connected 값을 갱신.

        서버 쪽 DeviceCreate 스키마에 맞춰 전체 payload를 전송한다.
        """
        payload: dict[str, Any] = {
            "name": device.get("name"),
            "type": device.get("type"),
            "device_type": device.get("device_type"),
            "connection_type": device.get("connection_type") or "ethernet",
            "connection_detail": device.get("connection_detail"),
            "control_method": device.get("control_method"),
            "ip_address": device.get("ip_address"),
            "port_info": device.get("port_info"),
            "is_connected": is_connected,
            "sensor_guids": device.get("sensor_guids"),
            "config": device.get("config"),
            "is_active": device.get("is_active", True),
        }
        device_id = device.get("id")
        if device_id is None:
            return
        resp = self._client.put(f"/devices/{device_id}", json=payload)
        resp.raise_for_status()

    def close(self) -> None:
        self._client.close()

