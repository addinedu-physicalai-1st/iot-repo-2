from typing import Any, Dict, List

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QGroupBox,
)

from api_client import ApiClient


class DashboardWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.api = ApiClient()

        self.setWindowTitle("스마트 주차장 관리 시스템 - 대시보드")
        self.resize(900, 600)

        root = QWidget()
        self.setCentralWidget(root)

        main_layout = QVBoxLayout()
        root.setLayout(main_layout)

        # 상단 요약 영역
        summary_box = QGroupBox("주차장 요약")
        summary_layout = QHBoxLayout()
        summary_box.setLayout(summary_layout)

        self.label_total = QLabel("총 주차면: -")
        self.label_occupied = QLabel("주차 중: -")
        self.label_free = QLabel("빈 공간: -")
        self.label_devices = QLabel("활성 장비: -")

        for lbl in (
            self.label_total,
            self.label_occupied,
            self.label_free,
            self.label_devices,
        ):
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-size: 16px;")
            summary_layout.addWidget(lbl)

        main_layout.addWidget(summary_box)

        # 중간 영역: 장비 목록
        devices_box = QGroupBox("장비 목록")
        devices_layout = QVBoxLayout()
        devices_box.setLayout(devices_layout)

        self.table_devices = QTableWidget(0, 4)
        self.table_devices.setHorizontalHeaderLabels(["ID", "이름", "타입", "IP"])
        self.table_devices.horizontalHeader().setStretchLastSection(True)

        devices_layout.addWidget(self.table_devices)
        main_layout.addWidget(devices_box)

        # 하단: 최근 이벤트(서버 API 구조만 잡혀 있으므로 간단히 텍스트로 표현)
        events_box = QGroupBox("최근 이벤트 (서버에서 요약)")
        events_layout = QVBoxLayout()
        events_box.setLayout(events_layout)

        self.label_events = QLabel("이벤트 정보 없음")
        self.label_events.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.label_events.setWordWrap(True)
        events_layout.addWidget(self.label_events)

        main_layout.addWidget(events_box)

        # 리프레시 버튼 및 자동 리프레시 타이머
        btn_layout = QHBoxLayout()
        self.button_refresh = QPushButton("지금 새로고침")
        self.button_refresh.clicked.connect(self.refresh_all)
        btn_layout.addWidget(self.button_refresh)
        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)

        self.timer = QTimer(self)
        self.timer.setInterval(5000)  # 5초마다 자동 갱신
        self.timer.timeout.connect(self.refresh_all)
        self.timer.start()

        self.refresh_all()

    def closeEvent(self, event) -> None:
        self.api.close()
        super().closeEvent(event)

    def refresh_all(self) -> None:
        try:
            dashboard = self.api.get_dashboard()
            devices = self.api.list_devices()
        except Exception as e:  # noqa: BLE001
            self.statusBar().showMessage(f"서버 통신 오류: {e}")
            return

        self.update_summary(dashboard)
        self.update_devices_table(devices)
        self.update_events(dashboard.get("recent_events", []))
        self.statusBar().showMessage("데이터 갱신 완료", 2000)

    def update_summary(self, data: Dict[str, Any]) -> None:
        self.label_total.setText(f"총 주차면: {data.get('total_slots', '-')}")
        self.label_occupied.setText(f"주차 중: {data.get('occupied_slots', '-')}")
        self.label_free.setText(f"빈 공간: {data.get('free_slots', '-')}")
        self.label_devices.setText(f"활성 장비: {data.get('active_devices', '-')}")

    def update_devices_table(self, devices: List[Dict[str, Any]]) -> None:
        self.table_devices.setRowCount(len(devices))
        for row, dev in enumerate(devices):
            self.table_devices.setItem(row, 0, QTableWidgetItem(str(dev.get("id", ""))))
            self.table_devices.setItem(row, 1, QTableWidgetItem(dev.get("name", "")))
            self.table_devices.setItem(row, 2, QTableWidgetItem(dev.get("type", "")))
            self.table_devices.setItem(
                row, 3, QTableWidgetItem(dev.get("ip_address", "") or "")
            )

    def update_events(self, events: List[Dict[str, Any]]) -> None:
        if not events:
            self.label_events.setText("최근 이벤트가 없습니다.")
            return

        lines: list[str] = []
        for ev in events:
            device_id = ev.get("device_id")
            etype = ev.get("event_type")
            msg = ev.get("message") or ""
            created = ev.get("created_at")
            lines.append(f"[{created}] device={device_id} type={etype} msg={msg}")

        self.label_events.setText("\n".join(lines))


def run_dashboard() -> None:
    import sys

    app = QApplication(sys.argv)
    win = DashboardWindow()
    win.show()
    sys.exit(app.exec())

