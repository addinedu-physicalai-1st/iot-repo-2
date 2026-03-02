import json
import socket
import threading
from typing import Callable, Optional

from config import settings

"""
ESP32 보드 1, 2와의 TCP/IP 통신 프로토콜 (제안)

- 공통 역할
  보드 1, 2 모두 "주차면 센서 정보"를 올리는 역할:
    {"board": "esp32_1", "type": "slot", "slot": "S1", "occupied": 1}
    {"board": "esp32_2", "type": "slot", "slot": "S3", "occupied": 0}

- 보드별 역할
  * esp32_1: 입출차/노상 주차 관련 슬롯(S1~) 및 센서
  * esp32_2: 평면 주차면 센서(HAM4311, IR 등) + 1602 LCD로 "현재 주차 대수" 등 안내 문구 표시

- 디바이스 PC -> ESP32 보드 (제어 명령)
  향후 필요 시 JSON + '\n' 형태로 추가할 수 있으나,
  현재는 주로 보드에서 PC로 주차면 상태를 보내는 방향으로 사용.
"""


class Esp32BoardClient:
    def __init__(
        self,
        host: str,
        port: int,
        name: str,
        on_message: Optional[Callable[[str, dict], None]] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.name = name
        self.on_message = on_message
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._connected = False

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while self._running:
            try:
                self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._sock.settimeout(5.0)
                self._sock.connect((self.host, self.port))
                print(f"[{self.name}] Connected to {self.host}:{self.port}")
                self._connected = True
                buffer = ""
                while self._running:
                    data = self._sock.recv(1024)
                    if not data:
                        raise ConnectionError("socket closed")
                    buffer += data.decode("utf-8", errors="ignore")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            payload = json.loads(line)
                        except json.JSONDecodeError:
                            print(f"[{self.name}] Invalid JSON: {line}")
                            continue
                        if self.on_message:
                            self.on_message(self.name, payload)
            except Exception as e:  # noqa: BLE001
                print(f"[{self.name}] Error: {e}, reconnecting in 3s...")
                if self._sock:
                    try:
                        self._sock.close()
                    except Exception:
                        pass
                    self._sock = None
                self._connected = False
                if self._running:
                    import time

                    time.sleep(3)

    def send_json(self, payload: dict) -> None:
        if not self._sock:
            return
        try:
            data = json.dumps(payload).encode("utf-8") + b"\n"
            self._sock.sendall(data)
        except Exception as e:  # noqa: BLE001
            print(f"[{self.name}] send_json error: {e}")

    def stop(self) -> None:
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected


class Esp32BoardManager:
    """보드 1, 2를 함께 관리하는 헬퍼."""

    def __init__(self, on_slot_update: Optional[Callable[[str, bool], None]] = None):
        self.on_slot_update = on_slot_update
        self.board1 = Esp32BoardClient(
            settings.esp32_1_host,
            settings.esp32_1_port,
            "esp32_1",
            self._handle_msg,
        )
        self.board2 = Esp32BoardClient(
            settings.esp32_2_host,
            settings.esp32_2_port,
            "esp32_2",
            self._handle_msg,
        )

    def _handle_msg(self, board_name: str, payload: dict) -> None:
        # 슬롯 점유 보고 타입만 우선 처리
        if payload.get("type") == "slot":
            slot = str(payload.get("slot", ""))
            occupied = bool(payload.get("occupied", 0))
            if self.on_slot_update:
                self.on_slot_update(slot, occupied)
        else:
            print(f"[{board_name}] MSG: {payload}")

    def start(self) -> None:
        self.board1.start()
        self.board2.start()

    def stop(self) -> None:
        self.board1.stop()
        self.board2.stop()

    def has_any_connection(self) -> bool:
        return self.board1.is_connected or self.board2.is_connected

