from typing import Any, Dict, List

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from api_client import ApiClient


class SensorEditDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        initial: Dict[str, Any] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("센서 정보 편집")
        self.setModal(True)

        form = QFormLayout()

        self.edit_guid = QLineEdit()
        self.edit_name = QLineEdit()
        self.edit_type = QLineEdit()
        self.edit_created_by = QLineEdit()

        form.addRow("센서 GUID", self.edit_guid)
        form.addRow("센서 이름", self.edit_name)
        form.addRow("센서 종류", self.edit_type)
        form.addRow("등록한 사람", self.edit_created_by)

        if initial:
            self.edit_guid.setText(initial.get("guid", ""))
            self.edit_name.setText(initial.get("name", ""))
            self.edit_type.setText(initial.get("sensor_type", ""))
            self.edit_created_by.setText(initial.get("created_by", ""))

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("저장")
        btn_cancel = QPushButton("취소")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)

        root = QVBoxLayout()
        root.addLayout(form)
        root.addLayout(btn_row)
        self.setLayout(root)

    def get_payload(self) -> Dict[str, Any]:
        return {
            "guid": self.edit_guid.text().strip(),
            "name": self.edit_name.text().strip(),
            "sensor_type": self.edit_type.text().strip(),
            "is_active": True,
            "created_by": self.edit_created_by.text().strip() or "ui",
        }


class SensorManagerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.api = ApiClient()
        self.setWindowTitle("센서 관리")
        self.resize(800, 500)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout()
        root.setLayout(layout)

        title = QLabel("센서 관리 (카메라 / IR / RFID / 게이트)")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "GUID", "이름", "종류", "사용 여부", "등록자"],
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.btn_reload = QPushButton("새로고침")
        self.btn_add = QPushButton("추가")
        self.btn_edit = QPushButton("수정")
        self.btn_deactivate = QPushButton("비활성화")

        btn_row.addWidget(self.btn_reload)
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_edit)
        btn_row.addWidget(self.btn_deactivate)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.btn_reload.clicked.connect(self.load_sensors)
        self.btn_add.clicked.connect(self.add_sensor)
        self.btn_edit.clicked.connect(self.edit_sensor)
        self.btn_deactivate.clicked.connect(self.deactivate_sensor)

        self.load_sensors()

    def load_sensors(self) -> None:
        try:
            sensors: List[Dict[str, Any]] = self.api.list_sensors()
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "오류", f"센서 목록 불러오기 실패: {e}")
            return

        self.table.setRowCount(len(sensors))
        for row, s in enumerate(sensors):
            self.table.setItem(row, 0, QTableWidgetItem(str(s.get("id", ""))))
            self.table.setItem(row, 1, QTableWidgetItem(s.get("guid", "")))
            self.table.setItem(row, 2, QTableWidgetItem(s.get("name", "")))
            self.table.setItem(row, 3, QTableWidgetItem(s.get("sensor_type", "")))
            self.table.setItem(
                row,
                4,
                QTableWidgetItem("사용" if s.get("is_active") else "미사용"),
            )
            self.table.setItem(
                row,
                5,
                QTableWidgetItem(s.get("created_by", "")),
            )

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        try:
            return int(item.text())
        except ValueError:
            return None

    def add_sensor(self) -> None:
        dlg = SensorEditDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dlg.get_payload()
        try:
            self.api.create_sensor(payload)
            self.load_sensors()
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "오류", f"센서 추가 실패: {e}")

    def edit_sensor(self) -> None:
        sensor_id = self._selected_id()
        if sensor_id is None:
            QMessageBox.information(self, "안내", "수정할 센서를 선택하세요.")
            return
        row = self.table.currentRow()
        initial = {
            "guid": self.table.item(row, 1).text(),
            "name": self.table.item(row, 2).text(),
            "sensor_type": self.table.item(row, 3).text(),
            "created_by": self.table.item(row, 5).text(),
        }
        dlg = SensorEditDialog(self, initial=initial)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dlg.get_payload()
        try:
            self.api.update_sensor(sensor_id, payload)
            self.load_sensors()
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "오류", f"센서 수정 실패: {e}")

    def deactivate_sensor(self) -> None:
        sensor_id = self._selected_id()
        if sensor_id is None:
            QMessageBox.information(self, "안내", "비활성화할 센서를 선택하세요.")
            return
        if (
            QMessageBox.question(
                self,
                "확인",
                "선택한 센서를 비활성화하시겠습니까?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self.api.deactivate_sensor(sensor_id)
            self.load_sensors()
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "오류", f"센서 비활성화 실패: {e}")

