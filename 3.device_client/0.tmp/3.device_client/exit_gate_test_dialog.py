"""
출구 차단기(esp32_board1_2, DEV-GATE-2) 테스트용 팝업.

- LCD 2줄 출력 명령 전송 (TYPE_CMD_DISPLAY)
- 게이트/출구 이벤트 로그 표시 (기존 gate log 활용)
"""
from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QLineEdit,
)

from device_manager import DeviceManager


class ExitGateTestDialog(QDialog):
    """ESP32 출구 차단기(보드1_2) 테스트: LCD 전송 + 로그."""

    def __init__(self, device_manager: DeviceManager, parent=None) -> None:
        super().__init__(parent)
        self._dev_mgr = device_manager
        self._last_log_count = 0

        self.setWindowTitle("출구 차단기 테스트 (ESP32 보드1_2)")
        self.resize(520, 480)

        layout = QVBoxLayout()

        layout.addWidget(QLabel("LCD 1줄 (최대 16자):"))
        self.edit_line1 = QLineEdit("SERVER OK")
        self.edit_line1.setMaxLength(16)
        layout.addWidget(self.edit_line1)

        layout.addWidget(QLabel("LCD 2줄 (최대 16자):"))
        self.edit_line2 = QLineEdit("READY!")
        self.edit_line2.setMaxLength(16)
        layout.addWidget(self.edit_line2)

        self.btn_send = QPushButton("LCD 전송")
        self.btn_send.clicked.connect(self._on_send_clicked)
        layout.addWidget(self.btn_send)

        layout.addWidget(QLabel("출구 보드 / 센서 로그:"))
        self.text_log = QTextEdit()
        self.text_log.setReadOnly(True)
        layout.addWidget(self.text_log, 1)

        self.setLayout(layout)

        self._timer = QTimer(self)
        self._timer.setInterval(800)
        self._timer.timeout.connect(self._refresh_log)
        self._timer.start()
        self._refresh_log()

    def _on_send_clicked(self) -> None:
        line1 = (self.edit_line1.text() or "SERVER OK")[:16]
        line2 = (self.edit_line2.text() or "READY!")[:16]
        self._dev_mgr.send_exit_display(line1, line2)

    def _refresh_log(self) -> None:
        logs = self._dev_mgr.get_gate_logs()
        if len(logs) != self._last_log_count:
            self.text_log.clear()
            self.text_log.append("\n".join(logs))
            self.text_log.moveCursor(self.text_log.textCursor().MoveOperation.End)
            self._last_log_count = len(logs)
