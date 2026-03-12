from typing import Any, Dict, List

import httpx

from config import settings


class ApiClient:
    def __init__(self) -> None:
        self._client = httpx.Client(
            base_url=settings.server_base_url,
            timeout=5.0,
        )

    def health(self) -> Dict[str, Any]:
        resp = self._client.get("/health")
        resp.raise_for_status()
        return resp.json()

    def get_dashboard(self) -> Dict[str, Any]:
        resp = self._client.get("/parking/dashboard")
        resp.raise_for_status()
        return resp.json()

    def get_operation_mode(self) -> Dict[str, Any]:
        resp = self._client.get("/parking/operation-mode")
        resp.raise_for_status()
        return resp.json()

    def set_operation_mode(self, operation_mode_on: bool) -> Dict[str, Any]:
        resp = self._client.post(
            "/parking/operation-mode",
            params={"operation_mode_on": str(operation_mode_on).lower()},
        )
        resp.raise_for_status()
        return resp.json()

    def get_gate_state(self) -> Dict[str, Any]:
        resp = self._client.get("/parking/gate-state")
        resp.raise_for_status()
        return resp.json()

    def set_gate_state(
        self,
        *,
        gate_sensor_state: int | None = None,
        gate_auto_state: int | None = None,
    ) -> Dict[str, Any]:
        params: dict[str, str] = {}
        if gate_sensor_state is not None:
            params["gate_sensor_state"] = str(int(gate_sensor_state))
        if gate_auto_state is not None:
            params["gate_auto_state"] = str(int(gate_auto_state))
        resp = self._client.post("/parking/gate-state", params=params)
        resp.raise_for_status()
        return resp.json()

    def list_devices(self) -> List[Dict[str, Any]]:
        resp = self._client.get("/devices/")
        resp.raise_for_status()
        return resp.json()

    # ─── 센서 API ──────────────────────────────────────────────
    def list_sensors(self) -> List[Dict[str, Any]]:
        resp = self._client.get("/sensors/")
        resp.raise_for_status()
        return resp.json()

    def create_sensor(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self._client.post("/sensors/", json=payload)
        resp.raise_for_status()
        return resp.json()

    def update_sensor(
        self,
        sensor_id: int,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        resp = self._client.put(f"/sensors/{sensor_id}", json=payload)
        resp.raise_for_status()
        return resp.json()

    def deactivate_sensor(self, sensor_id: int) -> None:
        resp = self._client.delete(f"/sensors/{sensor_id}")
        resp.raise_for_status()

    def list_residents(self) -> List[Dict[str, Any]]:
        resp = self._client.get("/residents/")
        resp.raise_for_status()
        return resp.json()

    def get_resident(self, resident_id: int) -> Dict[str, Any]:
        resp = self._client.get(f"/residents/{resident_id}")
        resp.raise_for_status()
        return resp.json()

    def create_resident(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self._client.post("/residents/", json=payload)
        resp.raise_for_status()
        return resp.json()

    def update_resident(
        self,
        resident_id: int,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        resp = self._client.put(f"/residents/{resident_id}", json=payload)
        resp.raise_for_status()
        return resp.json()

    def delete_resident(self, resident_id: int) -> None:
        resp = self._client.delete(f"/residents/{resident_id}")
        resp.raise_for_status()

    def list_rfid_cards(self) -> List[Dict[str, Any]]:
        resp = self._client.get("/residents/rfid")
        resp.raise_for_status()
        return resp.json()

    def create_rfid_card(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self._client.post("/residents/rfid", json=payload)
        resp.raise_for_status()
        return resp.json()

    def update_rfid_card(
        self,
        card_id: int,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        resp = self._client.put(f"/residents/rfid/{card_id}", json=payload)
        resp.raise_for_status()
        return resp.json()

    def delete_rfid_card(self, card_id: int) -> None:
        resp = self._client.delete(f"/residents/rfid/{card_id}")
        resp.raise_for_status()

    # ─── 입·출차 기록 (번호판 이미지 경로 포함) ─────────────────────
    def list_parking_records(self, limit: int = 100) -> List[Dict[str, Any]]:
        """입·출차 기록 목록 (entry_img_path, exit_img_path 포함)."""
        resp = self._client.get("/parking/records", params={"limit": limit})
        resp.raise_for_status()
        return resp.json()

    def get_parking_record(self, record_id: int) -> Dict[str, Any]:
        """단일 입·출차 기록 조회."""
        resp = self._client.get(f"/parking/records/{record_id}")
        resp.raise_for_status()
        return resp.json()

    def update_parking_record(self, record_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        """입·출차 기록 일부 수정 (번호판, 등록 여부, 요금 등)."""
        resp = self._client.patch(f"/parking/records/{record_id}", json=payload)
        resp.raise_for_status()
        return resp.json()

    def get_record_entry_image_url(self, record_id: int) -> str:
        """입차 번호판 이미지 URL (브라우저/이미지 뷰어에서 열기용)."""
        base = str(self._client.base_url).rstrip("/")
        return f"{base}/parking/records/{record_id}/entry-image"

    def get_record_exit_image_url(self, record_id: int) -> str:
        """출차 번호판 이미지 URL."""
        base = str(self._client.base_url).rstrip("/")
        return f"{base}/parking/records/{record_id}/exit-image"

    def close(self) -> None:
        self._client.close()

