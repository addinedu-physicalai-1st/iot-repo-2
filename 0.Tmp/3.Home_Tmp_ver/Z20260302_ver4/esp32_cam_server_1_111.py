# ESP32-CAM 전용 서버 (파이썬 서버 + 아두이노 클라이언트)
# TCP 8081: 캠 클라이언트 접속, keep_alive(PING/PONG), 장비 리스트 수신
# GUI: 캠 영상 전송 / 캠 영상 전송 중지 버튼 → 명령 전송 시 클라이언트가 UDP 7070으로 송출
# UDP 7070: 영상 수신 후 화면 표시

import sys
import socket
import struct
import threading
import time
from queue import Queue

import numpy as np
import cv2
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QTextEdit
from PyQt6.QtCore import pyqtSignal, QObject, QTimer, Qt
from PyQt6.QtGui import QImage, QPixmap

# 33바이트: type(1) + payload(32)
STRUCT_FORMAT = "<B 32s"
SIZE = struct.calcsize(STRUCT_FORMAT)

TYPE_PING = 0xFE
TYPE_PONG = 0xFD
TYPE_DEVICE_LIST = 4
TYPE_CMD_CAM_START = 6
TYPE_CMD_CAM_STOP = 7

TCP_PORT = 8081
UDP_PORT = 7070
KEEPALIVE_TIMEOUT_SEC = 12
RECV_CHECK_INTERVAL_SEC = 2

frame_queue = Queue(maxsize=3)


class CamServerWorker(QObject):
    log_signal = pyqtSignal(str)
    device_list_signal = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.client = None
        self._device_list_buf = {}

    def start(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('0.0.0.0', TCP_PORT))
        server.listen(5)
        threading.Thread(target=self._udp_receiver, daemon=True).start()
        while True:
            conn, addr = server.accept()
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.client = conn
            self.log_signal.emit(f"✅ 캠 클라이언트 연결 ({addr[0]}:{addr[1]})")
            threading.Thread(target=self._handle, args=(conn, addr), daemon=True).start()

    def _udp_receiver(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        sock.bind(('0.0.0.0', UDP_PORT))
        frames = {}
        last_frame_no = -1
        while True:
            try:
                data, addr = sock.recvfrom(2048)
                if len(data) < 5:
                    continue
                f_no, p_no, is_last = data[0], data[1], data[2]
                received_checksum = data[3]
                chunk = data[4:]
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
                                while frame_queue.full():
                                    try:
                                        frame_queue.get_nowait()
                                    except Exception:
                                        break
                                frame_queue.put((f_no, img.copy()))
                                last_frame_no = f_no
                        frames = {k: v for k, v in frames.items() if k > f_no}
            except Exception:
                pass

    def _handle(self, conn, addr):
        conn.settimeout(RECV_CHECK_INTERVAL_SEC)
        last_activity = time.monotonic()
        try:
            while True:
                try:
                    data = conn.recv(SIZE)
                except socket.timeout:
                    if time.monotonic() - last_activity > KEEPALIVE_TIMEOUT_SEC:
                        break
                    continue
                if not data:
                    break
                last_activity = time.monotonic()
                typ = data[0]
                payload = data[1:33]
                if typ == TYPE_PING:
                    conn.send(struct.pack(STRUCT_FORMAT, TYPE_PONG, b"\x00" * 32))
                    continue
                if typ == TYPE_DEVICE_LIST:
                    idx, total = payload[0], payload[1]
                    guid = payload[2:18].decode('utf-8', errors='ignore').strip('\x00 ')
                    name = payload[18:32].decode('utf-8', errors='ignore').strip('\x00 ')
                    self._device_list_buf[idx] = {"guid": guid, "name": name}
                    if len(self._device_list_buf) >= total:
                        lst = [self._device_list_buf[i] for i in range(total)]
                        self._device_list_buf.clear()
                        self.device_list_signal.emit(lst)
                    continue
        finally:
            if self.client is conn:
                self.client = None
                self._device_list_buf.clear()
                self.log_signal.emit(f"❌ 캠 클라이언트 연결 끊김 ({addr[0]}:{addr[1]})")
            try:
                conn.close()
            except Exception:
                pass

    def send_cam_start(self):
        if self.client:
            self.client.send(struct.pack(STRUCT_FORMAT, TYPE_CMD_CAM_START, b"\x00" * 32))
            self.log_signal.emit("📡 [명령] 캠 영상 전송 시작 → ESP32-CAM UDP 송출")

    def send_cam_stop(self):
        if self.client:
            self.client.send(struct.pack(STRUCT_FORMAT, TYPE_CMD_CAM_STOP, b"\x00" * 32))
            self.log_signal.emit("📡 [명령] 캠 영상 전송 중지")


class CamApp(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = CamServerWorker()
        self.worker.log_signal.connect(self.log_append)
        self.worker.device_list_signal.connect(self.on_device_list)
        threading.Thread(target=self.worker.start, daemon=True).start()
        self.initUI()
        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._update_video_frame)
        self._frame_timer.start(40)

    def initUI(self):
        layout = QVBoxLayout()
        layout.addWidget(QLabel("ESP32-CAM 서버 (TCP 8081, UDP 7070)"))
        btn_layout = QHBoxLayout()
        self.btn_cam_start = QPushButton("캠 영상 전송")
        self.btn_cam_stop = QPushButton("캠 영상 전송 중지")
        btn_layout.addWidget(self.btn_cam_start)
        btn_layout.addWidget(self.btn_cam_stop)
        layout.addLayout(btn_layout)
        layout.addWidget(QLabel("캠 장비 목록 (연결 시 수신):"))
        self.device_list_widget = QListWidget()
        self.device_list_widget.setMaximumHeight(60)
        layout.addWidget(self.device_list_widget)
        layout.addWidget(QLabel("캠 영상 (UDP 수신):"))
        self.video_label = QLabel()
        self.video_label.setMinimumSize(320, 240)
        self.video_label.setStyleSheet("background-color: #333; color: #888;")
        self.video_label.setText("영상 대기 중...")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.video_label)
        layout.addWidget(QLabel("로그:"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)
        self.setLayout(layout)
        self.btn_cam_start.clicked.connect(self.worker.send_cam_start)
        self.btn_cam_stop.clicked.connect(self.worker.send_cam_stop)
        self.setWindowTitle("ESP32-CAM 서버 (111)")
        self.resize(480, 640)

    def on_device_list(self, lst):
        self.device_list_widget.clear()
        for item in lst:
            guid = item.get("guid", "").strip()
            name = item.get("name", "").strip()
            self.device_list_widget.addItem(f"✓ {guid}  →  {name}")
        self.log_append("📋 캠 장비 목록 수신.")

    def _update_video_frame(self):
        if frame_queue.empty():
            return
        try:
            f_no, img = frame_queue.get_nowait()
        except Exception:
            return
        if img is None:
            return
        h, w, ch = img.shape
        bytes_per_line = ch * w
        qimg = QImage(img.data, w, h, bytes_per_line, QImage.Format.Format_BGR888)
        self.video_label.setPixmap(
            QPixmap.fromImage(qimg).scaled(
                self.video_label.width(), self.video_label.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.video_label.setText("")

    def log_append(self, line):
        self.log.append(line)
        self.log.moveCursor(self.log.textCursor().MoveOperation.End)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    ex = CamApp()
    ex.show()
    sys.exit(app.exec())
