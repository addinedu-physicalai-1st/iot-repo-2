import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH)


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

    # ───────── LPR 입구 카메라(esp32_lpr_enter) 설정 ─────────
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

        기본값은 LPR_CAMERA_SERVER_UDP_PORT, 없으면 7070.
        """
        return int(os.getenv("LPR_CAMERA_SERVER_UDP_PORT", "7070"))

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


settings = DeviceClientSettings()

