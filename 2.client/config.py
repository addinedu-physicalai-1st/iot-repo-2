import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH)


class ClientSettings:
    @property
    def server_base_url(self) -> str:
        return os.getenv("SERVER_BASE_URL", "http://127.0.0.1:8000")

    @property
    def client_name(self) -> str:
        return os.getenv("CLIENT_NAME", "client-pc")

    @property
    def udp_listen_host(self) -> str:
        return os.getenv("UDP_LISTEN_HOST", "0.0.0.0")

    @property
    def udp_listen_port(self) -> int:
        return int(os.getenv("UDP_LISTEN_PORT", "9100"))

    # LPR 실시간 영상 수신용 WebSocket 서버 (입구·출구 각각 별도 포트/스레드)
    @property
    def lpr_ws_host(self) -> str:
        return os.getenv("LPR_WS_HOST", "0.0.0.0")

    @property
    def lpr_ws_port_entry(self) -> int:
        return int(os.getenv("LPR_WS_PORT_ENTRY", "8765"))

    @property
    def lpr_ws_port_exit(self) -> int:
        return int(os.getenv("LPR_WS_PORT_EXIT", "8766"))


settings = ClientSettings()

