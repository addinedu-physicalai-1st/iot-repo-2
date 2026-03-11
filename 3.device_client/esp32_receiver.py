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
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        on_frame: Optional[Callable[[int, np.ndarray], None]] = None,
    ) -> None:
        """
        ESP32 UDP 수신기.

        - host/port 를 지정하지 않으면 config.settings 의 udp_listen_host/udp_listen_port 를 사용한다.
        - on_frame(f_no, img) 콜백으로 완성된 프레임을 전달한다.
        """
        self.on_frame = on_frame
        self._host = host or settings.udp_listen_host
        self._port = port or settings.udp_listen_port
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_frame_ts: float = 0.0

    def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        self._sock.bind((self._host, self._port))
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(
            f"[ESP32] UDP listening on {self._host}:{self._port}"
        )

    def _loop(self) -> None:
        assert self._sock is not None
        # frames[f_no] = {"chunks": {p_no: bytes}, "target_checksum": Optional[int]}
        # 헤더 포맷은 두 가지를 모두 지원한다.
        # 1) 구버전(esp32_cam_udp 등): [f_no, p_no, checksum] + data
        # 2) 555 버전(esp32_lpr_enter_555 등): [f_no, p_no, is_last, checksum] + data
        frames: dict[int, dict[str, object]] = {}
        last_frame_no = -1

        while self._running:
            try:
                data, _ = self._sock.recvfrom(2048)
                if len(data) < 4:
                    continue

                f_no = data[0]
                p_no = data[1]

                # 헤더 포맷 자동 감지
                header_type = "legacy"  # 또는 "555"
                is_last = 0
                if len(data) >= 5 and data[2] in (0, 1):
                    # 555 포맷: [f_no, p_no, is_last, checksum] + data
                    header_type = "555"
                    is_last = data[2]
                    received_checksum = data[3]
                    chunk = data[4:]
                else:
                    # 구버전 포맷: [f_no, p_no, checksum] + data
                    received_checksum = data[2]
                    chunk = data[3:]

                if f_no < last_frame_no and (last_frame_no - f_no) < 200:
                    continue

                if f_no not in frames:
                    if len(frames) > 3:
                        del frames[min(frames.keys())]
                    frames[f_no] = {"chunks": {}, "target_checksum": None}

                entry = frames[f_no]
                chunks: dict[int, bytes] = entry["chunks"]  # type: ignore[assignment]
                chunks[p_no] = chunk

                # 555 포맷: 마지막 패킷(is_last == 1)에서 checksum 저장
                if header_type == "555" and is_last == 1:
                    entry["target_checksum"] = received_checksum
                # 구버전 포맷: JPEG EOI(0xFFD9)를 포함한 패킷에서 checksum 저장
                elif header_type == "legacy" and b"\xff\xd9" in chunk:
                    entry["target_checksum"] = received_checksum

                target = entry.get("target_checksum")  # type: ignore[assignment]
                if target is not None:
                    indices = sorted(chunks.keys())
                    # 청크가 0부터 연속적으로 모두 도착했는지 확인
                    if indices and indices[0] == 0 and len(indices) == indices[-1] + 1:
                        full_data = b"".join(chunks[i] for i in indices)

                        # 체크섬 검증 (sum(full_data) % 256)
                        calculated_checksum = sum(full_data) % 256
                        if calculated_checksum != target:
                            print(
                                f"[ESP32] Frame {f_no} checksum mismatch "
                                f"calc={calculated_checksum}, recv={target}"
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

