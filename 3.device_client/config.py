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
        return int(os.getenv("UDP_LISTEN_PORT", "7070"))

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


settings = DeviceClientSettings()

