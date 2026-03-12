from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

import httpx

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidgetItem,
    QVBoxLayout,
    QTableWidget,
    QHeaderView,
)

from api_client import ApiClient
from ui.resident_manager import ResidentEditDialog


def _fmt_dt(value: Any) -> str:
    """ISO 문자열 또는 datetime 을 사람이 읽기 좋은 형식으로."""
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    try:
        # FastAPI 기본 ISO 포맷 가정
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)


class ParkingRecordsDialog(QDialog):
    """입·출차 기록 조회/수정 팝업."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("주차 기록 조회")
        self.resize(1100, 600)
        self._api = ApiClient()

        root = QVBoxLayout()
        self.setLayout(root)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("입차일자:"))
        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        today = date.today()
        self._date_from.setDate(today)
        self._date_to.setDate(today)
        top_row.addWidget(self._date_from)
        top_row.addWidget(QLabel("~"))
        top_row.addWidget(self._date_to)

        top_row.addWidget(QLabel("최대 레코드 수:"))
        self._spin_limit = QSpinBox()
        self._spin_limit.setRange(10, 2000)
        self._spin_limit.setValue(500)
        top_row.addWidget(self._spin_limit)

        self._btn_reload = QPushButton("새로고침")
        self._btn_reload.clicked.connect(self.reload)
        top_row.addWidget(self._btn_reload)

        self._btn_edit = QPushButton("선택 행 수정")
        self._btn_edit.clicked.connect(self._edit_selected)
        top_row.addWidget(self._btn_edit)

        top_row.addStretch()
        root.addLayout(top_row)

        self._table = QTableWidget(0, 8)
        self._table.setHorizontalHeaderLabels(
            [
                "ID",
                "번호판",
                "입차시각",
                "출차시각",
                "등록차량",
                "resident_id",
                "요금",
                "이미지",
            ]
        )
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # ID
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)           # 번호판
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)           # 입차시각
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)           # 출차시각
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # 등록차량
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # resident_id
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # 요금
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)  # 이미지
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.currentCellChanged.connect(self._on_row_changed)
        root.addWidget(self._table, 2)

        # 이미지 미리보기 영역
        img_row = QHBoxLayout()
        self._label_entry_img = QLabel("입차 이미지 미리보기")
        self._label_entry_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label_entry_img.setMinimumHeight(160)
        self._label_entry_img.setStyleSheet(
            "background-color: #252733; border: 1px solid #3a3b45; border-radius: 4px;"
        )
        img_row.addWidget(self._label_entry_img, 1)

        self._label_exit_img = QLabel("출차 이미지 미리보기")
        self._label_exit_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label_exit_img.setMinimumHeight(160)
        self._label_exit_img.setStyleSheet(
            "background-color: #252733; border: 1px solid #3a3b45; border-radius: 4px;"
        )
        img_row.addWidget(self._label_exit_img, 1)
        root.addLayout(img_row)

        btn_row = QHBoxLayout()
        self._btn_close = QPushButton("닫기")
        self._btn_close.clicked.connect(self.close)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_close)
        root.addLayout(btn_row)

        self.reload()

    def reload(self) -> None:
        limit = int(self._spin_limit.value())
        try:
            rows: List[Dict[str, Any]] = self._api.list_parking_records(limit=limit)
        except Exception as e:  # noqa: BLE001
            self._table.setRowCount(0)
            self._table.setRowCount(1)
            self._table.setItem(0, 0, QTableWidgetItem("오류"))
            self._table.setItem(0, 1, QTableWidgetItem(str(e)))
            return

        # 날짜 필터 (entry_timestamp 기준, 로컬 날짜만 비교)
        d_from = self._date_from.date().toPyDate()
        d_to = self._date_to.date().toPyDate()

        filtered: List[Dict[str, Any]] = []
        for rec in rows:
            ts_raw = rec.get("entry_timestamp")
            try:
                dt = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                d = dt.date()
            except Exception:
                d = None
            if d is not None and d_from <= d <= d_to:
                filtered.append(rec)

        self._table.setRowCount(len(filtered))
        for r, rec in enumerate(filtered):
            rid = rec.get("record_id")
            plate = rec.get("license_plate", "")
            entry_ts = _fmt_dt(rec.get("entry_timestamp"))
            exit_ts = _fmt_dt(rec.get("exit_timestamp"))
            is_reg = bool(rec.get("is_registered"))
            resident_id = rec.get("resident_id")
            charge = rec.get("charge_amount", 0)
            has_imgs = ("Y" if rec.get("entry_img_path") or rec.get("exit_img_path") else "")

            self._table.setItem(r, 0, QTableWidgetItem(str(rid)))
            self._table.setItem(r, 1, QTableWidgetItem(plate))
            self._table.setItem(r, 2, QTableWidgetItem(entry_ts))
            self._table.setItem(r, 3, QTableWidgetItem(exit_ts))

            reg_item = QTableWidgetItem("등록" if is_reg else "비등록")
            self._table.setItem(r, 4, reg_item)

            self._table.setItem(
                r,
                5,
                QTableWidgetItem("" if resident_id is None else str(resident_id)),
            )
            self._table.setItem(r, 6, QTableWidgetItem(str(charge)))
            self._table.setItem(r, 7, QTableWidgetItem(has_imgs))

        self._table.resizeColumnsToContents()

    # ── 행 선택 시 이미지 미리보기 ─────────────────────────────
    def _on_row_changed(self, current_row: int, current_col: int, _prev_row: int, _prev_col: int) -> None:  # noqa: ARG002
        if current_row < 0:
            return
        rid_item = self._table.item(current_row, 0)
        if rid_item is None:
            return
        try:
            record_id = int(rid_item.text())
        except ValueError:
            return
        self._load_images(record_id)

    def _load_images(self, record_id: int) -> None:
        """서버에서 입차/출차 이미지를 받아 미리보기."""
        base = None
        try:
            entry_url = self._api.get_record_entry_image_url(record_id)
            exit_url = self._api.get_record_exit_image_url(record_id)
            base = True  # dummy flag
        except Exception:
            entry_url = exit_url = ""

        for url, label in ((entry_url, self._label_entry_img), (exit_url, self._label_exit_img)):
            if not url:
                label.setText("이미지 없음")
                label.setPixmap(None)
                continue
            try:
                resp = httpx.get(url, timeout=3.0)
                if resp.status_code != 200:
                    label.setText("이미지 없음")
                    label.setPixmap(None)
                    continue
                data = resp.content
                from PyQt6.QtGui import QPixmap
                pix = QPixmap()
                if not pix.loadFromData(data):
                    label.setText("이미지 로드 실패")
                    label.setPixmap(None)
                    continue
                label.setPixmap(
                    pix.scaled(
                        label.width(),
                        label.height(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            except Exception:
                label.setText("이미지 오류")
                label.setPixmap(None)

    # ── 선택 행 수정 다이얼로그 ─────────────────────────────
    def _edit_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        rid_item = self._table.item(row, 0)
        if rid_item is None:
            return
        try:
            record_id = int(rid_item.text())
        except ValueError:
            return
        initial: Dict[str, Any] = {
            "record_id": record_id,
            "license_plate": self._table.item(row, 1).text() if self._table.item(row, 1) else "",
            "charge_amount": int(self._table.item(row, 6).text()) if self._table.item(row, 6) else 0,
            "resident_id": self._table.item(row, 5).text() if self._table.item(row, 5) else "",
        }
        from PyQt6.QtWidgets import QCheckBox, QDialogButtonBox, QFormLayout, QLineEdit, QSpinBox

        dlg = QDialog(self)
        dlg.setWindowTitle(f"주차 기록 수정 (ID={record_id})")
        layout = QVBoxLayout()
        dlg.setLayout(layout)

        form = QFormLayout()
        edit_plate = QLineEdit(initial["license_plate"])
        spin_charge = QSpinBox()
        spin_charge.setRange(0, 1_000_000)
        spin_charge.setValue(initial["charge_amount"])
        edit_resident = QLineEdit(str(initial["resident_id"]))
        chk_registered = QCheckBox("등록 차량 (is_registered=1)")
        # 등록/비등록은 텍스트 기준으로 추정
        reg_text = self._table.item(row, 4).text() if self._table.item(row, 4) else ""
        chk_registered.setChecked("등록" in reg_text)

        form.addRow("번호판:", edit_plate)
        form.addRow("요금:", spin_charge)
        form.addRow("resident_id:", edit_resident)
        form.addRow("", chk_registered)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        payload: Dict[str, Any] = {
            "license_plate": edit_plate.text().strip(),
            "charge_amount": int(spin_charge.value()),
            "is_registered": 1 if chk_registered.isChecked() else 0,
        }
        resid_text = edit_resident.text().strip()
        payload["resident_id"] = int(resid_text) if resid_text else None

        try:
            self._api.update_parking_record(record_id, payload)
        except Exception as e:  # noqa: BLE001
            # 간단히 테이블 첫 행에 에러 출력
            self._table.setRowCount(1)
            self._table.setItem(0, 0, QTableWidgetItem("수정 오류"))
            self._table.setItem(0, 1, QTableWidgetItem(str(e)))
            return
        self.reload()

        # resident_id 가 있고, 해당 입주민 정보를 바로 보고 싶을 때는
        # ResidentEditDialog 를 재사용해 read-only 처럼 보여줄 수 있다.
        # 여기서는 선택적으로만 사용하도록 남겨둔다.


