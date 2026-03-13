import math
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QLineEdit, QMessageBox, QListWidget, QListWidgetItem, QGroupBox,
    QFormLayout, QDialog
)

from models import PlateInfo, TOTAL_PLATES
from serial_controller import ArduinoClient
from parking_logic import ParkingController
from admin_dialog import AdminDialog

ADMIN_PASSWORD = "1234"



class RotaryBlueprintWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.plates = []
        self.current_floor_plate = 0          # 실제 1층 위치 차판
        self.display_bay_plate = 0.0          # 화면 애니메이션용 차판 위치
        self.target_bay_plate = 0.0
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.animate_step)
        self.setMinimumSize(640, 640)

    def set_data(self, plates, current_floor_plate):
        self.plates = plates
        self.current_floor_plate = current_floor_plate

        # 애니메이션이 아닐 때는 화면 기준도 실제 차판과 맞춘다
        if not self.anim_timer.isActive():
            self.display_bay_plate = float(current_floor_plate)
            self.target_bay_plate = float(current_floor_plate)

        self.update()

    def animate_to_plate(self, target_plate):
        # 6시 방향(하단)이 항상 홈/1층 위치가 되도록
        # "어느 차판이 하단에 와야 하는가" 자체를 애니메이션한다.
        self.target_bay_plate = float(target_plate)
        if not self.anim_timer.isActive():
            self.anim_timer.start(20)

    def animate_step(self):
        diff = self.target_bay_plate - self.display_bay_plate
        if abs(diff) < 0.01:
            self.display_bay_plate = self.target_bay_plate
            self.anim_timer.stop()
            self.update()
            return

        # 부드럽게 이동
        self.display_bay_plate += diff * 0.16
        self.update()

    def draw_blueprint_grid(self, painter):
        painter.fillRect(self.rect(), QColor("#0d1b2a"))
        painter.setPen(QPen(QColor(60, 90, 130, 80), 1))
        step = 28
        for x in range(0, self.width(), step):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), step):
            painter.drawLine(0, y, self.width(), y)

    def paintEvent(self, event):
        if not self.plates:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.draw_blueprint_grid(painter)

        cx = self.width() / 2
        cy = self.height() / 2 - 30
        orbit_r = min(self.width(), self.height()) * 0.30
        car_w, car_h = 116, 44

        # 구조 원 / 프레임
        painter.setPen(QPen(QColor("#5ec8ff"), 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(cx - orbit_r - 56, cy - orbit_r - 56, (orbit_r + 56) * 2, (orbit_r + 56) * 2))
        painter.setPen(QPen(QColor("#2fb5ff"), 2, Qt.PenStyle.DashLine))
        painter.drawEllipse(QRectF(cx - orbit_r, cy - orbit_r, orbit_r * 2, orbit_r * 2))

        # 중심축
        painter.setPen(QPen(QColor("#8be0ff"), 3))
        painter.setBrush(QBrush(QColor("#13314d")))
        painter.drawEllipse(QRectF(cx - 72, cy - 72, 144, 144))
        painter.setFont(QFont("Sans", 13, QFont.Weight.Bold))
        painter.drawText(QRectF(cx - 70, cy - 18, 140, 36), Qt.AlignmentFlag.AlignCenter, "ROTARY TOWER")

        # 중심 십자선
        painter.setPen(QPen(QColor("#5ec8ff"), 1, Qt.PenStyle.DashLine))
        painter.drawLine(int(cx), int(cy - orbit_r - 70), int(cx), int(cy + orbit_r + 70))
        painter.drawLine(int(cx - orbit_r - 70), int(cy), int(cx + orbit_r + 70), int(cy))

        step_angle = 360 / TOTAL_PLATES
        bay_plate = self.current_floor_plate

        for plate in self.plates:
            # display_bay_plate 가 하단(270도, 6시 방향)에 온다.
            angle_deg = 90 + (self.display_bay_plate - plate.plate_id) * step_angle
            rad = math.radians(angle_deg)
            x = cx + orbit_r * math.cos(rad)
            y = cy + orbit_r * math.sin(rad)

            is_bottom = (plate.plate_id == bay_plate)

            rect = QRectF(x - car_w / 2, y - car_h / 2, car_w, car_h)
            painter.setPen(QPen(QColor("#9ae6ff") if is_bottom else QColor("#5ec8ff"), 3 if is_bottom else 2))
            painter.setBrush(QBrush(QColor("#14324f") if not is_bottom else QColor("#1e4d73")))
            painter.drawRoundedRect(rect, 8, 8)

            inner = QRectF(x - car_w / 2 + 10, y - car_h / 2 + 8, car_w - 20, car_h - 16)
            painter.setPen(QPen(QColor("#7dd3fc"), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(inner, 5, 5)

            painter.setFont(QFont("Sans", 9, QFont.Weight.Bold))
            painter.drawText(QRectF(x - 50, y - 18, 36, 16), Qt.AlignmentFlag.AlignCenter, f"P{plate.plate_id}")

            if plate.car_number:
                painter.setFont(QFont("Sans", 10, QFont.Weight.Bold))
                painter.drawText(QRectF(x - 28, y - 10, 56, 20), Qt.AlignmentFlag.AlignCenter, "CAR")
                painter.setFont(QFont("Sans", 8))
                painter.drawText(QRectF(x - 50, y + 8, 100, 12), Qt.AlignmentFlag.AlignCenter, plate.car_number[:10])
            else:
                painter.setFont(QFont("Sans", 8))
                painter.drawText(QRectF(x - 50, y - 6, 100, 12), Qt.AlignmentFlag.AlignCenter, "EMPTY")

            if is_bottom:
                painter.setPen(QPen(QColor("#ffe082"), 2))
                painter.drawRoundedRect(QRectF(x - car_w / 2 - 5, y - car_h / 2 - 5, car_w + 10, car_h + 10), 10, 10)

        # 하단 1층 입출고 베이
        bay_w, bay_h = 280, 82
        bay_x = cx - bay_w / 2
        bay_y = self.height() - 118

        painter.setPen(QPen(QColor("#ffe082"), 3))
        painter.setBrush(QBrush(QColor("#3b2f0b")))
        painter.drawRoundedRect(QRectF(bay_x, bay_y, bay_w, bay_h), 10, 10)

        painter.setPen(QPen(QColor("#ffe082"), 2, Qt.PenStyle.DashLine))
        painter.drawLine(int(bay_x - 80), int(bay_y + bay_h / 2), int(bay_x), int(bay_y + bay_h / 2))
        painter.drawLine(int(bay_x + bay_w), int(bay_y + bay_h / 2), int(bay_x + bay_w + 80), int(bay_y + bay_h / 2))

        painter.setPen(QPen(QColor("#fff1a8"), 1))
        painter.setFont(QFont("Sans", 13, QFont.Weight.Bold))
        painter.drawText(QRectF(bay_x, bay_y + 8, bay_w, 24), Qt.AlignmentFlag.AlignCenter, "1층 입출고 위치")
        painter.setFont(QFont("Sans", 10))
        painter.drawText(QRectF(bay_x, bay_y + 38, bay_w, 18), Qt.AlignmentFlag.AlignCenter, f"현재 호출 차판 : P{bay_plate}")

        current_car = ""
        for p in self.plates:
            if p.plate_id == bay_plate:
                current_car = p.car_number
                break
        painter.drawText(QRectF(bay_x, bay_y + 56, bay_w, 16), Qt.AlignmentFlag.AlignCenter, current_car if current_car else "빈 차판")

        painter.setPen(QPen(QColor("#9ae6ff"), 1))
        painter.setFont(QFont("Sans", 16, QFont.Weight.Bold))
        painter.drawText(QRectF(20, 18, self.width() - 40, 24), Qt.AlignmentFlag.AlignLeft, "ROTARY PARKING TOWER BLUEPRINT VIEW")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("로터리 주차타워 제어 UI - Blueprint View")
        self.resize(1360, 860)

        self.arduino = ArduinoClient()
        self.steps_per_plate = 400
        self.plates = [PlateInfo(i) for i in range(TOTAL_PLATES)]
        self.current_floor_plate = 0

        self.logic = ParkingController(
            self.plates,
            self.arduino,
            log_callback=self.add_log,
            move_callback=self.animate_move_request
        )

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        left_layout = QVBoxLayout()
        right_layout = QVBoxLayout()
        root.addLayout(left_layout, 3)
        root.addLayout(right_layout, 2)

        tower_group = QGroupBox("로터리 주차타워 도면 화면")
        tower_layout = QVBoxLayout(tower_group)
        self.rotary_widget = RotaryBlueprintWidget()
        tower_layout.addWidget(self.rotary_widget)
        left_layout.addWidget(tower_group)

        self.lbl_move_state = QLabel("대기 중")
        self.lbl_move_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_move_state.setStyleSheet(
            "font-size:20px; font-weight:bold; padding:8px; border:1px solid #2fb5ff; border-radius:8px; background:#11263a; color:#d6f4ff;"
        )
        left_layout.addWidget(self.lbl_move_state)

        control_group = QGroupBox("차량 제어")
        control_layout = QVBoxLayout(control_group)

        form_group = QGroupBox("입출고 입력")
        form_layout = QFormLayout(form_group)
        self.input_car = QLineEdit()
        self.input_car.setPlaceholderText("차량번호 입력 예: 12가3456")
        form_layout.addRow("차량번호", self.input_car)
        control_layout.addWidget(form_group)

        row2 = QHBoxLayout()
        self.btn_out = QPushButton("출고")
        self.btn_out.clicked.connect(self.retrieve_car)
        self.btn_park = QPushButton("입고")
        self.btn_park.clicked.connect(self.park_car)
        row2.addWidget(self.btn_park)
        row2.addWidget(self.btn_out)
        control_layout.addLayout(row2)

        row3 = QHBoxLayout()
        self.btn_emg = QPushButton("비상정지")
        self.btn_emg.clicked.connect(self.toggle_emergency)
        self.btn_admin = QPushButton("관리자 화면")
        self.btn_admin.clicked.connect(self.open_admin)
        row3.addWidget(self.btn_emg)
        row3.addWidget(self.btn_admin)
        control_layout.addLayout(row3)

        lamp_group = QGroupBox("램프 상태")
        lamp_layout = QHBoxLayout(lamp_group)
        self.lbl_green = QLabel("초록램프")
        self.lbl_red = QLabel("빨간램프")
        for lbl in (self.lbl_green, self.lbl_red):
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedHeight(54)
            lamp_layout.addWidget(lbl)
        control_layout.addWidget(lamp_group)

        log_group = QGroupBox("로그")
        log_layout = QVBoxLayout(log_group)
        self.log_list = QListWidget()
        log_layout.addWidget(self.log_list)
        control_layout.addWidget(log_group)

        right_layout.addWidget(control_group)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_status)
        self.timer.start(1000)

        self.apply_global_style()
        self.refresh_ui()
        self.add_log("프로그램 시작")

    def apply_global_style(self):
        self.setStyleSheet("""
        QWidget {
            background-color: #091521;
            color: #d6f4ff;
            font-size: 14px;
        }
        QGroupBox {
            background-color: #11263a;
            color: #d6f4ff;
            font-weight: bold;
            border: 1px solid #2f6f96;
            border-radius: 10px;
            margin-top: 12px;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 4px 0 4px;
        }
        QPushButton {
            background-color: #1b75bc;
            color: #ffffff;
            padding: 8px;
            border-radius: 8px;
            font-weight: bold;
            border: 1px solid #5ec8ff;
        }
        QPushButton:hover {
            background-color: #2893e0;
        }
        QLineEdit {
            background-color: #0d1b2a;
            color: #ffffff;
            border: 1px solid #4d7fa1;
            border-radius: 6px;
            padding: 6px;
        }
        QListWidget {
            background-color: #0d1b2a;
            color: #e8fbff;
            border: 1px solid #2f6f96;
            border-radius: 8px;
        }
        QLabel {
            color: #d6f4ff;
        }
        QTableWidget {
            background-color: #0d1b2a;
            color: #ffffff;
            gridline-color: #2f6f96;
            border: 1px solid #2f6f96;
        }
        QHeaderView::section {
            background-color: #173754;
            color: #ffffff;
            border: 1px solid #2f6f96;
            padding: 4px;
        }
        QTabWidget::pane {
            border: 1px solid #2f6f96;
        }
        QTabBar::tab {
            background: #173754;
            color: #ffffff;
            padding: 8px 12px;
            border: 1px solid #2f6f96;
        }
        QTabBar::tab:selected {
            background: #1b75bc;
        }
        """)

    def add_log(self, text: str):
        self.log_list.insertItem(0, QListWidgetItem(text))

    def animate_move_request(self, plate_id: int):
        self.lbl_move_state.setText(f"차판 P{plate_id} 회전 이동 중")
        self.rotary_widget.animate_to_plate(plate_id)

    def refresh_ui(self):
        self.current_floor_plate = int(self.arduino.last_status.get("plate", self.current_floor_plate))
        self.rotary_widget.set_data(self.plates, self.current_floor_plate)

        moving = bool(self.arduino.last_status.get("moving", 0))
        emergency = bool(self.arduino.last_status.get("emergency", 0))
        full = self.logic.is_full()

        if emergency:
            self.lbl_move_state.setText("비상정지 상태")
        elif full:
            self.lbl_move_state.setText("만차")
        elif moving:
            self.lbl_move_state.setText("회전 이동 중")
        else:
            self.lbl_move_state.setText("대기 중")

        green_on = (not moving) and (not emergency) and (not full)
        self.lbl_green.setStyleSheet(
            f"border:1px solid #5ec8ff; border-radius:8px; font-weight:bold; background:{'#3cbf5b' if green_on else '#6b7280'}; color:#ffffff;"
        )
        self.lbl_red.setStyleSheet(
            f"border:1px solid #5ec8ff; border-radius:8px; font-weight:bold; background:{'#e74c3c' if not green_on else '#6b7280'}; color:#ffffff;"
        )

    def poll_status(self):
        self.arduino.send("STATUS")
        self.logic.set_full_status()
        self.refresh_ui()

    def home_tower(self):
        lines = self.arduino.send("HOME")
        for line in lines:
            self.add_log(line)
        self.rotary_widget.display_bay_plate = 0.0
        self.rotary_widget.target_bay_plate = 0.0
        self.refresh_ui()

    def park_car(self):
        ok, msg = self.logic.park_car(self.input_car.text().strip())
        if not ok:
            QMessageBox.warning(self, "입고", msg)
        else:
            self.input_car.clear()
        self.refresh_ui()

    def retrieve_car(self):
        ok, msg = self.logic.retrieve_car(self.input_car.text().strip())
        if not ok:
            QMessageBox.warning(self, "출고", msg)
        else:
            self.input_car.clear()
        self.refresh_ui()

    def toggle_emergency(self):
        emergency = bool(self.arduino.last_status.get("emergency", 0))
        lines = self.arduino.send("EMG_OFF" if emergency else "EMG_ON")
        for line in lines:
            self.add_log(line)
        self.refresh_ui()

    def open_admin(self):
        password, ok = self.simple_password_dialog()
        if not ok:
            return
        if password != ADMIN_PASSWORD:
            QMessageBox.warning(self, "권한 없음", "관리자 비밀번호가 틀렸습니다.")
            return

        dlg = AdminDialog(self)
        dlg.exec()
        self.refresh_ui()

    def simple_password_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("관리자 인증")
        layout = QVBoxLayout(dialog)
        edit = QLineEdit()
        edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(QLabel("관리자 비밀번호 입력"))
        layout.addWidget(edit)

        row = QHBoxLayout()
        btn_ok = QPushButton("확인")
        btn_cancel = QPushButton("취소")
        row.addWidget(btn_ok)
        row.addWidget(btn_cancel)
        layout.addLayout(row)

        result = {"ok": False}

        def accept_it():
            result["ok"] = True
            dialog.accept()

        btn_ok.clicked.connect(accept_it)
        btn_cancel.clicked.connect(dialog.reject)

        ok = dialog.exec() == QDialog.DialogCode.Accepted and result["ok"]
        return edit.text(), ok
