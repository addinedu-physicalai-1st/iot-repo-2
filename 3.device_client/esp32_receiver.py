import socket
import threading
import time
from typing import Callable, Optional

import cv2
import numpy as np

from config import settings


"""
ESP32 카메라 ↔ 디바이스 PC UDP 프로토콜

- esp32_wifi_webcam_ver7.ino 기준:
  각 패킷에 [frameNo(1바이트), packetNo(1바이트), checksum(1바이트)] + JPEG 데이터 조각(최대 1024바이트)
  마지막 패킷에서 checksum 은 전체 JPEG 바이트 합계의 8비트 합(sum % 256)
"""


class Esp32UdpReceiver:
    def __init__(self, on_frame: Optional[Callable[[int, np.ndarray], None]] = None) -> None:
        self.on_frame = on_frame
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_frame_ts: float = 0.0

    def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        self._sock.bind((settings.udp_listen_host, settings.udp_listen_port))
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(
            f"[ESP32] UDP listening on {settings.udp_listen_host}:{settings.udp_listen_port}"
        )

    def _loop(self) -> None:
        assert self._sock is not None
        # frames[f_no] = {"chunks": {p_no: bytes}, "target_checksum": int}
        frames: dict[int, dict[str, object]] = {}
        last_frame_no = -1

        while self._running:
            try:
                data, _ = self._sock.recvfrom(2048)
                if len(data) < 4:
                    continue

                f_no = data[0]
                p_no = data[1]
                received_checksum = data[2]
                chunk = data[3:]

                if f_no < last_frame_no and (last_frame_no - f_no) < 200:
                    continue

                if f_no not in frames:
                    if len(frames) > 3:
                        del frames[min(frames.keys())]
                    frames[f_no] = {"chunks": {}, "target_checksum": 0}

                entry = frames[f_no]
                chunks: dict[int, bytes] = entry["chunks"]  # type: ignore[assignment]
                chunks[p_no] = chunk

                # 마지막 패킷(JPEG 마커 포함)인 경우 체크섬 저장 후 프레임 조립
                if b"\xff\xd9" in chunk:
                    entry["target_checksum"] = received_checksum

                    indices = sorted(chunks.keys())
                    # 청크가 0부터 연속적으로 모두 도착했는지 확인
                    if indices and indices[0] == 0 and len(indices) == indices[-1] + 1:
                        full_data = b"".join(chunks[i] for i in indices)

                        # 체크섬 검증 (sum(full_data) % 256)
                        calculated_checksum = sum(full_data) % 256
                        if calculated_checksum != entry["target_checksum"]:
                            print(
                                f"[ESP32] Frame {f_no} checksum mismatch "
                                f"calc={calculated_checksum}, recv={received_checksum}"
                            )
                            frames.pop(f_no, None)
                            continue

                        nparr = np.frombuffer(full_data, dtype=np.uint8)
                        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        if img is not None and self.on_frame:
                            self.on_frame(f_no, img)
                            last_frame_no = f_no
                            self._last_frame_ts = time.time()

                    # 정리: 현재 프레임 이하 모두 삭제
                    frames = {k: v for k, v in frames.items() if k > f_no}
            except Exception as e:  # noqa: BLE001
                print(f"[ESP32] Error: {e}")

    def stop(self) -> None:
        self._running = False
        if self._sock:
            self._sock.close()
            self._sock = None

    def has_recent_frame(self, timeout_sec: float = 5.0) -> bool:
        """
        최근 timeout_sec 초 이내에 카메라 프레임을 받은 적이 있는지 여부.
        """
        if self._last_frame_ts <= 0:
            return False
        return (time.time() - self._last_frame_ts) <= timeout_sec

