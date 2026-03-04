from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
)

from device_manager import DeviceManager


class ParkingGuideTestDialog(QDialog):
    """
    esp32_board2(파킹 가이드)의 이벤트를 간단히 점검하는 팝업.

    - 3.device_client 가 수신한 로그 중에서 SPOT_1~4 관련 라인을 표시
    - '새로고침' 버튼 또는 주기적인 타이머로 최신 이벤트를 확인
    """

    def __init__(self, device_manager: DeviceManager, parent=None) -> None:
        super().__init__(parent)
        self._dev_mgr = device_manager

        self.setWindowTitle("파킹 가이드 테스트 (esp32_board2)")
        self.resize(600, 400)

        layout = QVBoxLayout()

        title = QLabel("esp32_board2 파킹 센서 이벤트 로그")
        layout.addWidget(title)

        btn_row = QHBoxLayout()
        self.btn_refresh = QPushButton("지금 새로고침")
        self.btn_refresh.clicked.connect(self.refresh_logs)
        btn_row.addWidget(self.btn_refresh)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.text_log = QTextEdit()
        self.text_log.setReadOnly(True)
        layout.addWidget(self.text_log, 1)

        self.setLayout(layout)

        # 주기적으로 로그 갱신 (예: 1초마다)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.refresh_logs)
        self._timer.start()

        self.refresh_logs()

    def refresh_logs(self) -> None:
        """
        DeviceManager 에서 수집한 전체 게이트/파킹 로그를 그대로 보여준다.

        - SPOT_x 이벤트뿐 아니라 [REG], [GATE] 등 등록/연결 상태 로그도
          함께 확인할 수 있도록 필터링을 제거했다.
        """
        logs = self._dev_mgr.get_gate_logs()
        self.text_log.clear()
        if logs:
            self.text_log.append("\n".join(logs))

