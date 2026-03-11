from typing import Dict, List

import cv2
import json
import requests
import numpy as np
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from api_client import DeviceApiClient
from arduino_client import ArduinoClient
from config import settings
from esp32_board_client import Esp32BoardManager
from esp32_receiver import Esp32UdpReceiver


class DeviceDashboardWindow(QMainWindow):
    slotUpdated = pyqtSignal(str, bool)
    cameraFrame = pyqtSignal(int, object)  # np.ndarray

    def __init__(self) -> None:
        super().__init__()

        self.api = DeviceApiClient()
        self.arduino: ArduinoClient | None = None
        self.esp32: Esp32UdpReceiver | None = None
        self.esp_boards: Esp32BoardManager | None = None

        self.setWindowTitle("스마트 주차장 - 디바이스 클라이언트")
        self.resize(1200, 700)

        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #12131a;
            }
            QGroupBox {
                color: #ffffff;
                border: 1px solid #343542;
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
                background-color: #20222b;
                color: #f5f5f5;
                gridline-color: #3a3b45;
                selection-background-color: #3a86ff;
            }
            QPushButton {
                background-color: #3a86ff;
                color: #ffffff;
                border-radius: 4px;
                padding: 6px 14px;
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

        # 상단 상태 바
        status_box = QGroupBox("연결 상태")
        status_layout = QHBoxLayout()
        status_box.setLayout(status_layout)

        self.label_server = QLabel("서버: 연결 확인 중...")
        self.label_arduino = QLabel("아두이노: -")
        self.label_camera = QLabel("ESP32 카메라: -")
        self.label_esp32_1 = QLabel("ESP32 보드1: -")
        self.label_esp32_2 = QLabel("ESP32 보드2: -")

        for lbl in (
            self.label_server,
            self.label_arduino,
            self.label_camera,
            self.label_esp32_1,
            self.label_esp32_2,
        ):
            lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            status_layout.addWidget(lbl)

        # 장비 개별 테스트 탭 윈도우 열기 버튼
        self.btn_open_test_tabs = QPushButton("장비 테스트 탭 열기")
        self.btn_open_test_tabs.clicked.connect(self.open_test_tabs_window)
        status_layout.addWidget(self.btn_open_test_tabs)

        main_layout.addWidget(status_box)

        # 디바이스 접속 리스트
        conn_box = QGroupBox("디바이스 접속 리스트")
        conn_layout = QVBoxLayout()
        conn_box.setLayout(conn_layout)

        self.table_conns = QTableWidget(0, 6)
        self.table_conns.setHorizontalHeaderLabels(
            ["ID", "이름", "타입", "연결방식", "PortInfo", "연결 상태"],
        )
        self.table_conns.horizontalHeader().setStretchLastSection(True)
        conn_layout.addWidget(self.table_conns)

        conn_btn_row = QHBoxLayout()
        self.btn_refresh_conns = QPushButton("디바이스 접속 상태 새로고침")
        self.btn_refresh_conns.clicked.connect(self.refresh_device_connections)
        conn_btn_row.addWidget(self.btn_refresh_conns)
        conn_btn_row.addStretch()
        conn_layout.addLayout(conn_btn_row)

        main_layout.addWidget(conn_box)

        # 중앙: 좌측 슬롯 상태, 우측 카메라 / 장비
        center_layout = QHBoxLayout()
        main_layout.addLayout(center_layout, 1)

        # 좌측: 슬롯 테이블
        slot_box = QGroupBox("주차 슬롯 상태 (S1~S4, T1~T6)")
        slot_layout = QVBoxLayout()
        slot_box.setLayout(slot_layout)

        self.table_slots = QTableWidget(10, 3)
        self.table_slots.setHorizontalHeaderLabels(["슬롯", "레벨", "상태"])
        self.table_slots.horizontalHeader().setStretchLastSection(True)
        slot_layout.addWidget(self.table_slots)

        center_layout.addWidget(slot_box, 1)

        # 우측: 카메라 프리뷰 + 제어 버튼
        right_box = QGroupBox("카메라 / 제어")
        right_layout = QVBoxLayout()
        right_box.setLayout(right_layout)

        self.label_camera_view = QLabel("카메라 프레임 대기 중...")
        self.label_camera_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_camera_view.setMinimumSize(400, 300)
        self.label_camera_view.setStyleSheet(
            "background-color: #20222b; border-radius: 6px;"
        )
        right_layout.addWidget(self.label_camera_view, 1)

        btn_row = QHBoxLayout()
        self.btn_refresh = QPushButton("슬롯 상태 새로고침")
        self.btn_refresh.clicked.connect(self.load_slots_from_server)
        btn_row.addWidget(self.btn_refresh)

        self.btn_gate_open = QPushButton("차단기 열기 (테스트)")
        self.btn_gate_open.clicked.connect(self.send_gate_open)
        btn_row.addWidget(self.btn_gate_open)

        btn_row.addStretch()
        right_layout.addLayout(btn_row)

        center_layout.addWidget(right_box, 1)

        # 테스트 탭 윈도우 핸들
        self._test_tabs_window = None

        # 시그널 연결
        self.slotUpdated.connect(self.handle_slot_updated_ui)
        self.cameraFrame.connect(self.handle_camera_frame_ui)

        # 초기 데이터 로드 및 통신 시작
        self.load_slots_from_server()
        self.start_comm()
        self.refresh_device_connections()

        # 주기적으로 서버 상태 체크 (간단한 헬스 모니터)
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.update_server_status)
        self.timer.start()
        self.update_server_status()

        # 주기적으로 디바이스 접속 상태를 재확인하고 서버에 반영
        self.conn_timer = QTimer(self)
        self.conn_timer.setInterval(5000)
        self.conn_timer.timeout.connect(self.refresh_device_connections)
        self.conn_timer.start()

    # ───────── LPR 카메라 서버 연결 헬스체크 (REST) ─────────
    def _check_lpr_http_alive(self, device: dict) -> bool:
        """
        UDP 프레임이 없을 때, LPR 카메라 서버의 REST 포트를 헬스체크하여
        장비가 살아 있는지 보조적으로 판단한다.
        config: {"rest_port":5555,"udp_port":7072}
        """
        ip = device.get("ip_address")
        if not ip:
            return False
        rest_port = None
        cfg = device.get("config")
        if isinstance(cfg, str) and cfg:
            try:
                cfg_obj = json.loads(cfg)
                rest_port = cfg_obj.get("rest_port")
            except Exception:
                rest_port = None
        if not rest_port:
            # port_info 에 REST 포트가 들어있는 경우도 고려
            port_info = device.get("port_info")
            if port_info and str(port_info).isdigit():
                rest_port = int(port_info)
        if not rest_port:
            return False

        # LPR 카메라 서버는 /health 가 아니라 /api/devices 등의 REST 엔드포인트를 제공하므로
        # 가장 가벼운 GET /api/devices 로 생존 여부를 확인한다.
        url = f"http://{ip}:{rest_port}/api/devices"
        try:
            resp = requests.get(url, timeout=1.5)
            if resp.status_code != 200:
                return False
            # 응답 JSON 안에 devices 리스트에 guid/name 이 하나 이상 있으면
            # ESP32-CAM 이 register/heartbeat/command 폴링으로 살아 있다고 판단.
            try:
                data = resp.json()
            except Exception:
                return False
            devices = data.get("devices") if isinstance(data, dict) else None
            if not isinstance(devices, list) or not devices:
                return False
            return True
        except Exception:
            return False

    def open_test_tabs_window(self) -> None:
        """ESP32 카메라 / IR·RFID·모터 테스트용 탭 윈도우를 연다."""
        try:
            from device_test_tabs import DeviceTestTabsWindow
        except Exception as e:  # noqa: BLE001
            self.statusBar().showMessage(f"테스트 탭 로드 실패: {e}", 3000)
            return

        if self._test_tabs_window is None:
            self._test_tabs_window = DeviceTestTabsWindow()
        self._test_tabs_window.show()
        self._test_tabs_window.raise_()
        self._test_tabs_window.activateWindow()

    # ───────── 통신/백엔드 초기화 ─────────
    def start_comm(self) -> None:
        # 아두이노
        def on_slot_update_from_thread(slot: str, occupied: bool) -> None:
            # 백그라운드 쓰레드 → Qt 메인쓰레드로 신호 전달
            self.slotUpdated.emit(slot, occupied)

        self.arduino = ArduinoClient(on_slot_update=on_slot_update_from_thread)
        try:
            self.arduino.connect()
            self.label_arduino.setText("아두이노: 연결됨")
        except Exception as e:  # noqa: BLE001
            self.label_arduino.setText(f"아두이노: 연결 실패 ({e})")

        # ESP32 보드 1, 2 (TCP)
        def on_slot_update_from_esp(slot: str, occupied: bool) -> None:
            self.slotUpdated.emit(slot, occupied)

        try:
            self.esp_boards = Esp32BoardManager(on_slot_update=on_slot_update_from_esp)
            self.esp_boards.start()
            self.label_esp32_1.setText("ESP32 보드1: 연결 시도 중")
            self.label_esp32_2.setText("ESP32 보드2: 연결 시도 중")
        except Exception as e:  # noqa: BLE001
            self.label_esp32_1.setText(f"ESP32 보드1: 시작 실패 ({e})")
            self.label_esp32_2.setText(f"ESP32 보드2: 시작 실패 ({e})")

        # ESP32 카메라
        def on_frame_from_thread(frame_no: int, img: np.ndarray) -> None:
            self.cameraFrame.emit(frame_no, img)

        self.esp32 = Esp32UdpReceiver(on_frame=on_frame_from_thread)
        try:
            self.esp32.start()
            self.label_camera.setText("ESP32 카메라: 수신 대기")
        except Exception as e:  # noqa: BLE001
            self.label_camera.setText(f"ESP32 카메라: 시작 실패 ({e})")

    # ───────── 서버 연동 ─────────
    def load_slots_from_server(self) -> None:
        try:
            resp = self.api._client.get("/parking/slots")
            resp.raise_for_status()
            slots: List[Dict[str, object]] = resp.json()
        except Exception as e:  # noqa: BLE001
            self.statusBar().showMessage(f"슬롯 조회 실패: {e}", 3000)
            return

        # S1~S4, T1~T6 순서대로 정렬
        order = ["S1", "S2", "S3", "S4", "T1", "T2", "T3", "T4", "T5", "T6"]
        sorted_slots = sorted(
            slots, key=lambda s: order.index(s.get("name")) if s.get("name") in order else 999
        )

        self.table_slots.setRowCount(len(sorted_slots))
        for row, s in enumerate(sorted_slots):
            name = s.get("name", "")
            level = s.get("level", "")
            occupied = s.get("is_occupied", False)

            self.table_slots.setItem(row, 0, QTableWidgetItem(str(name)))
            self.table_slots.setItem(row, 1, QTableWidgetItem(str(level)))

            status_item = QTableWidgetItem("주차 중" if occupied else "빈 자리")
            if occupied:
                status_item.setBackground(Qt.GlobalColor.red)
            else:
                status_item.setBackground(Qt.GlobalColor.darkGreen)
            self.table_slots.setItem(row, 2, status_item)

    def update_server_status(self) -> None:
        try:
            h = self.api.health()
            self.label_server.setText(f"서버: 연결됨 ({h.get('status', 'ok')})")
        except Exception as e:  # noqa: BLE001
            self.label_server.setText(f"서버: 연결 실패 ({e})")

    def refresh_device_connections(self) -> None:
        """
        .env 의 device_no 와 device_clients 테이블을 매칭하여
        이 device_client 가 관리하는 devices 들의 접속 상태를 조회/표시하고,
        devices.is_connected 값을 업데이트한다.
        """
        try:
            dc_list = self.api.list_device_clients()
        except Exception as e:  # noqa: BLE001
            self.statusBar().showMessage(f"device_clients 조회 실패: {e}", 3000)
            return

        dc = None
        for item in dc_list:
            if item.get("device_no") == settings.device_no:
                dc = item
                break
        if not dc:
            self.statusBar().showMessage(
                f"device_no={settings.device_no} 에 해당하는 device_client 없음",
                4000,
            )
            self.table_conns.setRowCount(0)
            return

        devices_ids_str = dc.get("devices_ids") or ""
        if not devices_ids_str:
            self.table_conns.setRowCount(0)
            return
        try:
            target_ids = [
                int(x.strip())
                for x in devices_ids_str.split(",")
                if x.strip()
            ]
        except ValueError:
            self.statusBar().showMessage("devices_ids 파싱 실패", 3000)
            return

        try:
            all_devices = self.api.list_devices()
        except Exception as e:  # noqa: BLE001
            self.statusBar().showMessage(f"devices 조회 실패: {e}", 3000)
            return

        dev_by_id: dict[int, dict] = {
            int(d.get("id")): d for d in all_devices if d.get("id") is not None
        }

        rows: list[dict] = []
        for did in target_ids:
            d = dev_by_id.get(did)
            if not d:
                continue

            connected_now = False
            ctype = (d.get("connection_type") or "").lower()
            if ctype == "serial":
                connected_now = self.arduino is not None
            elif ctype == "ethernet":
                dtype = d.get("type") or ""
                if dtype == "gate_controller":
                    connected_now = (
                        self.esp_boards is not None and self.esp_boards.has_any_connection()
                    )
                elif dtype == "lpr_camera_server":
                    # 1차: UDP 프레임 기준
                    connected_now = (
                        self.esp32 is not None and self.esp32.has_recent_frame(timeout_sec=5.0)
                    )
                    # 2차: UDP 가 조용할 때 REST 헬스체크로 보조 판단
                    if not connected_now:
                        connected_now = self._check_lpr_http_alive(d)

            # DB 의 is_connected 와 다르면 서버에 반영
            if bool(d.get("is_connected")) != connected_now:
                try:
                    self.api.update_device_is_connected(d, connected_now)
                    d["is_connected"] = connected_now
                except Exception:
                    # 실패해도 UI에는 현재 상태를 그대로 표시
                    d["is_connected"] = connected_now

            rows.append(d)

        # 테이블 갱신
        self.table_conns.setRowCount(len(rows))
        for row, d in enumerate(rows):
            self.table_conns.setItem(
                row,
                0,
                QTableWidgetItem(str(d.get("id", ""))),
            )
            self.table_conns.setItem(
                row,
                1,
                QTableWidgetItem(d.get("name", "")),
            )
            self.table_conns.setItem(
                row,
                2,
                QTableWidgetItem(d.get("type", "")),
            )

            conn_parts: list[str] = []
            if d.get("connection_type"):
                conn_parts.append(str(d.get("connection_type")))
            if d.get("connection_detail"):
                conn_parts.append(str(d.get("connection_detail")))
            if d.get("control_method"):
                conn_parts.append(str(d.get("control_method")))
            conn_str = " / ".join(conn_parts) if conn_parts else ""
            self.table_conns.setItem(row, 3, QTableWidgetItem(conn_str))

            self.table_conns.setItem(
                row,
                4,
                QTableWidgetItem(d.get("port_info", "") or ""),
            )

            is_conn = bool(d.get("is_connected"))
            status_item = QTableWidgetItem("연결됨" if is_conn else "미연결")
            status_item.setBackground(
                Qt.GlobalColor.darkGreen if is_conn else Qt.GlobalColor.darkRed,
            )
            self.table_conns.setItem(row, 5, status_item)

    # ───────── 슬롯/카메라 업데이트 (UI 쓰레드) ─────────
    def handle_slot_updated_ui(self, slot_name: str, occupied: bool) -> None:
        # 서버에 먼저 반영
        self.api.set_slot_occupied(slot_name, occupied)

        # 테이블에서도 상태 반영
        for row in range(self.table_slots.rowCount()):
            item = self.table_slots.item(row, 0)
            if not item:
                continue
            if item.text() == slot_name:
                status_item = self.table_slots.item(row, 2)
                if status_item is None:
                    status_item = QTableWidgetItem()
                    self.table_slots.setItem(row, 2, status_item)
                status_item.setText("주차 중" if occupied else "빈 자리")
                if occupied:
                    status_item.setBackground(Qt.GlobalColor.red)
                else:
                    status_item.setBackground(Qt.GlobalColor.darkGreen)
                break

    def handle_camera_frame_ui(self, frame_no: int, img: object) -> None:
        if not isinstance(img, np.ndarray):
            return
        # OpenCV BGR → Qt RGB 변환
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg)
        self.label_camera_view.setPixmap(pix.scaled(
            self.label_camera_view.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
        self.label_camera.setText(f"ESP32 카메라: 프레임 {frame_no}")

    # ───────── 제어 버튼 ─────────
    def send_gate_open(self) -> None:
        # 아두이노 프로토콜 예시: "CMD,GATE,OPEN"
        if self.arduino:
            self.arduino.send_command("CMD,GATE,OPEN")
            self.statusBar().showMessage("차단기 열기 명령 전송", 2000)

    # ───────── 종료 처리 ─────────
    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.esp32:
            self.esp32.stop()
        if self.esp_boards:
            self.esp_boards.stop()
        if self.arduino:
            self.arduino.close()
        self.api.close()
        super().closeEvent(event)


def run_device_dashboard() -> None:
    import sys

    app = QApplication(sys.argv)
    win = DeviceDashboardWindow()
    win.show()
    sys.exit(app.exec())

