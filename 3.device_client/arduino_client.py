import threading
from typing import Callable, Optional

import serial

from config import settings


"""
아두이노 ↔ 디바이스 PC 직렬 통신 프로토콜 (제안)

- 아두이노 -> PC (슬롯 상태 보고)
  예) "SLOT,S1,1\n"   # S1 자리에 차량 있음
      "SLOT,S3,0\n"   # S3 자리가 비어 있음

- PC -> 아두이노 (제어 명령, 예: 차단기, 타워 이동 등)
  예) "CMD,GATE,OPEN\n"
      "CMD,TOWER,T1\n"
"""


class ArduinoClient:
    def __init__(self, on_slot_update: Optional[Callable[[str, bool], None]] = None) -> None:
        self.port = settings.arduino_port
        self.baud = settings.arduino_baud
        self.on_slot_update = on_slot_update
        self._ser: Optional[serial.Serial] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def connect(self) -> None:
        self._ser = serial.Serial(self.port, self.baud, timeout=1)
        self._running = True
        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()

    def _reader_loop(self) -> None:
        assert self._ser is not None
        print(f"[Arduino] Listening on {self.port} @ {self.baud}")
        while self._running:
            try:
                line = self._ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                # 예: SLOT,S1,1
                parts = line.split(",")
                if len(parts) == 3 and parts[0] == "SLOT":
                    slot_name = parts[1].strip()
                    occupied = parts[2].strip() == "1"
                    if self.on_slot_update:
                        self.on_slot_update(slot_name, occupied)
                else:
                    print(f"[Arduino] RAW: {line}")
            except Exception as e:  # noqa: BLE001
                print(f"[Arduino] Error: {e}")

    def send_command(self, cmd: str) -> None:
        """간단한 제어 명령 전송용. 예: 'CMD,GATE,OPEN'"""
        if not self._ser:
            return
        data = (cmd.strip() + "\n").encode("utf-8")
        self._ser.write(data)

    def close(self) -> None:
        self._running = False
        if self._ser:
            self._ser.close()
            self._ser = None

