from typing import Any, Dict, List

import httpx

from config import settings


class ApiClient:
    def __init__(self) -> None:
        self._client = httpx.Client(base_url=settings.server_base_url, timeout=5.0)

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

    def close(self) -> None:
        self._client.close()

