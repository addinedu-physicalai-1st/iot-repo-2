from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTabWidget, QWidget, QFormLayout, QLabel,
    QSpinBox, QPushButton, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView
)
from models import TOTAL_PLATES


class AdminDialog(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle("관리자 화면")
        self.resize(760, 560)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        status_tab = QWidget()
        status_layout = QFormLayout(status_tab)
        self.lbl_homed = QLabel("-")
        self.lbl_sensor = QLabel("-")
        self.lbl_step_pos = QLabel("-")
        self.lbl_current_plate = QLabel("-")
        self.btn_home = QPushButton("초기 홈 설정")
        self.btn_home.clicked.connect(self.home_tower)
        status_layout.addRow("홈 완료", self.lbl_homed)
        status_layout.addRow("근접센서 상태", self.lbl_sensor)
        status_layout.addRow("현재 스텝 위치", self.lbl_step_pos)
        status_layout.addRow("현재 1층 차판", self.lbl_current_plate)
        status_layout.addRow("장치 초기화", self.btn_home)
        tabs.addTab(status_tab, "장치 상태")

        motor_tab = QWidget()
        motor_layout = QFormLayout(motor_tab)
        self.spin_steps = QSpinBox()
        self.spin_steps.setRange(1, 100000)
        self.spin_steps.setValue(self.main_window.steps_per_plate)
        self.btn_apply_steps = QPushButton("스텝 수 적용")
        self.btn_apply_steps.clicked.connect(self.apply_steps)
        motor_layout.addRow("차판당 스텝 수", self.spin_steps)
        motor_layout.addRow(self.btn_apply_steps)
        tabs.addTab(motor_tab, "모터 설정")

        car_tab = QWidget()
        car_layout = QVBoxLayout(car_tab)
        self.car_table = QTableWidget(TOTAL_PLATES, 2)
        self.car_table.setHorizontalHeaderLabels(["차판", "차량번호"])
        self.car_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        car_layout.addWidget(self.car_table)
        self.btn_save_cars = QPushButton("차량번호 수정 저장")
        self.btn_save_cars.clicked.connect(self.save_cars)
        car_layout.addWidget(self.btn_save_cars)
        tabs.addTab(car_tab, "차량 정보 수정")

        self.refresh()

    def refresh(self):
        st = self.main_window.arduino.last_status
        self.lbl_homed.setText("완료" if st.get("homed") else "미완료")
        self.lbl_sensor.setText("감지됨" if st.get("sensor") else "미감지")
        self.lbl_step_pos.setText(str(st.get("stepPos")))
        self.lbl_current_plate.setText(str(st.get("plate")))

        for i, plate in enumerate(self.main_window.plates):
            item0 = QTableWidgetItem(str(i))
            item0.setFlags(item0.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.car_table.setItem(i, 0, item0)
            self.car_table.setItem(i, 1, QTableWidgetItem(plate.car_number))

    def home_tower(self):
        self.main_window.home_tower()
        self.refresh()
        QMessageBox.information(self, "완료", "초기 홈 설정을 실행했습니다.")

    def apply_steps(self):
        value = self.spin_steps.value()
        self.main_window.steps_per_plate = value
        self.main_window.arduino.send(f"SET_STEPS={value}")
        QMessageBox.information(self, "완료", "스텝 수를 적용했습니다.")

    def save_cars(self):
        for i in range(TOTAL_PLATES):
            text = self.car_table.item(i, 1).text().strip() if self.car_table.item(i, 1) else ""
            self.main_window.plates[i].car_number = text
        self.main_window.refresh_ui()
        QMessageBox.information(self, "완료", "차량번호를 수정했습니다.")
