from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget


class ResidentManagerWindow(QMainWindow):
    """
    입주민 / 차량 / RFID 관리 화면.

    현재는 센서 관리 UI만 우선 구현되어 있어,
    이 창은 간단한 플레이스홀더로 두었습니다.
    추후 필요 시 상세 CRUD 기능을 채워 넣으면 됩니다.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("입주민 / 차량 / RFID 관리 (준비중)")
        self.resize(600, 400)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout()
        root.setLayout(layout)

        label = QLabel("입주민 / 차량 / RFID 관리 화면은 추후 확장 예정입니다.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from api_client import ApiClient


class ResidentEditDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        initial: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("입주민 정보 편집")
        self.setModal(True)

        form = QFormLayout()

        self.edit_unit = QLineEdit()
        self.edit_name = QLineEdit()
        self.edit_phone = QLineEdit()
        self.edit_plate = QLineEdit()

        form.addRow("세대(호수)", self.edit_unit)
        form.addRow("입주민 이름", self.edit_name)
        form.addRow("연락처", self.edit_phone)
        form.addRow("차량 번호", self.edit_plate)

        if initial:
            self.edit_unit.setText(initial.get("unit_number", ""))
            self.edit_name.setText(initial.get("name", ""))
            self.edit_phone.setText(initial.get("phone", ""))
            self.edit_plate.setText(initial.get("car_plate", ""))

        btn_box = QHBoxLayout()
        btn_ok = QPushButton("저장")
        btn_cancel = QPushButton("취소")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(btn_ok)
        btn_box.addWidget(btn_cancel)

        root = QVBoxLayout()
        root.addLayout(form)
        root.addLayout(btn_box)
        self.setLayout(root)

    def get_payload(self) -> Dict[str, Any]:
        return {
            "unit_number": self.edit_unit.text().strip(),
            "name": self.edit_name.text().strip(),
            "phone": self.edit_phone.text().strip(),
            "car_plate": self.edit_plate.text().strip(),
        }


class ResidentManagerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.api = ApiClient()
        self.setWindowTitle("입주민 / 차량 / RFID 관리")
        self.resize(1000, 600)

        root = QWidget()
        self.setCentralWidget(root)

        main_layout = QVBoxLayout()
        root.setLayout(main_layout)

        title = QLabel("입주민 / 차량 / RFID 관리")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff;")

        main_layout.addWidget(title)

        splitter = QSplitter()
        splitter.setOrientation(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, 1)

        # ── 좌측: 입주민 테이블 ────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout()
        left.setLayout(left_layout)

        label_res = QLabel("입주민 / 차량 목록")
        label_res.setStyleSheet("font-weight: bold; color: #ffffff;")
        left_layout.addWidget(label_res)

        self.table_residents = QTableWidget(0, 5)
        self.table_residents.setHorizontalHeaderLabels(
            ["ID", "세대", "이름", "연락처", "차량번호"]
        )
        self.table_residents.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table_residents.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        left_layout.addWidget(self.table_residents)

        btn_row_res = QHBoxLayout()
        self.btn_add_res = QPushButton("추가")
        self.btn_edit_res = QPushButton("수정")
        self.btn_del_res = QPushButton("삭제")
        btn_row_res.addWidget(self.btn_add_res)
        btn_row_res.addWidget(self.btn_edit_res)
        btn_row_res.addWidget(self.btn_del_res)
        btn_row_res.addStretch()
        left_layout.addLayout(btn_row_res)

        splitter.addWidget(left)

        # ── 우측: RFID 카드 목록 ───────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout()
        right.setLayout(right_layout)

        label_rfid = QLabel("RFID 카드 목록")
        label_rfid.setStyleSheet("font-weight: bold; color: #ffffff;")
        right_layout.addWidget(label_rfid)

        self.table_rfid = QTableWidget(0, 5)
        self.table_rfid.setHorizontalHeaderLabels(
            ["ID", "카드 UID", "입주민 ID", "활성 여부", "설명"],
        )
        self.table_rfid.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        right_layout.addWidget(self.table_rfid)

        btn_row_rfid = QHBoxLayout()
        self.btn_add_rfid = QPushButton("추가")
        self.btn_edit_rfid = QPushButton("수정")
        self.btn_del_rfid = QPushButton("삭제")
        btn_row_rfid.addWidget(self.btn_add_rfid)
        btn_row_rfid.addWidget(self.btn_edit_rfid)
        btn_row_rfid.addWidget(self.btn_del_rfid)
        btn_row_rfid.addStretch()
        right_layout.addLayout(btn_row_rfid)

        splitter.addWidget(right)
        splitter.setSizes([500, 500])

        # 이벤트 연결
        self.btn_add_res.clicked.connect(self._on_add_resident)
        self.btn_edit_res.clicked.connect(self._on_edit_resident)
        self.btn_del_res.clicked.connect(self._on_delete_resident)

        self.btn_add_rfid.clicked.connect(self._on_add_rfid)
        self.btn_edit_rfid.clicked.connect(self._on_edit_rfid)
        self.btn_del_rfid.clicked.connect(self._on_delete_rfid)

        self._load_all()

    # ── 데이터 로드 / 테이블 갱신 ─────────────────────────────────────
    def _load_all(self) -> None:
        try:
            residents = self.api.list_residents()
            rfid_cards = self.api.list_rfid_cards()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "오류", f"서버 통신 오류: {exc}")
            return

        self._update_resident_table(residents)
        self._update_rfid_table(rfid_cards)

    def _update_resident_table(self, items: List[Dict[str, Any]]) -> None:
        self.table_residents.setRowCount(len(items))
        for row, res in enumerate(items):
            self.table_residents.setItem(
                row,
                0,
                QTableWidgetItem(str(res.get("id", ""))),
            )
            self.table_residents.setItem(
                row,
                1,
                QTableWidgetItem(res.get("unit_number", "")),
            )
            self.table_residents.setItem(
                row,
                2,
                QTableWidgetItem(res.get("name", "")),
            )
            self.table_residents.setItem(
                row,
                3,
                QTableWidgetItem(res.get("phone", "")),
            )
            self.table_residents.setItem(
                row,
                4,
                QTableWidgetItem(res.get("car_plate", "")),
            )

    def _update_rfid_table(self, items: List[Dict[str, Any]]) -> None:
        self.table_rfid.setRowCount(len(items))
        for row, card in enumerate(items):
            self.table_rfid.setItem(
                row,
                0,
                QTableWidgetItem(str(card.get("id", ""))),
            )
            self.table_rfid.setItem(
                row,
                1,
                QTableWidgetItem(card.get("card_uid", "")),
            )
            self.table_rfid.setItem(
                row,
                2,
                QTableWidgetItem(
                    str(card.get("resident_id")) if card.get("resident_id") else "",
                ),
            )
            self.table_rfid.setItem(
                row,
                3,
                QTableWidgetItem("활성" if card.get("is_active") else "비활성"),
            )
            self.table_rfid.setItem(
                row,
                4,
                QTableWidgetItem(card.get("description", "") or ""),
            )

    def _get_selected_row_id(self, table: QTableWidget) -> Optional[int]:
        row = table.currentRow()
        if row < 0:
            return None
        item = table.item(row, 0)
        if not item:
            return None
        try:
            return int(item.text())
        except ValueError:
            return None

    # ── 입주민 CRUD 핸들러 ───────────────────────────────────────────
    def _on_add_resident(self) -> None:
        dlg = ResidentEditDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dlg.get_payload()
        try:
            self.api.create_resident(payload)
            self._load_all()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "오류", f"입주민 추가 실패: {exc}")

    def _on_edit_resident(self) -> None:
        res_id = self._get_selected_row_id(self.table_residents)
        if res_id is None:
            QMessageBox.information(self, "안내", "수정할 입주민을 선택하세요.")
            return

        row = self.table_residents.currentRow()
        initial = {
            "unit_number": self.table_residents.item(row, 1).text(),
            "name": self.table_residents.item(row, 2).text(),
            "phone": self.table_residents.item(row, 3).text(),
            "car_plate": self.table_residents.item(row, 4).text(),
        }
        dlg = ResidentEditDialog(self, initial=initial)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        payload = dlg.get_payload()
        try:
            self.api.update_resident(res_id, payload)
            self._load_all()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "오류", f"입주민 수정 실패: {exc}")

    def _on_delete_resident(self) -> None:
        res_id = self._get_selected_row_id(self.table_residents)
        if res_id is None:
            QMessageBox.information(self, "안내", "삭제할 입주민을 선택하세요.")
            return
        if (
            QMessageBox.question(
                self,
                "확인",
                "선택한 입주민을 삭제하시겠습니까? 연결된 RFID 카드도 함께 삭제됩니다.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self.api.delete_resident(res_id)
            self._load_all()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "오류", f"입주민 삭제 실패: {exc}")

    # ── RFID CRUD 핸들러 ────────────────────────────────────────────
    def _on_add_rfid(self) -> None:
        uid, ok = QInputDialog.getText(self, "RFID 추가", "카드 UID:")
        if not ok or not uid:
            return
        payload: Dict[str, Any] = {
            "card_uid": uid.strip(),
            "resident_id": None,
            "is_active": True,
            "description": "",
        }
        try:
            self.api.create_rfid_card(payload)
            self._load_all()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "오류", f"RFID 추가 실패: {exc}")

    def _on_edit_rfid(self) -> None:
        card_id = self._get_selected_row_id(self.table_rfid)
        if card_id is None:
            QMessageBox.information(self, "안내", "수정할 RFID 카드를 선택하세요.")
            return

        row = self.table_rfid.currentRow()
        uid_item = self.table_rfid.item(row, 1)
        resident_item = self.table_rfid.item(row, 2)
        active_item = self.table_rfid.item(row, 3)
        desc_item = self.table_rfid.item(row, 4)

        from PyQt6.QtWidgets import QInputDialog  # local import to avoid circular issues

        uid, ok = QInputDialog.getText(
            self,
            "RFID 수정",
            "카드 UID:",
            text=uid_item.text() if uid_item else "",
        )
        if not ok or not uid:
            return

        resident_text = resident_item.text() if resident_item else ""
        resident_id: Optional[int] = None
        if resident_text:
            try:
                resident_id = int(resident_text)
            except ValueError:
                resident_id = None

        is_active = (active_item.text() if active_item else "") == "활성"

        desc, ok_desc = QInputDialog.getText(
            self,
            "RFID 설명",
            "설명:",
            text=desc_item.text() if desc_item else "",
        )
        if not ok_desc:
            return

        payload: Dict[str, Any] = {
            "card_uid": uid.strip(),
            "resident_id": resident_id,
            "is_active": is_active,
            "description": desc.strip(),
        }

        try:
            self.api.update_rfid_card(card_id, payload)
            self._load_all()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "오류", f"RFID 수정 실패: {exc}")

    def _on_delete_rfid(self) -> None:
        card_id = self._get_selected_row_id(self.table_rfid)
        if card_id is None:
            QMessageBox.information(self, "안내", "삭제할 RFID 카드를 선택하세요.")
            return

        if (
            QMessageBox.question(
                self,
                "확인",
                "선택한 RFID 카드를 삭제하시겠습니까?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            self.api.delete_rfid_card(card_id)
            self._load_all()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "오류", f"RFID 삭제 실패: {exc}")

