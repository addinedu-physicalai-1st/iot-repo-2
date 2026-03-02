import sys, socket, struct, threading, time
from PyQt6.QtWidgets import *
from PyQt6.QtCore import pyqtSignal, QObject

# Mode(B), UID(16s), SiteID(16s) = 총 33바이트
# mode 0xFE: Keep-alive PING(클라이언트→서버), 0xFD: PONG(서버→클라이언트)
STRUCT_FORMAT = "<B16s16s"
SIZE = struct.calcsize(STRUCT_FORMAT)
MODE_PING = 0xFE
MODE_PONG = 0xFD

# 서버 keep-alive: 이 시간(초) 동안 클라이언트에서 PING/데이터가 없으면 소켓 종료 (클라이언트 PING 주기 5초의 2배 이상 권장)
KEEPALIVE_TIMEOUT_SEC = 12
RECV_CHECK_INTERVAL_SEC = 2  # recv 타임아웃(주기적으로 타임아웃 체크용)

# 가상의 데이터베이스 (실제로는 DB 연결)
USER_DB = {
    "A1B2C3D4": {"name": "홍길동", "car": "123가4567", "phone": "010-1111-2222"},
    "E5F6G7H8": {"name": "김철수", "car": "98나7654", "phone": "010-3333-4444"},
    "0726d306": {"name": "이영희", "car": "12345678", "phone": "010-5555-6666"}
}

class ServerWorker(QObject):
    data_signal = pyqtSignal(tuple)
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
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # PONG 즉시 전송(버퍼링 없음)
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
                unpacked = struct.unpack(STRUCT_FORMAT, data)
                mode = unpacked[0]
                if mode == MODE_PING:
                    conn.send(struct.pack(STRUCT_FORMAT, MODE_PONG, b"", b""))
                    continue
                decoded = [x.decode('utf-8', errors='ignore').strip('\x00') if isinstance(x, bytes) else x for x in unpacked]
                self.data_signal.emit(tuple(decoded))
        finally:
            if self.client is conn:
                self.client = None
            try:
                conn.close()
            except Exception:
                pass

    def send_command(self, site_id):
        if self.client:
            packet = struct.pack(STRUCT_FORMAT, 2, b"", site_id.encode())
            self.client.send(packet)

class ParkingApp(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = ServerWorker()
        self.worker.data_signal.connect(self.display_info)
        threading.Thread(target=self.worker.start, daemon=True).start()
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        self.site_input = QLineEdit("APT_SEOUL_01")
        self.btn_write = QPushButton("주차장 유일값 카드에 쓰기 설정")
        self.log = QTextEdit()
        
        layout.addWidget(QLabel("설정할 주차장 유일ID (SiteID):"))
        layout.addWidget(self.site_input)
        layout.addWidget(self.btn_write)
        layout.addWidget(QLabel("조회 로그:"))
        layout.addWidget(self.log)
        
        self.setLayout(layout)
        self.btn_write.clicked.connect(lambda: self.worker.send_command(self.site_input.text()))
        self.setWindowTitle("주차 관리 서버 (UID 매핑 방식)")

    def display_info(self, data):
        mode, uid, site_id = data
        self.log.append(f"\n[카드 태그됨]")
        self.log.append(f"UID: {uid}")
        self.log.append(f"카드 내 저장된 SiteID: {site_id}")
        
        # 서버 DB에서 UID로 조회 (대소문자 구분 없음)
        user = next((v for k, v in USER_DB.items() if k.upper() == uid.upper()), None)
        if user:
            self.log.append(f"▶ 매칭 정보: {user['name']} | {user['car']} | {user['phone']}")
        else:
            self.log.append("▶ 미등록 카드입니다.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    ex = ParkingApp()
    ex.show()
    sys.exit(app.exec())