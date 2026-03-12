import queue
from typing import Any, Dict, List

try:
    import cv2
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QImage, QPixmap
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
    QFrame,
    QGridLayout,
    QSplitter,
    QComboBox,
)

from api_client import ApiClient
from config import settings
from lpr_ws_server import start_lpr_ws_server_threads
from ui.resident_manager import ResidentManagerWindow
from ui.sensor_manager import SensorManagerWindow
from ui.parking_records_dialog import ParkingRecordsDialog


class DashboardWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.api = ApiClient()
        self._resident_window: ResidentManagerWindow | None = None
        self._sensor_window: SensorManagerWindow | None = None
        self._operation_mode_on: bool = True
        self._gate_sensor_state: int = 1
        self._entry_gate_connected: bool = False
        self._syncing_gate_combo: bool = False
        # CCTV 웹캠
        self._video_cap: Any = None
        self._video_playing: bool = False
        self._video_timer: QTimer | None = None
        # LPR WebSocket 수신 큐 (channel, jpeg_bytes). 채널 0=입구, 1=출구
        self._lpr_frame_queue: queue.Queue = queue.Queue(maxsize=30)

        self.setWindowTitle("스마트 주차장 관리 시스템 - 대시보드")
        self.resize(1200, 700)

        # 전체 스타일
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #1e1f26;
            }
            QGroupBox {
                color: #ffffff;
                border: 1px solid #3a3b45;
                border-radius: 6px;
                margin-top: 18px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
            }
            QLabel {
                color: #e0e0e0;
            }
            QTableWidget {
                background-color: #252733;
                color: #f5f5f5;
                gridline-color: #3a3b45;
                selection-background-color: #3a86ff;
            }
            QPushButton {
                background-color: #3a86ff;
                color: #ffffff;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #4f9dff;
            }
            QPushButton:pressed {
                background-color: #2f6fd1;
            }
            """
        )

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
            lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
            summary_layout.addWidget(lbl)

        main_layout.addWidget(summary_box)

        # 실시간 영상 3구역: 상단 CCTV, 하단 입구/출구 LPR
        video_box = QGroupBox("실시간 영상 (CCTV · 입구 LPR · 출구 LPR)")
        video_layout = QVBoxLayout()
        video_box.setLayout(video_layout)
        video_style = "background-color: #252733; border-radius: 6px; border: 1px solid #3a3b45;"
        min_size = (320, 240)

        # ── 상단: CCTV 영역 (영상 + 하단 제어 버튼) ────────────────
        cctv_col = QVBoxLayout()
        self.label_cctv = QLabel("재생 버튼을 눌러 웹캠을 시작하세요.")
        self.label_cctv.setMinimumSize(*min_size)
        self.label_cctv.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_cctv.setStyleSheet(video_style)
        cctv_col.addWidget(self.label_cctv, 1)

        self.btn_video_toggle = QPushButton("웹캠 재생")
        self.btn_video_toggle.setCheckable(True)
        self.btn_video_toggle.clicked.connect(self._on_video_toggle)
        cctv_col.addWidget(self.btn_video_toggle)

        cctv_wrapper = QWidget()
        cctv_wrapper.setLayout(cctv_col)
        video_layout.addWidget(cctv_wrapper, 2)

        # ── 하단: 입구/출구 LPR 두 영상을 가로로 배치 ──────────────
        lpr_row = QHBoxLayout()

        port_entry = settings.lpr_ws_port_entry
        port_exit = settings.lpr_ws_port_exit
        self.label_lpr_entry = QLabel(f"입구 LPR\n(수신 대기 · 포트 {port_entry})")
        self.label_lpr_entry.setMinimumSize(*min_size)
        self.label_lpr_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_lpr_entry.setStyleSheet(video_style)
        self.label_lpr_entry.setToolTip(f"3.device_client .env: LPR_WS_SERVER_ENTRY_URL=ws://127.0.0.1:{port_entry} (같은 PC)")
        lpr_row.addWidget(self.label_lpr_entry, 1)

        self.label_lpr_exit = QLabel(f"출구 LPR\n(수신 대기 · 포트 {port_exit})")
        self.label_lpr_exit.setMinimumSize(*min_size)
        self.label_lpr_exit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_lpr_exit.setStyleSheet(video_style)
        self.label_lpr_exit.setToolTip(f"3.device_client .env: LPR_WS_SERVER_EXIT_URL=ws://127.0.0.1:{port_exit} (같은 PC)")
        lpr_row.addWidget(self.label_lpr_exit, 1)

        video_layout.addLayout(lpr_row, 1)

        if not _CV2_AVAILABLE:
            self.btn_video_toggle.setEnabled(False)
            self.label_cctv.setText("opencv-python\n필요")

        # 중앙 영역: 좌측 주차면 맵, 우측 장비/이벤트
        splitter = QSplitter()
        splitter.setOrientation(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, 1)

        # ── 좌측: 주차 레이아웃 맵 ─────────────────────────────
        left_frame = QFrame()
        left_layout = QVBoxLayout()
        left_frame.setLayout(left_layout)

        parking_box = QGroupBox("주차 레이아웃")
        parking_layout = QGridLayout()
        parking_box.setLayout(parking_layout)

        self.slot_widgets: dict[str, QLabel] = {}

        def create_slot_label(name: str, title: str) -> QLabel:
            lbl = QLabel(title)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedSize(90, 60)
            lbl.setStyleSheet(
                """
                background-color: #2e7d32;  /* 기본: 빈자리(초록) */
                border-radius: 6px;
                border: 2px solid #1b5e20;
                font-weight: bold;
            """
            )
            self.slot_widgets[name] = lbl
            return lbl

        # 노상 4면 (S1~S4)
        parking_layout.addWidget(QLabel("노상 주차면"), 0, 0, 1, 4)
        parking_layout.addWidget(create_slot_label("S1", "S1"), 1, 0)
        parking_layout.addWidget(create_slot_label("S2", "S2"), 1, 1)
        parking_layout.addWidget(create_slot_label("S3", "S3"), 1, 2)
        parking_layout.addWidget(create_slot_label("S4", "S4"), 1, 3)

        # 주차타워 6면 (T1~T6)
        parking_layout.addWidget(QLabel("주차타워"), 2, 0, 1, 3)
        parking_layout.addWidget(create_slot_label("T1", "T1"), 3, 0)
        parking_layout.addWidget(create_slot_label("T2", "T2"), 3, 1)
        parking_layout.addWidget(create_slot_label("T3", "T3"), 3, 2)
        parking_layout.addWidget(create_slot_label("T4", "T4"), 4, 0)
        parking_layout.addWidget(create_slot_label("T5", "T5"), 4, 1)
        parking_layout.addWidget(create_slot_label("T6", "T6"), 4, 2)

        left_layout.addWidget(parking_box)
        # 주차 레이아웃 아래에 실시간 영상 배치 (기존 레이아웃 유지, 위치만 이동)
        left_layout.addWidget(video_box)
        left_layout.addStretch()

        splitter.addWidget(left_frame)

        # ── 우측: 장비 목록 + 디바이스 상태 + 이벤트 ───────────
        right_frame = QFrame()
        right_vlayout = QVBoxLayout()
        right_frame.setLayout(right_vlayout)

        # 장비 목록
        devices_box = QGroupBox("장비 목록 (연결 방식 / 포트 / 상태)")
        devices_layout = QVBoxLayout()
        devices_box.setLayout(devices_layout)

        self.table_devices = QTableWidget(0, 7)
        self.table_devices.setHorizontalHeaderLabels(
            ["ID", "이름", "타입", "IP", "연결방식", "PortInfo", "연결 상태"],
        )
        self.table_devices.horizontalHeader().setStretchLastSection(True)

        devices_layout.addWidget(self.table_devices)
        right_vlayout.addWidget(devices_box, 2)

        # 디바이스 상태 요약 (차단바/LCD/입·출차 감지 센서)
        device_status_box = QGroupBox("디바이스 상태 요약")
        device_status_layout = QVBoxLayout()
        device_status_box.setLayout(device_status_layout)

        # 차단기 상태 콤보박스
        gate_row = QHBoxLayout()
        label_gate = QLabel("차단기 상태:")
        self.combo_gate_status = QComboBox()
        self.combo_gate_status.addItems(["연결 안됨", "닫힘", "열림", "자동"])
        self.combo_gate_status.setCurrentIndex(0)
        # 초기에는 '연결 안됨' 상태이므로 나머지 항목 비활성화
        self.combo_gate_status.currentIndexChanged.connect(
            self._update_gate_combo_enabled
        )
        self.combo_gate_status.currentIndexChanged.connect(self._on_gate_status_changed)
        self._update_gate_combo_enabled()
        gate_row.addWidget(label_gate)
        gate_row.addWidget(self.combo_gate_status)
        gate_row.addStretch()
        device_status_layout.addLayout(gate_row)

        # 운영 상태 스위치 (ON/OFF)
        op_row = QHBoxLayout()
        op_row.addWidget(QLabel("운영 상태:"))
        self.btn_operation_mode = QPushButton("ON")
        self.btn_operation_mode.setCheckable(True)
        self.btn_operation_mode.clicked.connect(self._on_operation_mode_clicked)
        op_row.addWidget(self.btn_operation_mode)
        op_row.addStretch()
        device_status_layout.addLayout(op_row)

        # 센서 상태 버튼 (좌: 입차 감지, 우: 출차 감지)
        sensor_row = QHBoxLayout()
        label_sensor = QLabel("입·출차 감지 센서:")
        sensor_row.addWidget(label_sensor)

        self.btn_sensor_left = QPushButton("입차")
        self.btn_sensor_right = QPushButton("출차")

        # 기본 스타일: 연결 안됨(회색)
        self._set_sensor_button_state(self.btn_sensor_left, "연결 안됨")
        self._set_sensor_button_state(self.btn_sensor_right, "연결 안됨")

        # Tooltip 설명 추가
        tooltip_text = (
            "센서 상태 의미:\n"
            "- 회색: 연결 안됨 (센서 미연결 / 데이터 없음)\n"
            "- 초록: 감지 없음 (센서 정상, 차량 없음)\n"
            "- 빨강: 차량 감지 (입차/출차 감지됨)"
        )
        self.btn_sensor_left.setToolTip(tooltip_text)
        self.btn_sensor_right.setToolTip(tooltip_text)

        sensor_row.addWidget(self.btn_sensor_left)
        sensor_row.addWidget(self.btn_sensor_right)
        sensor_row.addStretch()
        device_status_layout.addLayout(sensor_row)

        # LCD / 센서 요약 텍스트
        self.label_lcd_info = QLabel("LCD: -")
        self.label_sensor_info = QLabel("센서 요약: -")
        for lbl in (self.label_lcd_info, self.label_sensor_info):
            lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            device_status_layout.addWidget(lbl)

        right_vlayout.addWidget(device_status_box, 1)

        # 최근 이벤트
        events_box = QGroupBox("최근 이벤트")
        events_layout = QVBoxLayout()
        events_box.setLayout(events_layout)

        self.label_events = QLabel("이벤트 정보 없음")
        self.label_events.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.label_events.setWordWrap(True)
        events_layout.addWidget(self.label_events)

        right_vlayout.addWidget(events_box, 1)

        splitter.addWidget(right_frame)
        # 좌우 폭을 픽셀 기준으로 대략 40:60 비율로 설정 (예: 800px : 1200px)
        splitter.setSizes([400, 1600])

        # 리프레시 버튼 및 자동 리프레시 타이머
        btn_layout = QHBoxLayout()
        self.button_refresh = QPushButton("지금 새로고침")
        self.button_refresh.clicked.connect(self.refresh_all)
        btn_layout.addWidget(self.button_refresh)

        self.button_manage_residents = QPushButton("입주민 / 차량 / RFID 관리")
        self.button_manage_residents.clicked.connect(
            self.open_resident_manager,
        )
        btn_layout.addWidget(self.button_manage_residents)

        self.button_parking_records = QPushButton("주차 기록 조회")
        self.button_parking_records.clicked.connect(self.open_parking_records)
        btn_layout.addWidget(self.button_parking_records)

        self.button_manage_sensors = QPushButton("장비관리 / 센서 관리")
        self.button_manage_sensors.clicked.connect(
            self.open_sensor_manager,
        )
        btn_layout.addWidget(self.button_manage_sensors)

        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh_all)
        self.timer.start()

        # CCTV 프레임 갱신용 타이머 (재생 중일 때만 동작)
        self._video_timer = QTimer(self)
        self._video_timer.setInterval(40)
        self._video_timer.timeout.connect(self._update_video_frame)

        # LPR WebSocket 서버 기동 (입구·출구 각각 별도 스레드/포트)
        lpr_threads = start_lpr_ws_server_threads(
            settings.lpr_ws_host,
            settings.lpr_ws_port_entry,
            settings.lpr_ws_port_exit,
            self._lpr_frame_queue,
        )
        if lpr_threads is None:
            self.statusBar().showMessage(
                "LPR 수신 비활성: pip install websockets 후 2.client 재실행",
                10000,
            )
        # LPR 수신 큐 처리 타이머
        self._lpr_timer = QTimer(self)
        self._lpr_timer.setInterval(50)
        self._lpr_timer.timeout.connect(self._drain_lpr_queue)
        self._lpr_timer.start()

        self.refresh_all()
        if lpr_threads:
            self.statusBar().showMessage(
                f"LPR 수신: 입구 {settings.lpr_ws_port_entry} / 출구 {settings.lpr_ws_port_exit} — 3.device_client .env 포트와 일치해야 함",
                8000,
            )

    def closeEvent(self, event) -> None:
        self._stop_video()
        self.api.close()
        super().closeEvent(event)

    def open_parking_records(self) -> None:
        dlg = ParkingRecordsDialog(self)
        dlg.exec()

    def _on_video_toggle(self) -> None:
        if self.btn_video_toggle.isChecked():
            self._start_video()
        else:
            self._stop_video()

    def _start_video(self) -> None:
        if not _CV2_AVAILABLE or self._video_playing:
            return
        self._video_cap = cv2.VideoCapture(0)
        if not self._video_cap.isOpened():
            self.label_cctv.setText("웹캠을 열 수 없습니다.")
            self.btn_video_toggle.setChecked(False)
            return
        self._video_playing = True
        self.btn_video_toggle.setText("일시정지")
        self._video_timer.start()

    def _stop_video(self) -> None:
        self._video_playing = False
        self._video_timer.stop()
        if self._video_cap is not None:
            try:
                self._video_cap.release()
            except Exception:
                pass
            self._video_cap = None
        self.btn_video_toggle.setChecked(False)
        self.btn_video_toggle.setText("재생")
        self.label_cctv.setText("재생 버튼을 눌러 웹캠을 시작하세요.")

    def _update_video_frame(self) -> None:
        if not _CV2_AVAILABLE or not self._video_playing or self._video_cap is None:
            return
        ret, frame = self._video_cap.read()
        if not ret or frame is None:
            return
        h, w, ch = frame.shape
        bytes_per_line = ch * w
        qimg = QImage(
            frame.data,
            w,
            h,
            bytes_per_line,
            QImage.Format.Format_BGR888,
        ).copy()
        pix = QPixmap.fromImage(qimg)
        self.label_cctv.setPixmap(
            pix.scaled(
                self.label_cctv.width(),
                self.label_cctv.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _drain_lpr_queue(self) -> None:
        """LPR WebSocket에서 받은 프레임을 큐에서 꺼내 입구/출구 라벨에 표시."""
        while True:
            try:
                channel, jpeg_bytes = self._lpr_frame_queue.get_nowait()
            except queue.Empty:
                break
            if not jpeg_bytes:
                continue
            qimg = QImage()
            if not qimg.loadFromData(jpeg_bytes):
                continue
            pix = QPixmap.fromImage(qimg)
            label = self.label_lpr_entry if channel == 0 else self.label_lpr_exit
            label.setPixmap(
                pix.scaled(
                    label.width(),
                    label.height(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def open_resident_manager(self) -> None:
        if self._resident_window is None:
            self._resident_window = ResidentManagerWindow()
        self._resident_window.show()
        self._resident_window.raise_()
        self._resident_window.activateWindow()

    def open_sensor_manager(self) -> None:
        if self._sensor_window is None:
            self._sensor_window = SensorManagerWindow()
        self._sensor_window.show()
        self._sensor_window.raise_()
        self._sensor_window.activateWindow()

    def refresh_all(self) -> None:
        try:
            dashboard = self.api.get_dashboard()
            devices = self.api.list_devices()
        except Exception as e:  # noqa: BLE001
            self.statusBar().showMessage(f"서버 통신 오류: {e}")
            return

        self.update_summary(dashboard)
        self.update_devices_table(devices)
        self.update_device_status_summary(devices, dashboard)
        self._apply_operation_mode_ui(bool(dashboard.get("operation_mode_on", True)))
        self.update_events(dashboard.get("recent_events", []))
        self.statusBar().showMessage("데이터 갱신 완료", 2000)

    def update_summary(self, data: Dict[str, Any]) -> None:
        self.label_total.setText(f"총 주차면: {data.get('total_slots', '-')}")
        self.label_occupied.setText(f"주차 중: {data.get('occupied_slots', '-')}")
        self.label_free.setText(f"빈 공간: {data.get('free_slots', '-')}")
        self.label_devices.setText(f"활성 장비: {data.get('active_devices', '-')}")

        # 슬롯 상태가 포함되어 있다면 맵에도 반영
        slots: List[Dict[str, Any]] | None = data.get("slots")
        if slots:
            self.update_slot_map(slots)

            # 디바이스 센서 요약도 업데이트 (현재는 슬롯 점유 기반으로 요약)
            occupied = [s for s in slots if s.get("is_occupied")]
            total = len(slots)
            self.label_sensor_info.setText(
                f"센서 기반 주차 상태: {len(occupied)}/{total}면 사용 중"
            )

            # 간단히 LCD 정보도 여기서 표현 (esp32_board2의 '현재 X대 주차중'과 동일 의미)
            self.label_lcd_info.setText(
                f"LCD 표시 예: 현재 {len(occupied)}대 주차중"
            )

        # 차단기 상태 콤보박스는 현재 UI 테스트용 (향후 서버/디바이스와 연동 예정)
        # 서버 정보에 따라 기본값을 바꾸고 싶다면 여기에서 setCurrentIndex 를 조정하면 됨.

    def _set_sensor_button_state(self, button: QPushButton, state: str) -> None:
        """센서 버튼 색상/텍스트를 상태에 따라 변경."""
        if state == "연결 안됨":
            button.setStyleSheet(
                """
                QPushButton {
                    background-color: #616161;
                    color: #ffffff;
                    border-radius: 4px;
                    padding: 4px 8px;
                }
                """
            )
        elif state == "차량 감지":
            button.setStyleSheet(
                """
                QPushButton {
                    background-color: #c62828;
                    color: #ffffff;
                    border-radius: 4px;
                    padding: 4px 8px;
                }
                """
            )
        elif state == "감지 없음":
            button.setStyleSheet(
                """
                QPushButton {
                    background-color: #2e7d32;
                    color: #ffffff;
                    border-radius: 4px;
                    padding: 4px 8px;
                }
                """
            )
        button.setProperty("sensor_state", state)

    def _update_gate_combo_enabled(self) -> None:
        """
        차단기 상태 콤보박스의 항목 활성화/비활성 제어.

        - esp32_board1_1 미연결: 0번만 선택 가능, 1~3 비활성화
        - esp32_board1_1 연결됨: 0번 비활성화, 1~3 선택 가능
        """
        model = self.combo_gate_status.model()
        for i in range(model.rowCount()):
            item = model.item(i)
            if item is None:
                continue
            if not self._entry_gate_connected:
                item.setEnabled(i == 0)
            else:
                item.setEnabled(i != 0)

    def update_devices_table(self, devices: List[Dict[str, Any]]) -> None:
        self.table_devices.setRowCount(len(devices))
        for row, dev in enumerate(devices):
            self.table_devices.setItem(row, 0, QTableWidgetItem(str(dev.get("id", ""))))
            self.table_devices.setItem(row, 1, QTableWidgetItem(dev.get("name", "")))
            self.table_devices.setItem(row, 2, QTableWidgetItem(dev.get("type", "")))
            self.table_devices.setItem(
                row, 3, QTableWidgetItem(dev.get("ip_address", "") or "")
            )
            # 연결 방식: connection_type / detail / control_method
            conn_str_parts: list[str] = []
            if dev.get("connection_type"):
                conn_str_parts.append(str(dev.get("connection_type")))
            if dev.get("connection_detail"):
                conn_str_parts.append(str(dev.get("connection_detail")))
            if dev.get("control_method"):
                conn_str_parts.append(str(dev.get("control_method")))
            conn_str = " / ".join(conn_str_parts) if conn_str_parts else ""
            self.table_devices.setItem(row, 4, QTableWidgetItem(conn_str))

            # PortInfo (ethernet: port, serial: 포트명)
            self.table_devices.setItem(
                row,
                5,
                QTableWidgetItem(dev.get("port_info", "") or ""),
            )

            # 연결 상태 (is_connected)
            is_conn = bool(dev.get("is_connected"))
            status_item = QTableWidgetItem("연결됨" if is_conn else "미연결")
            if is_conn:
                status_item.setBackground(Qt.GlobalColor.darkGreen)
            else:
                status_item.setBackground(Qt.GlobalColor.darkRed)
            self.table_devices.setItem(row, 6, status_item)

    def update_device_status_summary(
        self,
        devices: List[Dict[str, Any]],
        dashboard: Dict[str, Any],
    ) -> None:
        """
        devices 목록을 바탕으로 게이트 컨트롤러(esp32_board1) 등의
        연결 상태를 상단 요약 UI(차단기 상태/센서 버튼)에 반영한다.
        """
        gate_connected = False
        found_by_guid = False

        for dev in devices:
            if (dev.get("device_guid") or "").strip() == "DEV-GATE-1":
                gate_connected = bool(dev.get("is_connected"))
                found_by_guid = True
                break
        if not found_by_guid:
            for dev in devices:
                dtype = (dev.get("type") or "").lower()
                if dtype == "gate_controller":
                    gate_connected = bool(dev.get("is_connected"))
                    break
        self._entry_gate_connected = gate_connected

        # 서버에 저장된 gate 상태 코드와 연동 (0:연결안됨 1:닫힘 2:열림 3:자동)
        desired_idx = int(dashboard.get("gate_sensor_state", 1))
        if not gate_connected:
            desired_idx = 0
        elif desired_idx == 0:
            # 연결되었는데 서버값이 0이면 기본 상태를 열림(2)으로 복구
            try:
                data = self.api.set_gate_state(gate_sensor_state=2)
                desired_idx = int(data.get("gate_sensor_state", 2))
            except Exception:
                desired_idx = 2
        desired_idx = max(0, min(3, desired_idx))
        self._gate_sensor_state = desired_idx
        if self.combo_gate_status.currentIndex() != desired_idx:
            self._syncing_gate_combo = True
            self.combo_gate_status.setCurrentIndex(desired_idx)
            self._syncing_gate_combo = False
        self._update_gate_combo_enabled()

        # 입/출차 감지 센서 버튼 상태 (주차타워 T1/T2 와 무관한 별도 상태)
        entry_conn = bool(dashboard.get("entry_sensor_connected", False))
        entry_det = bool(dashboard.get("entry_sensor_detected", False))
        exit_conn = bool(dashboard.get("exit_sensor_connected", False))
        exit_det = bool(dashboard.get("exit_sensor_detected", False))

        if not gate_connected or not entry_conn:
            self._set_sensor_button_state(self.btn_sensor_left, "연결 안됨")
        elif entry_det:
            self._set_sensor_button_state(self.btn_sensor_left, "차량 감지")
        else:
            self._set_sensor_button_state(self.btn_sensor_left, "감지 없음")

        if not gate_connected or not exit_conn:
            self._set_sensor_button_state(self.btn_sensor_right, "연결 안됨")
        elif exit_det:
            self._set_sensor_button_state(self.btn_sensor_right, "차량 감지")
        else:
            self._set_sensor_button_state(self.btn_sensor_right, "감지 없음")

    def _apply_operation_mode_ui(self, operation_mode_on: bool) -> None:
        self._operation_mode_on = operation_mode_on
        self.btn_operation_mode.blockSignals(True)
        self.btn_operation_mode.setChecked(operation_mode_on)
        self.btn_operation_mode.setText("ON" if operation_mode_on else "OFF")
        if operation_mode_on:
            self.btn_operation_mode.setStyleSheet(
                """
                QPushButton {
                    background-color: #2e7d32;
                    color: #ffffff;
                    border-radius: 4px;
                    padding: 4px 10px;
                }
                """
            )
        else:
            self.btn_operation_mode.setStyleSheet(
                """
                QPushButton {
                    background-color: #c62828;
                    color: #ffffff;
                    border-radius: 4px;
                    padding: 4px 10px;
                }
                """
            )
        self.btn_operation_mode.blockSignals(False)

    def _on_operation_mode_clicked(self) -> None:
        target = self.btn_operation_mode.isChecked()
        try:
            data = self.api.set_operation_mode(target)
            self._apply_operation_mode_ui(bool(data.get("operation_mode_on", target)))
            self.statusBar().showMessage(
                f"운영 상태 변경: {'ON' if self._operation_mode_on else 'OFF'}",
                2000,
            )
        except Exception as e:  # noqa: BLE001
            self.statusBar().showMessage(f"운영 상태 변경 실패: {e}", 3000)
            self._apply_operation_mode_ui(self._operation_mode_on)

    def _on_gate_status_changed(self, idx: int) -> None:
        if self._syncing_gate_combo:
            return
        if not self._entry_gate_connected:
            return
        try:
            data = self.api.set_gate_state(gate_sensor_state=idx)
            self._gate_sensor_state = int(data.get("gate_sensor_state", idx))
            self.statusBar().showMessage(
                f"차단기 상태 변경: {self.combo_gate_status.currentText()}",
                2000,
            )
        except Exception as e:  # noqa: BLE001
            self.statusBar().showMessage(f"차단기 상태 변경 실패: {e}", 3000)
            self._syncing_gate_combo = True
            self.combo_gate_status.setCurrentIndex(self._gate_sensor_state)
            self._syncing_gate_combo = False

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

    def update_slot_map(self, slots: List[Dict[str, Any]]) -> None:
        """S1~S4, T1~T6 슬롯 상태를 색상으로 표시.

        - sensor_connected == False : 회색 (센서 미연결 / 상태 미수신)
        - sensor_connected == True  & is_occupied == True  : 빨강 (차량 있음)
        - sensor_connected == True  & is_occupied == False : 초록 (빈자리)
        """
        for s in slots:
            name = s.get("name")
            widget = self.slot_widgets.get(name)
            if not widget:
                continue

            # 주차타워 슬롯(T1~T6)은 현재 센서 연동 대상이 아니므로 항상 비활성(회색)으로 표시.
            if isinstance(name, str) and name.startswith("T"):
                widget.setStyleSheet(
                    """
                    background-color: #616161;  /* 센서 연결 안됨: 회색 */
                    border-radius: 6px;
                    border: 2px solid #424242;
                    font-weight: bold;
                """
                )
                continue

            occupied = s.get("is_occupied", False)
            sensor_connected = s.get("sensor_connected", False)

            if not sensor_connected:
                widget.setStyleSheet(
                    """
                    background-color: #616161;  /* 센서 연결 안됨: 회색 */
                    border-radius: 6px;
                    border: 2px solid #424242;
                    font-weight: bold;
                """
                )
            elif occupied:
                widget.setStyleSheet(
                    """
                    background-color: #c62828;  /* 점유: 빨강 */
                    border-radius: 6px;
                    border: 2px solid #8e0000;
                    font-weight: bold;
                """
                )
            else:
                widget.setStyleSheet(
                    """
                    background-color: #2e7d32;  /* 빈자리: 초록 */
                    border-radius: 6px;
                    border: 2px solid #1b5e20;
                    font-weight: bold;
                """
                )


def run_dashboard() -> None:
    import sys

    app = QApplication(sys.argv)
    win = DashboardWindow()
    win.show()
    sys.exit(app.exec())

