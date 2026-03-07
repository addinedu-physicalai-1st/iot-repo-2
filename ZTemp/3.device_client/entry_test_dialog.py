from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QLineEdit,
    QListWidget,
)

from device_manager import DeviceManager


class EntryTestDialog(QDialog):
    """
    ESP32 입차 차단기 테스트용 팝업. (보드 1)

    - 게이트 열기/닫기 및 카드 SiteID 쓰기 명령
    - 센서/이벤트 로그 및 장비 목록 표시
    """

    def __init__(self, device_manager: DeviceManager, device_guid: str = "DEV-GATE-1", parent=None) -> None:
        super().__init__(parent)
        self._dev_mgr = device_manager
        self._device_guid = device_guid
        self._last_log_count = 0

        self.setWindowTitle("입차 차단기 테스트 (ESP32 보드1)") 
        self.resize(600, 650)

        layout = QVBoxLayout()

        # ───────── 1. SiteID 및 카드 쓰기 ─────────
        layout.addWidget(QLabel("카드에 기록할 SiteID:"))
        self.edit_siteid = QLineEdit("APT_SEOUL_01")
        layout.addWidget(self.edit_siteid)

        # ───────── 2. 게이트 및 LCD 제어 버튼 ─────────
        btn_row = QHBoxLayout()
        self.btn_open = QPushButton("게이트 열기")
        self.btn_close = QPushButton("게이트 닫기")
        self.btn_write = QPushButton("SiteID 카드 쓰기")
        btn_row.addWidget(self.btn_open)
        btn_row.addWidget(self.btn_close)
        btn_row.addWidget(self.btn_write)
        layout.addLayout(btn_row)


        # ───────── 4. 장비 목록 ─────────
        layout.addWidget(QLabel("ESP32 장치 구성 (GUID → 연결 모듈):"))
        self.list_devices = QListWidget()
        self.list_devices.setMaximumHeight(120)
        layout.addWidget(self.list_devices)

        # ───────── 5. 로그 ─────────
        layout.addWidget(QLabel("게이트 / 센서 / RFID 로그:"))
        self.text_log = QTextEdit()
        self.text_log.setReadOnly(True)
        layout.addWidget(self.text_log, 1)

        self.setLayout(layout)

        # 버튼 핸들러
        self.btn_open.clicked.connect(self._on_open_clicked)
        self.btn_close.clicked.connect(self._on_close_clicked)
        self.btn_write.clicked.connect(self._on_write_clicked)

        # 주기적으로 로그/장비 갱신
        self._timer = QTimer(self)
        self._timer.setInterval(800)
        self._timer.timeout.connect(self._refresh_from_device_manager)
        self._timer.start()

        self._refresh_from_device_manager()

    def _on_open_clicked(self) -> None:
        self._dev_mgr.open_gate(guid=self._device_guid)

    def _on_close_clicked(self) -> None:
        self._dev_mgr.close_gate(guid=self._device_guid)

    def _on_write_clicked(self) -> None:
        site_id = self.edit_siteid.text().strip() or "APT_SEOUL_01"
        self._dev_mgr.write_siteid(site_id, guid=self._device_guid)


    def _refresh_from_device_manager(self) -> None:
        # 로그 갱신
        logs = self._dev_mgr.get_gate_logs(guid=self._device_guid)
        if len(logs) != self._last_log_count:
            self.text_log.clear()
            self.text_log.append("\n".join(logs))
            self.text_log.moveCursor(self.text_log.textCursor().MoveOperation.End)
            self._last_log_count = len(logs)

        # 장비 목록 갱신
        devices = self._dev_mgr.get_gate_devices(guid=self._device_guid)
        current_items = [self.list_devices.item(i).text() for i in range(self.list_devices.count())]
        new_items = []
        for d in devices:
            guid = str(d.get("guid", "")).strip()
            name = str(d.get("name", "")).strip()
            new_items.append(f"{guid} → {name}")
        
        if current_items != new_items:
            self.list_devices.clear()
            self.list_devices.addItems(new_items)
