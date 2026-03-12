import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH)


def _ws_url_with_port_offset(url: str, port_offset: int) -> str:
    """ws://host:port 에서 port + port_offset 한 URL 반환."""
    if not url or port_offset == 0:
        return url
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        port = p.port or (443 if p.scheme == "wss" else 8765)
        new_port = port + port_offset
        netloc = f"{p.hostname}:{new_port}" if p.hostname else ""
        return f"{p.scheme}://{netloc}{p.path or ''}{p.query and '?' + p.query or ''}"
    except Exception:
        return url


class DeviceClientSettings:
    @property
    def server_base_url(self) -> str:
        return os.getenv("SERVER_BASE_URL", "http://127.0.0.1:8000")

    @property
    def client_name(self) -> str:
        return os.getenv("CLIENT_NAME", "device-pc")

    @property
    def arduino_port(self) -> str:
        return os.getenv("ARDUINO_PORT", "/dev/ttyACM0")

    @property
    def arduino_baud(self) -> int:
        return int(os.getenv("ARDUINO_BAUD", "115200"))

    @property
    def udp_listen_host(self) -> str:
        return os.getenv("UDP_LISTEN_HOST", "0.0.0.0")

    @property
    def udp_listen_port(self) -> int:
        # DB/init_manual.sql 기준: rest_port=7080, udp_port=7070
        return int(os.getenv("UDP_LISTEN_PORT", "7070"))

    # ───────── LPR 카메라 (입구/출구) 설정 ─────────
    @property
    def lpr_enter_rest_port(self) -> int:
        """
        esp32_lpr_enter 가 접속하는 REST 서버 포트.

        기본값은 7080 (DB init_manual.sql 의 rest_port 기준).
        """
        return int(os.getenv("LPR_ENTER_REST_PORT", "7080"))

    @property
    def lpr_enter_udp_port(self) -> int:
        """
        LPR 입구 카메라 UDP 영상 포트.

        기본값은 LPR_CAMERA_SERVER_UDP_PORT1, 없으면
        LPR_CAMERA_SERVER_UDP_PORT (구버전 환경변수), 최종 7070.
        """
        return int(
            os.getenv(
                "LPR_CAMERA_SERVER_UDP_PORT1",
                os.getenv("LPR_CAMERA_SERVER_UDP_PORT", "7070"),
            )
        )

    @property
    def lpr_exit_udp_port(self) -> int:
        """
        LPR 출구 카메라 UDP 영상 포트.

        기본값은 LPR_CAMERA_SERVER_UDP_PORT2, 없으면 7090.
        """
        return int(os.getenv("LPR_CAMERA_SERVER_UDP_PORT2", "7090"))

    # ESP32 보드 TCP 설정
    @property
    def esp32_1_host(self) -> str:
        return os.getenv("ESP32_1_HOST", "192.168.0.201")

    @property
    def esp32_1_port(self) -> int:
        return int(os.getenv("ESP32_1_PORT", "9001"))

    @property
    def esp32_2_host(self) -> str:
        return os.getenv("ESP32_2_HOST", "192.168.0.202")

    @property
    def esp32_2_port(self) -> int:
        return int(os.getenv("ESP32_2_PORT", "9002"))

    @property
    def device_no(self) -> str:
        # device_clients 테이블과 매칭되는 device_no
        return os.getenv("device_no", "DC-001")

    # 2.client 로 LPR 실시간 영상 전송용 WebSocket (입구·출구 각각 별도 주소)
    @property
    def lpr_ws_server_entry_url(self) -> str:
        """2.client 입구 LPR 수신 주소. 예: ws://192.168.0.10:8765"""
        u = os.getenv("LPR_WS_SERVER_ENTRY_URL", "").strip()
        if u:
            return u
        u = os.getenv("LPR_WS_SERVER_URL", "").strip()
        if u:
            return _ws_url_with_port_offset(u, 0)
        return ""

    @property
    def lpr_ws_server_exit_url(self) -> str:
        """2.client 출구 LPR 수신 주소. 예: ws://192.168.0.10:8766"""
        u = os.getenv("LPR_WS_SERVER_EXIT_URL", "").strip()
        if u:
            return u
        u = os.getenv("LPR_WS_SERVER_URL", "").strip()
        if u:
            return _ws_url_with_port_offset(u, 1)
        return ""

    @property
    def lpr_plate_model_path(self) -> str:
        """
        번호판 인식 YOLO 모델 경로 (best.pt).
        기본: 3.device_client/lpr_models/best.pt, 없으면 Ztmp_lpr_detect/lpr_system_release/best.pt
        """
        default = BASE_DIR / "lpr_models" / "best.pt"
        if not default.is_file():
            fallback = (BASE_DIR.parent / "Ztmp_lpr_detect" / "lpr_system_release" / "best.pt").resolve()
            if fallback.is_file():
                return str(fallback)
        default = str(default.resolve())
        raw = os.getenv("LPR_PLATE_MODEL_PATH", default)
        p = Path(raw)
        if not p.is_absolute():
            p = (BASE_DIR / raw).resolve()
        return str(p)


settings = DeviceClientSettings()

