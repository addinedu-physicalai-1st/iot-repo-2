from __future__ import annotations

from typing import List

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


class ExitTestDialog(QDialog):
    """
    ESP32 출차 차단기 테스트용 팝업. (보드 2)

    - LCD 텍스트 전송 제어
    - 센서/이벤트 로그 및 장비 목록 표시
    """

    def __init__(self, device_manager: DeviceManager, device_guid: str = "DEV-GATE-2", parent=None) -> None:
        super().__init__(parent)
        self._dev_mgr = device_manager
        self._device_guid = device_guid
        self._last_log_count = 0

        self.setWindowTitle("출차 차단기 테스트 (ESP32 보드2)")
        self.resize(600, 600)

        layout = QVBoxLayout()

        # ───────── 1. LCD 전송 제어 ─────────
        layout.addWidget(QLabel("LCD 에 표시할 텍스트:"))
        lcd_row = QHBoxLayout()
        self.edit_lcd1 = QLineEdit("WELCOME")
        self.edit_lcd1.setPlaceholderText("Line 1 (Max 16)")
        self.edit_lcd2 = QLineEdit("GOODBYE")
        self.edit_lcd2.setPlaceholderText("Line 2 (Max 16)")
        lcd_row.addWidget(self.edit_lcd1)
        lcd_row.addWidget(self.edit_lcd2)
        layout.addLayout(lcd_row)

        self.btn_send_lcd = QPushButton("LCD 텍스트 전송")
        layout.addWidget(self.btn_send_lcd)

        layout.addWidget(QLabel("ESP32 장치 구성 (GUID → 연결 모듈):"))
        self.list_devices = QListWidget()
        self.list_devices.setMaximumHeight(140)
        layout.addWidget(self.list_devices)

        layout.addWidget(QLabel("게이트 / 센서 / RFID 로그:"))
        self.text_log = QTextEdit()
        self.text_log.setReadOnly(True)
        layout.addWidget(self.text_log, 1)

        self.setLayout(layout)
        # 버튼 핸들러
        self.btn_send_lcd.clicked.connect(self._on_send_lcd_clicked)

        # 주기적으로 DeviceManager 에서 로그/장비목록을 가져와 반영
        self._timer = QTimer(self)
        self._timer.setInterval(800)  # 0.8초마다 폴링
        self._timer.timeout.connect(self._refresh_from_device_manager)
        self._timer.start()

        # 최초 한 번 갱신
        self._refresh_from_device_manager()

    # ───────── 버튼 콜백 ─────────
    def _on_send_lcd_clicked(self) -> None:
        l1 = self.edit_lcd1.text()
        l2 = self.edit_lcd2.text()
        self._dev_mgr.send_lcd_text(l1, l2, guid=self._device_guid)

    # ───────── 폴링으로 UI 갱신 ─────────
    def _refresh_from_device_manager(self) -> None:
        # 로그
        logs: List[str] = self._dev_mgr.get_gate_logs(guid=self._device_guid)
        if len(logs) != self._last_log_count:
            self.text_log.clear()
            self.text_log.append("\n".join(logs))
            self.text_log.moveCursor(self.text_log.textCursor().MoveOperation.End)
            self._last_log_count = len(logs)

        # 장비 목록
        devices = self._dev_mgr.get_gate_devices(guid=self._device_guid)
        self.list_devices.clear()
        for d in devices:
            guid = str(d.get("guid", "")).strip()
            name = str(d.get("name", "")).strip()
            self.list_devices.addItem(f"{guid} → {name}")
