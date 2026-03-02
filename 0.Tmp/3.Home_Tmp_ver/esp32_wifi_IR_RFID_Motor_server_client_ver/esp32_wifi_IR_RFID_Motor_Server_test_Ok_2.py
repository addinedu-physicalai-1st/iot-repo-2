# ESP32 IR + RFID + 모터 통합 테스트 서버 (에러 리포팅 기능 추가)
# 조도/IR 이벤트·RFID(UID/SiteID) 수신 표시, 게이트 열기·카드 SiteID 쓰기 명령

import sys, socket, struct, threading, time
from PyQt6.QtWidgets import *
from PyQt6.QtCore import pyqtSignal, QObject

# 33바이트: type(1) + payload(32)
# type: 0xFE PING, 0xFD PONG, 0 IR이벤트, 1 RFID, 2 게이트열기(서버→클), 3 SiteID쓰기(서버→클)
STRUCT_FORMAT = "<B 32s"
SIZE = struct.calcsize(STRUCT_FORMAT)

TYPE_PING = 0xFE
TYPE_PONG = 0xFD
TYPE_IR_EVENT = 0
TYPE_RFID = 1
TYPE_CMD_OPEN = 2
TYPE_CMD_WRITE = 3

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

class ServerWorker(QObject):
    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.client = None

    def start(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('0.0.0.0', 8080))
        server.listen(5)
        while True:
            conn, _ = server.accept()
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.client = conn
            threading.Thread(target=self.handle, args=(conn,), daemon=True).start()

    def handle(self, conn):
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
                
                # 1. PING 처리
                if typ == TYPE_PING:
                    conn.send(struct.pack(STRUCT_FORMAT, TYPE_PONG, b"\x00" * 32))
                    continue
                
                # 2. IR 및 시스템 이벤트 처리
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
                    
        finally:
            if self.client is conn:
                self.client = None
            try:
                conn.close()
            except Exception:
                pass

    def send_open_gate(self):
        if self.client:
            self.client.send(struct.pack(STRUCT_FORMAT, TYPE_CMD_OPEN, b"\x00" * 32))

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
        threading.Thread(target=self.worker.start, daemon=True).start()
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Parking Management System v2.0"))
        
        # SiteID 입력부
        self.site_input = QLineEdit("APT_SEOUL_01")
        layout.addWidget(QLabel("카드에 기록할 SiteID:"))
        layout.addWidget(self.site_input)
        
        # 버튼부
        btn_layout = QHBoxLayout()
        self.btn_open = QPushButton("게이트 강제 열기")
        self.btn_write = QPushButton("현재 SiteID 카드로 전송")
        btn_layout.addWidget(self.btn_open)
        btn_layout.addWidget(self.btn_write)
        layout.addLayout(btn_layout)
        
        # 로그창
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(QLabel("시스템 로그:"))
        layout.addWidget(self.log)
        
        self.setLayout(layout)
        
        # 시그널 연결
        self.btn_open.clicked.connect(self.worker.send_open_gate)
        self.btn_write.clicked.connect(self.on_write_clicked)
        
        self.setWindowTitle("통합 주차 서버 (UID/SiteID 매핑)")
        self.resize(500, 600)

    def on_write_clicked(self):
        sid = self.site_input.text()
        self.worker.send_write_siteid(sid)
        self.log_append(f"📡 [명령] 카드 쓰기 대기 모드 전환 (SiteID: {sid})")

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