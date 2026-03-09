import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"


def load_env() -> None:
    # 프로젝트 루트의 1.server/.env 로드
    env_file = ENV_PATH if ENV_PATH.exists() else BASE_DIR.parent / ".env"
    load_dotenv(dotenv_path=env_file, override=False)


load_env()


def set_env_value(key: str, value: str) -> None:
    """1.server/.env 에 key=value 를 반영(있으면 교체, 없으면 추가)."""
    env_file = ENV_PATH if ENV_PATH.exists() else BASE_DIR.parent / ".env"
    lines: list[str] = []
    if env_file.exists():
        lines = env_file.read_text(encoding="utf-8").splitlines()

    replaced = False
    prefix = f"{key}="
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            lines[i] = f"{key}={value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{key}={value}")

    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


class Settings:
    @property
    def db_url(self) -> str:
        host = os.getenv("DB_HOST", "127.0.0.1")
        port = os.getenv("DB_PORT", "3306")
        user = os.getenv("DB_USER", "root")
        password = os.getenv("DB_PASSWORD", "")
        name = os.getenv("DB_NAME", "smart_parking")
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}"

    @property
    def udp_host(self) -> str:
        return os.getenv("UDP_HOST", "0.0.0.0")

    @property
    def udp_port(self) -> int:
        return int(os.getenv("UDP_PORT", "9000"))

    @property
    def operation_mode_on(self) -> bool:
        return os.getenv("OPERATION_MODE_ON", "true").lower() in ("1", "true", "yes", "on")

    @property
    def gate_sensor_state(self) -> int:
        # 0: 연결안됨, 1: 닫힘, 2: 열림, 3: 자동
        return int(os.getenv("GATE_SENSOR_STATE", "1"))

    @property
    def gate_auto_state(self) -> int:
        # 0: 동작하지 않음, 1: 열림, 2: 닫힘
        return int(os.getenv("GATE_AUTO_STATE", "0"))


settings = Settings()

