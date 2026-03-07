# ESP32-CAM LPR 서버 666 — UDP 영상 수신 후 화면 표시 전용
# - REST API 없음. UDP 스트림이 들어오면 자동으로 영상 표시
# - esp32_lpr_enter_666.ino 와 쌍으로 사용 (기동 후 자동 UDP 스트리밍)

import os
import sys
import socket
import threading
from queue import Queue

import numpy as np
import cv2
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap

UDP_PORT = 7070
frame_queue = Queue(maxsize=5)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(SCRIPT_DIR, "img")


def udp_receiver_thread(log_signal):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    sock.bind(('0.0.0.0', UDP_PORT))
    frames = {}
    last_frame_no = -1
    if log_signal:
        log_signal.emit(f"[666] UDP 수신 시작 (포트 {UDP_PORT}). 스트림 들어오면 영상 표시.")
    while True:
        try:
            data, addr = sock.recvfrom(2048)
            if len(data) < 5:
                continue
            f_no = data[0]
            p_no = data[1]
            is_last = data[2]
            received_checksum = data[3]
            chunk = data[4:]
            if f_no < last_frame_no and (last_frame_no - f_no) < 200:
                continue
            if f_no not in frames:
                if len(frames) > 3:
                    del frames[min(frames.keys())]
                frames[f_no] = {'chunks': {}, 'target_checksum': None}
            frames[f_no]['chunks'][p_no] = chunk
            if is_last == 1:
                frames[f_no]['target_checksum'] = received_checksum
            target = frames[f_no].get('target_checksum')
            if target is not None:
                indices = sorted(frames[f_no]['chunks'].keys())
                if len(indices) > 0 and indices[0] == 0 and indices[-1] == p_no and len(indices) == p_no + 1:
                    full_data = b"".join([frames[f_no]['chunks'][i] for i in indices])
                    calculated_checksum = sum(full_data) % 256
                    if calculated_checksum == target:
                        nparr = np.frombuffer(full_data, dtype=np.uint8)
                        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        if img is not None:
                            if frame_queue.full():
                                frame_queue.get()
                            frame_queue.put((f_no, img.copy()))
                            last_frame_no = f_no
                    frames = {k: v for k, v in frames.items() if k > f_no}
        except Exception as e:
            if log_signal:
                log_signal.emit(f"UDP 수신 오류: {e}")


class CamApp666(QWidget):
    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._last_frame = None
        os.makedirs(IMG_DIR, exist_ok=True)
        self.setWindowTitle("ESP32-CAM LPR 666 — UDP 영상")
        layout = QVBoxLayout()
        layout.addWidget(QLabel("UDP 스트림 수신 시 영상 표시 (REST 없음)"))
        self.video_label = QLabel()
        self.video_label.setMinimumSize(320, 240)
        self.video_label.setStyleSheet("background-color: #333; color: #888;")
        self.video_label.setText("UDP 대기 중... (ESP32 LPR 666 기동 후 자동 전송)")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.video_label)
        self.log_label = QLabel("상태: UDP 수신 대기")
        layout.addWidget(self.log_label)
        self.setLayout(layout)
        self.resize(400, 320)
        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._update_video_frame)
        self._frame_timer.start(40)
        self.log_signal.connect(self._on_log)
        threading.Thread(target=udp_receiver_thread, args=(self.log_signal,), daemon=True).start()

    def _on_log(self, msg):
        self.log_label.setText(msg)

    def _update_video_frame(self):
        if frame_queue.empty():
            return
        try:
            f_no, img = frame_queue.get_nowait()
        except Exception:
            return
        if img is None:
            return
        img = cv2.rotate(img, cv2.ROTATE_180)
        img = cv2.flip(img, 1)
        img = np.ascontiguousarray(img)
        h, w, ch = img.shape
        bytes_per_line = ch * w
        qimg = QImage(img.data, w, h, bytes_per_line, QImage.Format.Format_BGR888).copy()
        self.video_label.setPixmap(
            QPixmap.fromImage(qimg).scaled(
                self.video_label.width(), self.video_label.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.video_label.setText("")
        self._last_frame = img.copy()
        self.log_label.setText(f"수신 중 (프레임 {f_no})")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    ex = CamApp666()
    ex.show()
    sys.exit(app.exec())
