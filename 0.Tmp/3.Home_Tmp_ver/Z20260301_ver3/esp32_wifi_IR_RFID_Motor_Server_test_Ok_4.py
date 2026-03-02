# ESP32 IR + RFID + 모터 + 캠 통합 서버
# TCP 8080: 제어(444), TCP 8081: 캠(111). GUI에서 캠 영상 전송/중지 버튼 → UDP 7070 수신 영상 표시

import sys, socket, struct, threading, time
from queue import Queue
import numpy as np
import cv2
from PyQt6.QtWidgets import *
from PyQt6.QtCore import pyqtSignal, QObject, QTimer, Qt
from PyQt6.QtGui import QImage, QPixmap

# 33바이트: type(1) + payload(32)
# type: 0xFE PING, 0xFD PONG, 0 IR이벤트, 1 RFID, 2 게이트열기, 5 게이트닫기, 3 SiteID쓰기, 4 장비목록, 6 CAM시작, 7 CAM중지
STRUCT_FORMAT = "<B 32s"
SIZE = struct.calcsize(STRUCT_FORMAT)

TYPE_PING = 0xFE
TYPE_PONG = 0xFD
TYPE_IR_EVENT = 0
TYPE_RFID = 1
TYPE_CMD_OPEN = 2
TYPE_CMD_CLOSE = 5
TYPE_CMD_WRITE = 3
TYPE_DEVICE_LIST = 4
TYPE_CMD_CAM_START = 6
TYPE_CMD_CAM_STOP = 7

TCP_PORT_CONTROL = 8080
TCP_PORT_CAM = 8081
UDP_PORT_VIDEO = 7070

# 이벤트 정의 (99번 에러 추가)
EV_NAMES = {
    1: "ENTRY_DETECTED", 
    2: "EXIT_DETECTED", 
    3: "RFID", 
    4: "GATE_OPEN", 
    5: "GATE_CLOSED",
    99: "!!! H/W SENSOR ERROR !!!" # ESP32 초기화 실패 시
}

KEEPALIVE_TIMEOUT_SEC = 12
RECV_CHECK_INTERVAL_SEC = 2

USER_DB = {
    "A1B2C3D4": {"name": "홍길동", "car": "123가4567", "phone": "010-1111-2222"},
    "E5F6G7H8": {"name": "김철수", "car": "98나7654", "phone": "010-3333-4444"},
    "0726d306": {"name": "이영희", "car": "12345678", "phone": "010-5555-6666"},
}

# ESP32 센서 목록 (DB 연동 시 채울 예정). GUID → 영문명.
SENSOR_LIST = {
    "ESP32-S1-ENTRY01": "EntryVehDetect",
    "ESP32-S2-EXIT01": "ExitVehDetect",
    "ESP32-RFID-01": "RFIDReader",
    "ESP32-GATE-01": "GateServo",
    "ESP32-CAM-01": "CamStream",
}

# UDP 수신 프레임 큐 (캠 영상 표시용)
frame_queue = Queue(maxsize=3)

