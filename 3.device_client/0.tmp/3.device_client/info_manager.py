from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any, Dict, List

from config import settings


@dataclass
class EnvInfo:
    """환경(.env) 및 정적 설정 정보."""

    server_base_url: str
    client_name: str
    device_no: str
    udp_listen_host: str
    udp_listen_port: int
    lpr_enter_rest_port: int
    lpr_enter_udp_port: int
    esp32_1_host: str
    esp32_1_port: int
    esp32_2_host: str
    esp32_2_port: int


@dataclass
class RuntimeStatus:
    """서버/디바이스와의 통신 과정에서 수집된 런타임 상태."""

    server_health: Dict[str, Any] | None = None
    devices: List[Dict[str, Any]] = field(default_factory=list)
    last_updated_ts: float | None = None


class InfoManager:
    """
    - .env 기반 기본 설정(EnvInfo)
    - 서버/디바이스에서 받아온 상태(RuntimeStatus)
    를 한 곳에서 관리하는 매니저.
    """

    def __init__(self) -> None:
        self._env = EnvInfo(
            server_base_url=settings.server_base_url,
            client_name=settings.client_name,
            device_no=settings.device_no,
            udp_listen_host=settings.udp_listen_host,
            udp_listen_port=settings.udp_listen_port,
            esp32_1_host=settings.esp32_1_host,
            esp32_1_port=settings.esp32_1_port,
            esp32_2_host=settings.esp32_2_host,
            esp32_2_port=settings.esp32_2_port,
            lpr_enter_rest_port=settings.lpr_enter_rest_port,
            lpr_enter_udp_port=settings.lpr_enter_udp_port,
        )
        self._runtime = RuntimeStatus()

    # ───────── Env / 설정 정보 ─────────
    @property
    def env(self) -> EnvInfo:
        return self._env

    # ───────── 런타임 상태 업데이트 ─────────
    def update_from_server(
        self,
        health: Dict[str, Any] | None,
        devices: List[Dict[str, Any]] | None,
    ) -> None:
        if health is not None:
            self._runtime.server_health = health
        if devices is not None:
            self._runtime.devices = devices
        self._runtime.last_updated_ts = time()

    # ───────── 조회용 헬퍼 ─────────
    @property
    def server_health(self) -> Dict[str, Any] | None:
        return self._runtime.server_health

    @property
    def devices(self) -> List[Dict[str, Any]]:
        return list(self._runtime.devices)

    @property
    def last_updated_ts(self) -> float | None:
        return self._runtime.last_updated_ts

