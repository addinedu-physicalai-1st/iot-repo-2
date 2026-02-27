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

    def close(self) -> None:
        self._client.close()

