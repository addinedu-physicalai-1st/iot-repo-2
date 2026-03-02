import sys, socket, struct, threading, time
from PyQt6.QtWidgets import *
from PyQt6.QtCore import pyqtSignal, QObject

STRUCT_FORMAT = "<B 32s"
SIZE = struct.calcsize(STRUCT_FORMAT)
TYPE_PING, TYPE_PONG, TYPE_IR_EVENT, TYPE_RFID, TYPE_CMD_OPEN, TYPE_CMD_WRITE = 0xFE, 0xFD, 0, 1, 2, 3

class ClientWorker(QObject):
    log_signal = pyqtSignal(str)
    con_signal = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.sock = None
        self.running = False

    def connect_to_esp(self, ip):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((ip, 8080))
            self.running = True
            self.con_signal.emit(True)
            threading.Thread(target=self.receive_loop, daemon=True).start()
            return True
        except Exception as e:
            self.log_signal.emit(f"❌ 연결 실패: {e}")
            return False

    def receive_loop(self):
        while self.running:
            try:
                data = self.sock.recv(SIZE)
                if not data: break
                typ = data[0]
                payload = data[1:33]

                if typ == TYPE_IR_EVENT:
                    ev = payload[0]
                    src = payload[1:17].decode('utf-8', errors='ignore').strip('\x00')
                    self.log_signal.emit(f"🔔 [이벤트] {src} 감지 (Code: {ev})")
                elif typ == TYPE_RFID:
                    uid = payload[1:17].decode('utf-8', errors='ignore').strip('\x00')
                    self.log_signal.emit(f"💳 [RFID] UID: {uid}")
            except: break
        self.running = False
        self.con_signal.emit(False)

    def send_cmd(self, typ, payload_data=b""):
        if self.sock and self.running:
            packet = struct.pack(STRUCT_FORMAT, typ, payload_data.ljust(32, b'\x00'))
            self.sock.send(packet)

class IntegratedApp(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = ClientWorker()
        self.worker.log_signal.connect(lambda s: self.log.append(s))
        self.worker.con_signal.connect(self.update_status)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        self.ip_input = QLineEdit("192.168.25.XX") # 아두이노 IP 입력
        self.btn_conn = QPushButton("아두이노 접속")
        self.btn_open = QPushButton("게이트 열기 명령")
        self.log = QTextEdit()

        layout.addWidget(QLabel("아두이노(서버) IP:"))
        layout.addWidget(self.ip_input)
        layout.addWidget(self.btn_conn)
        layout.addWidget(self.btn_open)
        layout.addWidget(self.log)

        self.btn_conn.clicked.connect(lambda: self.worker.connect_to_esp(self.ip_input.text()))
        self.btn_open.clicked.connect(lambda: self.worker.send_cmd(TYPE_CMD_OPEN))
        
        self.setLayout(layout)
        self.setWindowTitle("Python Client - ESP32 Server")

    def update_status(self, connected):
        status = "연결됨" if connected else "연결 끊김"
        self.log.append(f"🌐 상태: {status}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    ex = IntegratedApp()
    ex.show()
    sys.exit(app.exec())