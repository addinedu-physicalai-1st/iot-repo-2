from __future__ import annotations

from typing import List, Dict, Any

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QGroupBox,
)

from architect_manager import ArchitectManager
from device_manager import DeviceManager
from info_manager import InfoManager
from transmission_manager import TransmissionManager
from gate_test_dialog import GateTestDialog
from parking_guide_test_dialog import ParkingGuideTestDialog
from lpr_enter_test_dialog import LprEnterTestDialog


class MainWindow(QMainWindow):
    """
    3.device_client 메인 대시보드 창.

    - InfoManager 에 저장된 정보를 읽어와
      서버 연결 상태, 디바이스 리스트, UDP 관련 정보 등을 표시한다.
    - TransmissionManager 를 통해 서버와 통신하여 정보를 갱신한다.
    """

    def __init__(
        self,
        info_manager: InfoManager,
        device_manager: DeviceManager,
        architect_manager: ArchitectManager,
        transmission_manager: TransmissionManager,
    ) -> None:
        super().__init__()
        self._info = info_manager
        self._device_mgr = device_manager
        self._arch_mgr = architect_manager
        self._tx = transmission_manager
        self._gate_dialog: GateTestDialog | None = None
        self._parking_dialog: ParkingGuideTestDialog | None = None
        self._lpr_dialog: LprEnterTestDialog | None = None

        self.setWindowTitle("스마트 주차장 - 디바이스 클라이언트 대시보드")
        self.resize(1100, 700)

        root = QWidget()
        self.setCentralWidget(root)
        main_layout = QVBoxLayout()
        root.setLayout(main_layout)

        # ───────── 상단 요약 영역 ─────────
        summary_box = QGroupBox("연결 요약")
        summary_layout = QHBoxLayout()
        summary_box.setLayout(summary_layout)

        self.label_server = QLabel("서버 상태: 확인 중...")
        self.label_devices = QLabel("등록 디바이스: -")
        self.label_active_devices = QLabel("활성 디바이스: -")
        self.label_udp = QLabel("UDP 스트림: -")

        for lbl in (
            self.label_server,
            self.label_devices,
            self.label_active_devices,
            self.label_udp,
        ):
            lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            summary_layout.addWidget(lbl)

        main_layout.addWidget(summary_box)

        # ───────── 디바이스 테이블 ─────────
        devices_box = QGroupBox("디바이스 목록 (1.server 기준)")
        devices_layout = QVBoxLayout()
        devices_box.setLayout(devices_layout)

        self.table_devices = QTableWidget(0, 6)
        self.table_devices.setHorizontalHeaderLabels(
            ["ID", "이름", "타입", "IP", "PortInfo", "연결 상태"],
        )
        self.table_devices.horizontalHeader().setStretchLastSection(True)

        devices_layout.addWidget(self.table_devices)

        btn_row = QHBoxLayout()
        self.btn_refresh = QPushButton("지금 새로고침")
        self.btn_refresh.clicked.connect(self.refresh_from_server)
        btn_row.addWidget(self.btn_refresh)

        self.btn_gate_test = QPushButton ("esp32 board_1_1 테스트") #("입구 차단기 테스트") => 입구 차단기 이지만 RFID, IR 센서가 있어 보드 테스트로 명명.
        self.btn_gate_test.clicked.connect(self.open_gate_test_dialog)
        btn_row.addWidget(self.btn_gate_test)

        self.btn_parking_test = QPushButton("esp32_board2 파킹 가이드 테스트")
        self.btn_parking_test.clicked.connect(self.open_parking_guide_test_dialog)
        btn_row.addWidget(self.btn_parking_test)

        self.btn_lpr_test = QPushButton("입구 LPR 카메라 테스트 (esp32_lpr_enter)")
        self.btn_lpr_test.clicked.connect(self.open_lpr_enter_test_dialog)
        btn_row.addWidget(self.btn_lpr_test)

        btn_row.addStretch()
        devices_layout.addLayout(btn_row)

        main_layout.addWidget(devices_box, 1)

        # ───────── 타이머: 주기적 갱신 ─────────
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self.refresh_from_server)
        self._timer.start()

        # 초기 한 번 불러오기
        self.refresh_from_server()

    # ───────── 데이터 로드 및 UI 반영 ─────────
    def refresh_from_server(self) -> None:
        try:
            self._tx.refresh_from_server()
        except Exception as e:  # noqa: BLE001
            self.statusBar().showMessage(f"서버 통신 오류: {e}", 3000)
            self.label_server.setText(f"서버 상태: 연결 실패 ({e})")
            return

        self._update_summary()
        self._update_devices_table(self._info.devices)
        self.statusBar().showMessage("데이터 갱신 완료", 2000)

    def open_gate_test_dialog(self) -> None:
        """입구 차단기(ESP32 보드1) 테스트용 팝업을 연다."""
        if self._gate_dialog is None:
            self._gate_dialog = GateTestDialog(self._device_mgr, self)
        self._gate_dialog.show()
        self._gate_dialog.raise_()
        self._gate_dialog.activateWindow()

    def open_parking_guide_test_dialog(self) -> None:
        """esp32_board2(파킹 가이드) 이벤트를 확인하는 팝업을 연다."""
        if self._parking_dialog is None:
            self._parking_dialog = ParkingGuideTestDialog(self._device_mgr, self)
        self._parking_dialog.show()
        self._parking_dialog.raise_()
        self._parking_dialog.activateWindow()

    def open_lpr_enter_test_dialog(self) -> None:
        """입구 LPR 카메라(esp32_lpr_enter) 테스트용 팝업을 연다."""
        if self._lpr_dialog is None:
            self._lpr_dialog = LprEnterTestDialog(self._tx, self)
        self._lpr_dialog.show()
        self._lpr_dialog.raise_()
        self._lpr_dialog.activateWindow()

    def _update_summary(self) -> None:
        health = self._info.server_health or {}
        status = health.get("status", "unknown")
        self.label_server.setText(
            f"서버 상태: {status} ({self._info.env.server_base_url})",
        )

        devices = self._info.devices
        total = len(devices)
        active = sum(1 for d in devices if d.get("is_connected"))
        self.label_devices.setText(f"등록 디바이스: {total}개")
        self.label_active_devices.setText(f"활성 디바이스: {active}개")

        # UDP 관련 정보는 .env + LPR 카메라 서버 config 를 기준으로 단순 표시
        udp_host = self._info.env.udp_listen_host
        udp_port = self._info.env.udp_listen_port
        self.label_udp.setText(f"UDP 수신: {udp_host}:{udp_port}")

    def _update_devices_table(self, devices: List[Dict[str, Any]]) -> None:
        self.table_devices.setRowCount(len(devices))
        for row, dev in enumerate(devices):
            self.table_devices.setItem(
                row,
                0,
                QTableWidgetItem(str(dev.get("id", ""))),
            )
            self.table_devices.setItem(
                row,
                1,
                QTableWidgetItem(dev.get("name", "")),
            )
            self.table_devices.setItem(
                row,
                2,
                QTableWidgetItem(dev.get("type", "")),
            )
            self.table_devices.setItem(
                row,
                3,
                QTableWidgetItem(dev.get("ip_address", "") or ""),
            )
            self.table_devices.setItem(
                row,
                4,
                QTableWidgetItem(dev.get("port_info", "") or ""),
            )

            is_conn = bool(dev.get("is_connected"))
            status_item = QTableWidgetItem("연결됨" if is_conn else "미연결")
            if is_conn:
                status_item.setBackground(Qt.GlobalColor.darkGreen)
            else:
                status_item.setBackground(Qt.GlobalColor.darkRed)
            self.table_devices.setItem(row, 5, status_item)

