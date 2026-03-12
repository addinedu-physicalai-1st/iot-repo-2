"""
저장된 이미지(파일)를 선택해 YOLO + PaddleOCR 로 OCR 테스트하는 별도 창.
대시보드·실시간 파이프라인과 분리되어 비즈니스 로직에 영향을 주지 않음.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Any, List, Optional

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QTextEdit,
    QFileDialog,
    QMessageBox,
    QProgressBar,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

# 선택 의존
try:
    import cv2
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False

try:
    from ultralytics import YOLO
    _YOLO_AVAILABLE = True
except ImportError:
    YOLO = None
    _YOLO_AVAILABLE = False

try:
    from paddleocr import PaddleOCR
    _PADDLE_AVAILABLE = True
except ImportError:
    PaddleOCR = None
    _PADDLE_AVAILABLE = False

from lpr_detector import _extract_plate_text_from_ocr_result


# 이미지 파일 패턴 (lpr_debug 등)
IMAGE_GLOBS = ["dashboard_entry_*.jpg", "dashboard_exit_*.jpg", "plate_*.jpg", "manual_*.jpg", "*.jpg", "*.png"]


def _collect_images(dir_path: Path) -> List[Path]:
    out: List[Path] = []
    if not dir_path.is_dir():
        return out
    seen = set()
    for pattern in IMAGE_GLOBS:
        for p in dir_path.glob(pattern):
            if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png") and p not in seen:
                seen.add(p)
                out.append(p)
    out.sort(key=lambda x: (x.stat().st_mtime, x.name), reverse=True)
    return out


class SavedImageOcrWorker(QThread):
    """선택된 이미지 파일들에 대해 YOLO + PaddleOCR 실행. 결과 한 줄씩 시그널."""
    line_ready = pyqtSignal(str)
    progress = pyqtSignal(int, int)  # current, total
    finished_success = pyqtSignal()
    finished_error = pyqtSignal(str)

    def __init__(
        self,
        model_path: str,
        file_paths: List[Path],
        plate_conf_threshold: float = 0.12,
    ) -> None:
        super().__init__()
        self._model_path = model_path
        self._file_paths = file_paths
        self._plate_conf = plate_conf_threshold
        self._plate_model: Any = None
        self._ocr: Any = None

    def run(self) -> None:
        if not _CV2_AVAILABLE or not _YOLO_AVAILABLE or not _PADDLE_AVAILABLE:
            self.finished_error.emit("cv2 / ultralytics / paddleocr 중 일부가 없습니다.")
            return
        try:
            self._plate_model = YOLO(str(Path(self._model_path).resolve()))
            self._ocr = PaddleOCR(lang="korean", use_textline_orientation=True, enable_mkldnn=False)
        except Exception as e:
            self.finished_error.emit(f"모델 로드 실패: {e}")
            return

        total = len(self._file_paths)
        for i, path in enumerate(self._file_paths):
            self.progress.emit(i + 1, total)
            img = cv2.imread(str(path))
            if img is None:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.line_ready.emit(f"저장이미지 ({path.name}) / {ts} / [파일 읽기 실패]")
                continue

            h, w = img.shape[:2]
            try:
                results = self._plate_model(img, conf=self._plate_conf, verbose=False)
                boxes = results[0].boxes.xyxy.cpu().numpy() if len(results) > 0 and results[0].boxes is not None else []
            except Exception:
                boxes = []

            final_text = ""
            for box in boxes:
                x1, y1, x2, y2 = map(int, box)
                pad_y = max(5, int((y2 - y1) * 0.15))
                pad_x = max(5, int((x2 - x1) * 0.05))
                y1_pad = max(0, y1 - pad_y)
                y2_pad = min(h, y2 + pad_y)
                x1_pad = max(0, x1 - pad_x)
                x2_pad = min(w, x2 + pad_x)
                cropped = img[y1_pad:y2_pad, x1_pad:x2_pad]
                if cropped.size == 0:
                    continue
                h_c, w_c = cropped.shape[:2]
                scaled = cv2.resize(cropped, (w_c * 4, h_c * 4), interpolation=cv2.INTER_CUBIC)
                try:
                    ocr_results = self._ocr.ocr(scaled)
                    text = _extract_plate_text_from_ocr_result(ocr_results)
                    if text and (not final_text or len(text) > len(final_text)):
                        final_text = text
                except Exception:
                    pass
                if final_text:
                    break

            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            result_str = final_text if final_text else "[인식 없음]"
            self.line_ready.emit(f"저장이미지 ({path.name}) / {ts} / {result_str}")

        self.finished_success.emit()


class SavedImageOcrDialog(QDialog):
    """저장된 이미지 목록에서 선택 후 OCR 실행, 결과는 이 창의 텍스트 영역에만 표시."""

    def __init__(
        self,
        default_dir: str,
        model_path: str,
        parent: Optional[Any] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("저장 이미지 OCR 테스트")
        self.setMinimumSize(520, 420)
        self._default_dir = Path(default_dir)
        self._model_path = model_path
        self._worker: Optional[SavedImageOcrWorker] = None

        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel("폴더:"))
        self._dir_edit = QLineEdit()
        self._dir_edit.setReadOnly(True)
        self._dir_edit.setText(str(self._default_dir.resolve()))
        row.addWidget(self._dir_edit, 1)
        btn_dir = QPushButton("폴더 선택")
        btn_dir.clicked.connect(self._choose_dir)
        row.addWidget(btn_dir)
        layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("이미지 목록 (선택 후 OCR 실행):"))
        layout.addLayout(row2)
        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        self._btn_refresh = QPushButton("목록 새로고침")
        self._btn_refresh.clicked.connect(self._refresh_list)
        btn_row.addWidget(self._btn_refresh)
        self._btn_run = QPushButton("OCR 실행")
        self._btn_run.clicked.connect(self._run_ocr)
        btn_row.addWidget(self._btn_run)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        layout.addWidget(QLabel("결과 (저장이미지 (파일명) / 시각 / 결과):"))
        self._result = QTextEdit()
        self._result.setReadOnly(True)
        layout.addWidget(self._result, 1)

        self._refresh_list()

    def _choose_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "폴더 선택", str(self._default_dir))
        if d:
            self._default_dir = Path(d)
            self._dir_edit.setText(d)
            self._refresh_list()

    def _refresh_list(self) -> None:
        self._list.clear()
        for p in _collect_images(self._default_dir):
            item = QListWidgetItem(p.name)
            item.setData(Qt.ItemDataRole.UserRole, str(p))
            self._list.addItem(item)

    def _run_ocr(self) -> None:
        items = self._list.selectedItems()
        if items:
            paths = [Path(item.data(Qt.ItemDataRole.UserRole)) for item in items]
        else:
            paths = [Path(self._list.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self._list.count())]
        if not paths:
            QMessageBox.information(self, "알림", "이미지를 선택하거나 폴더에 이미지를 넣은 뒤 목록 새로고침 후 실행하세요.")
            return
        self._btn_run.setEnabled(False)
        self._btn_refresh.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setMaximum(len(paths))
        self._progress.setValue(0)
        self._worker = SavedImageOcrWorker(self._model_path, paths)
        self._worker.line_ready.connect(self._on_line)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_success.connect(self._on_finished)
        self._worker.finished_error.connect(self._on_error)
        self._worker.start()

    def _on_line(self, line: str) -> None:
        self._result.append(line)

    def _on_progress(self, current: int, total: int) -> None:
        self._progress.setMaximum(total)
        self._progress.setValue(current)

    def _on_finished(self) -> None:
        self._btn_run.setEnabled(True)
        self._btn_refresh.setEnabled(True)
        self._progress.setVisible(False)

    def _on_error(self, msg: str) -> None:
        self._result.append(f"[오류] {msg}")
        self._btn_run.setEnabled(True)
        self._btn_refresh.setEnabled(True)
        self._progress.setVisible(False)
