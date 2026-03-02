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

    def list_devices(self) -> List[Dict[str, Any]]:
        resp = self._client.get("/devices/")
        resp.raise_for_status()
        return resp.json()

    def list_residents(self) -> List[Dict[str, Any]]:
        resp = self._client.get("/residents/")
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

    def close(self) -> None:
        self._client.close()