class ServerWorker(QObject):
    log_signal = pyqtSignal(str)
    device_list_signal = pyqtSignal(list)   # 8080 제어 장비
    cam_device_list_signal = pyqtSignal(list)  # 8081 캠 장비

    def __init__(self):
        super().__init__()
        self.client = None
        self.cam_client = None
        self._device_list_buf = {}
        self._cam_device_list_buf = {}

    def start(self):
        # TCP 8080: 제어 클라이언트(444)
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('0.0.0.0', TCP_PORT_CONTROL))
        server.listen(5)
        threading.Thread(target=self._accept_loop, args=(server, "control"), daemon=True).start()
        # TCP 8081: 캠 클라이언트(111)
        cam_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cam_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        cam_server.bind(('0.0.0.0', TCP_PORT_CAM))
        cam_server.listen(5)
        threading.Thread(target=self._accept_loop, args=(cam_server, "cam"), daemon=True).start()
        # UDP 7070 수신 스레드
        threading.Thread(target=self._udp_receiver, daemon=True).start()

    def _accept_loop(self, sock, kind):
        while True:
            conn, addr = sock.accept()
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            if kind == "control":
                self.client = conn
                self.log_signal.emit(f"✅ 제어 클라이언트 연결 ({addr[0]}:{addr[1]})")
                threading.Thread(target=self.handle, args=(conn, addr, "control"), daemon=True).start()
            else:
                self.cam_client = conn
                self.log_signal.emit(f"✅ 캠 클라이언트 연결 ({addr[0]}:{addr[1]})")
                threading.Thread(target=self.handle, args=(conn, addr, "cam"), daemon=True).start()

    def _udp_receiver(self):
        """UDP 7070에서 캠 패킷 수신 → 프레임 조립 → frame_queue에 넣기"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        sock.bind(('0.0.0.0', UDP_PORT_VIDEO))
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
            except Exception as e:
                pass

    def handle(self, conn, addr, kind="control"):
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
                
                if kind == "cam":
                    if typ == TYPE_DEVICE_LIST:
                        idx, total = payload[0], payload[1]
                        guid = payload[2:18].decode('utf-8', errors='ignore').strip('\x00 ')
                        name = payload[18:32].decode('utf-8', errors='ignore').strip('\x00 ')
                        self._cam_device_list_buf[idx] = {"guid": guid, "name": name}
                        if len(self._cam_device_list_buf) >= total:
                            lst = [self._cam_device_list_buf[i] for i in range(total)]
                            self._cam_device_list_buf.clear()
                            self.cam_device_list_signal.emit(lst)
                    continue
                
                # 제어(444) 전용: IR, RFID, 장비목록
                if typ == TYPE_IR_EVENT:
                    ev = payload[0]
                    src = payload[1:17].decode('utf-8', errors='ignore').strip('\x00')
                    ext = payload[17:32].decode('utf-8', errors='ignore').strip('\x00')
                    
                    if ev == 99: # 하드웨어 초기화 에러 발생 시
                        line = f"❌ [ERROR] {src} 초기화 실패! ({ext})"
                    else:
                        name = EV_NAMES.get(ev, f"EV_{ev}")
                        line = f"[EVENT] {name} | {src}" + (f" | {ext}" if ext else "")
                    
                    self.log_signal.emit(line)
                    continue
                
                # 3. RFID 데이터 처리
                if typ == TYPE_RFID:
                    mode = payload[0]
                    uid = payload[1:17].decode('utf-8', errors='ignore').strip('\x00')
                    siteid = payload[17:32].decode('utf-8', errors='ignore').strip('\x00')
                    
                    self.log_signal.emit(f"\n[RFID] UID: {uid} | SiteID: {siteid}")
                    user = next((v for k, v in USER_DB.items() if k.upper() == uid.upper()), None)
                    if user:
                        self.log_signal.emit(f"  ▶ 사용자: {user['name']} | 차량: {user['car']} | {user['phone']}")
                    else:
                        self.log_signal.emit("  ▶ 경고: 등록되지 않은 카드입니다.")
                    continue

                # 4. 장비 목록 수신 (ESP32 접속 시 GUID + 센서명)
                if typ == TYPE_DEVICE_LIST:
                    idx = payload[0]
                    total = payload[1]
                    guid = payload[2:18].decode('utf-8', errors='ignore').strip('\x00 ')
                    name = payload[18:32].decode('utf-8', errors='ignore').strip('\x00 ')
                    self._device_list_buf[idx] = {"guid": guid, "name": name}
                    if len(self._device_list_buf) >= total:
                        lst = [self._device_list_buf[i] for i in range(total)]
                        self._device_list_buf.clear()
                        self.device_list_signal.emit(lst)
                    continue
                    
        finally:
            if kind == "cam" and self.cam_client is conn:
                self.cam_client = None
                self._cam_device_list_buf.clear()
                self.log_signal.emit(f"❌ 캠 클라이언트 연결 끊김 ({addr[0]}:{addr[1]})")
            elif kind == "control" and self.client is conn:
                self.client = None
                self._device_list_buf.clear()
                self.log_signal.emit(f"❌ 제어 클라이언트 연결 끊김 ({addr[0]}:{addr[1]})")
            try:
                conn.close()
            except Exception:
                pass

    def send_cam_start(self):
        """캠 영상 전송 시작: ESP32-CAM이 UDP로 서버에 영상 송출 시작."""
        if self.cam_client:
            self.cam_client.send(struct.pack(STRUCT_FORMAT, TYPE_CMD_CAM_START, b"\x00" * 32))
            self.log_signal.emit("📡 [명령] 캠 영상 전송 시작 → ESP32-CAM UDP 송출")

    def send_cam_stop(self):
        """캠 영상 전송 중지."""
        if self.cam_client:
            self.cam_client.send(struct.pack(STRUCT_FORMAT, TYPE_CMD_CAM_STOP, b"\x00" * 32))
            self.log_signal.emit("📡 [명령] 캠 영상 전송 중지 → ESP32-CAM")

    def send_open_gate(self):
        """게이트 열기: ESP32가 이 명령을 받으면 서보를 열린 상태(90°)로 둠."""
        if self.client:
            self.client.send(struct.pack(STRUCT_FORMAT, TYPE_CMD_OPEN, b"\x00" * 32))
            self.log_signal.emit("📡 [명령] 게이트 열기 전송 → ESP32 반영")

    def send_close_gate(self):
        """게이트 닫기: ESP32가 이 명령을 받으면 서보를 닫힌 상태(0°)로 둠."""
        if self.client:
            self.client.send(struct.pack(STRUCT_FORMAT, TYPE_CMD_CLOSE, b"\x00" * 32))
            self.log_signal.emit("📡 [명령] 게이트 닫기 전송 → ESP32 반영")

    def send_write_siteid(self, site_id):
        if self.client:
            # 첫 바이트는 예비용(0), 이후 16바이트 SiteID, 나머지 패딩
            payload = b"\x00" + site_id.encode().ljust(16, b'\x00')[:16] + b"\x00" * 15
            self.client.send(struct.pack(STRUCT_FORMAT, TYPE_CMD_WRITE, payload))

class IntegratedApp(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = ServerWorker()
        self.worker.log_signal.connect(self.log_append)
        self.worker.device_list_signal.connect(self.on_device_list)
        self.worker.cam_device_list_signal.connect(self.on_cam_device_list)
        threading.Thread(target=self.worker.start, daemon=True).start()
        self.initUI()
        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._update_video_frame)
        self._frame_timer.start(40)  # ~25 FPS 갱신

    def initUI(self):
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Parking Management System v2.0 (제어 + 캠)"))
        
        self.site_input = QLineEdit("APT_SEOUL_01")
        layout.addWidget(QLabel("카드에 기록할 SiteID:"))
        layout.addWidget(self.site_input)
        
        btn_layout = QHBoxLayout()
        self.btn_open = QPushButton("게이트 열기")
        self.btn_close = QPushButton("게이트 닫기")
        self.btn_write = QPushButton("현재 SiteID 카드로 전송")
        btn_layout.addWidget(self.btn_open)
        btn_layout.addWidget(self.btn_close)
        btn_layout.addWidget(self.btn_write)
        layout.addLayout(btn_layout)
        
        # 캠 영상 전송 버튼 (서버 명령 → ESP32-CAM이 UDP로 송출)
        cam_btn_layout = QHBoxLayout()
        self.btn_cam_start = QPushButton("캠 영상 전송")
        self.btn_cam_stop = QPushButton("캠 영상 전송 중지")
        cam_btn_layout.addWidget(self.btn_cam_start)
        cam_btn_layout.addWidget(self.btn_cam_stop)
        layout.addLayout(cam_btn_layout)
        
        layout.addWidget(QLabel("ESP32 제어 장비 (연결 시 수신):"))
        self.sensor_list_widget = QListWidget()
        self.sensor_list_widget.setMaximumHeight(80)
        layout.addWidget(self.sensor_list_widget)
        
        layout.addWidget(QLabel("ESP32 캠 장비 (연결 시 수신):"))
        self.cam_list_widget = QListWidget()
        self.cam_list_widget.setMaximumHeight(50)
        layout.addWidget(self.cam_list_widget)
        
        layout.addWidget(QLabel("캠 영상 (UDP 수신):"))
        self.video_label = QLabel()
        self.video_label.setMinimumSize(320, 240)
        self.video_label.setStyleSheet("background-color: #333; color: #888;")
        self.video_label.setText("영상 대기 중...")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.video_label)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(QLabel("시스템 로그:"))
        layout.addWidget(self.log)
        
        self.setLayout(layout)
        
        self.btn_open.clicked.connect(self.worker.send_open_gate)
        self.btn_close.clicked.connect(self.worker.send_close_gate)
        self.btn_write.clicked.connect(self.on_write_clicked)
        self.btn_cam_start.clicked.connect(self.worker.send_cam_start)
        self.btn_cam_stop.clicked.connect(self.worker.send_cam_stop)
        
        self.setWindowTitle("통합 주차 서버 (제어 8080 + 캠 8081)")
        self.resize(520, 720)

    def on_write_clicked(self):
        sid = self.site_input.text()
        self.worker.send_write_siteid(sid)
        self.log_append(f"📡 [명령] 카드 쓰기 대기 모드 전환 (SiteID: {sid})")

    def on_device_list(self, lst):
        """제어(444) 장비 목록."""
        self.sensor_list_widget.clear()
        for item in lst:
            guid = item.get("guid", "").strip()
            name = item.get("name", "").strip()
            expected = SENSOR_LIST.get(guid) or SENSOR_LIST.get(guid.replace(" ", ""))
            if expected and expected == name:
                self.sensor_list_widget.addItem(f"✓ {guid}  →  {name}")
            else:
                self.sensor_list_widget.addItem(f"  {guid}  →  {name}")
        self.log_append("📋 제어 장비 목록 수신.")

    def on_cam_device_list(self, lst):
        """캠(111) 장비 목록."""
        self.cam_list_widget.clear()
        for item in lst:
            guid = item.get("guid", "").strip()
            name = item.get("name", "").strip()
            self.cam_list_widget.addItem(f"✓ {guid}  →  {name}")
        self.log_append("📋 캠 장비 목록 수신.")

    def _update_video_frame(self):
        """UDP 수신 프레임을 비디오 라벨에 표시."""
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
        self.video_label.setPixmap(QPixmap.fromImage(qimg).scaled(
            self.video_label.width(), self.video_label.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        self.video_label.setText("")

    def log_append(self, line):
        self.log.append(line)
        # 자동 스크롤
        self.log.moveCursor(self.log.textCursor().MoveOperation.End)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # 스타일 살짝 가미
    app.setStyle('Fusion') 
    ex = IntegratedApp()
    ex.show()
    sys.exit(app.exec())