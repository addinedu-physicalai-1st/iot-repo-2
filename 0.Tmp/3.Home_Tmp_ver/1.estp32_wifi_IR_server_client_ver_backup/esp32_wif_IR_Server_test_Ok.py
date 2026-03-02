# ESP32 IR/조도/RFID/게이트 테스트 서버
# 클라이언트에서 ENTRY/EXIT/RFID/GATE_OPEN/GATE_CLOSED 이벤트 수신·표시, 게이트 열기 테스트 명령 전송

import sys, socket, struct, threading, time
from PyQt6.QtWidgets import *
from PyQt6.QtCore import pyqtSignal, QObject

# 33바이트: mode(B), event_type(B), source(16s), extra(15s)
# mode 0=이벤트, 2=게이트열기(서버→클라이언트), 0xFE=PING, 0xFD=PONG
STRUCT_FORMAT = "<B B 16s 15s"
SIZE = struct.calcsize(STRUCT_FORMAT)
MODE_PING = 0xFE
MODE_PONG = 0xFD
MODE_EVENT = 0
MODE_CMD_OPEN = 2

EV_ENTRY, EV_EXIT, EV_RFID, EV_GATE_OPEN, EV_GATE_CLOSED = 1, 2, 3, 4, 5
EVENT_NAMES = {EV_ENTRY: "ENTRY_DETECTED", EV_EXIT: "EXIT_DETECTED", EV_RFID: "RFID_ALLOWED",
               EV_GATE_OPEN: "GATE_OPEN", EV_GATE_CLOSED: "GATE_CLOSED"}

KEEPALIVE_TIMEOUT_SEC = 12
RECV_CHECK_INTERVAL_SEC = 2


class ServerWorker(QObject):
    data_signal = pyqtSignal(str)

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
                unpacked = struct.unpack(STRUCT_FORMAT, data)
                mode = unpacked[0]
                if mode == MODE_PING:
                    conn.send(struct.pack(STRUCT_FORMAT, MODE_PONG, 0, b"", b""))
                    continue
                if mode != MODE_EVENT:
                    continue
                event_type = unpacked[1]
                source = unpacked[2].decode('utf-8', errors='ignore').strip('\x00')
                extra = unpacked[3].decode('utf-8', errors='ignore').strip('\x00')
                name = EVENT_NAMES.get(event_type, f"EVENT_{event_type}")
                line = f"[{name}] source={source}"
                if extra:
                    line += f" | {extra}"
                self.data_signal.emit(line)
        finally:
            if self.client is conn:
                self.client = None
            try:
                conn.close()
            except Exception:
                pass

    def send_open_gate(self):
        if self.client:
            packet = struct.pack(STRUCT_FORMAT, MODE_CMD_OPEN, 0, b"", b"")
            self.client.send(packet)


class IRGateApp(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = ServerWorker()
        self.worker.data_signal.connect(self.log_line)
        threading.Thread(target=self.worker.start, daemon=True).start()
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        self.btn_open = QPushButton("게이트 열기 (테스트)")
        self.log = QTextEdit()
        layout.addWidget(QLabel("ESP32 IR/조도/RFID·게이트 테스트 서버"))
        layout.addWidget(self.btn_open)
        layout.addWidget(QLabel("이벤트 로그:"))
        layout.addWidget(self.log)
        self.setLayout(layout)
        self.btn_open.clicked.connect(self.worker.send_open_gate)
        self.setWindowTitle("IR/게이트 테스트 서버")

    def log_line(self, line):
        self.log.append(line)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ex = IRGateApp()
    ex.show()
    sys.exit(app.exec())
