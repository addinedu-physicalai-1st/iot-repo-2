from __future__ import annotations

from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import QTimer, Qt, QThread
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QVBoxLayout,
    QTextEdit,
)

from config import settings
from transmission_manager import TransmissionManager
from lpr_detector import LprRecognitionWorker


class LprEnterTestDialog(QDialog):
    """
    입구 LPR 카메라(esp32_lpr_enter) 테스트용 팝업.

    - UDP 7070 영상 표시 (실시간, 지연 없음)
    - 번호판 인식: 별도 스레드에서 YOLO+OCR 실행, 인식 결과를 하단 에디터에 표시
    """

    def __init__(
        self,
        transmission_manager: TransmissionManager,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._tx = transmission_manager

        self.setWindowTitle("입구 LPR 카메라 테스트 (esp32_lpr_enter)")
        self.resize(680, 620)

        layout = QVBoxLayout()

        self.label_status = QLabel("상태: UDP 스트림 대기 중...")
        layout.addWidget(self.label_status)

        layout.addWidget(QLabel("입구 LPR UDP 영상 (포트 7070):"))
        self.video_label = QLabel()
        self.video_label.setMinimumSize(320, 240)
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: #333; color: #aaa;")
        self.video_label.setText("영상 대기 중... (ESP32에서 UDP 전송 시 표시)")
        layout.addWidget(self.video_label, 1)

        layout.addWidget(QLabel("번호판 인식 결과:"))
        self.result_edit = QTextEdit()
        self.result_edit.setReadOnly(True)
        self.result_edit.setMaximumHeight(140)
        self.result_edit.setPlaceholderText("인식된 번호가 여기 표시됩니다. (YOLO+PaddleOCR)")
        layout.addWidget(self.result_edit)

        self._last_frame: Optional[np.ndarray] = None
        self._refresh_count = 0

        # LPR 워커: 샘플 standalone과 동일 파라미터 (민감도 0.12, 쿨다운 3초, 1회 검출 시 OCR)
        self._lpr_worker = LprRecognitionWorker(
            model_path=settings.lpr_plate_model_path,
            plate_conf_threshold=0.12,
            stability_threshold=1,
            cooldown_seconds=3.0,
            mirror_flip=False,
        )
        self._lpr_worker.result_ready.connect(self._on_lpr_result)
        self._lpr_thread = QThread()
        self._lpr_worker.moveToThread(self._lpr_thread)
        self._lpr_thread.started.connect(self._lpr_worker.run_loop)
        if self._lpr_worker.is_available():
            self._lpr_thread.start()
        else:
            self.result_edit.append("[LPR] 번호판 인식 모듈을 사용할 수 없습니다. (ultralytics, paddleocr 설치 필요)")

        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._refresh_ui)
        self._timer.start()

        self.setLayout(layout)
        self._tx.set_lpr_ocr_ui_active(is_exit=False, active=True)

    def _on_lpr_result(self, line: str) -> None:
        self.result_edit.append(line)
        # 스크롤 맨 아래로
        cursor = self.result_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.result_edit.setTextCursor(cursor)

    def _refresh_ui(self) -> None:
        frame = self._tx.get_lpr_frame()
        if frame is not None:
            fno, img = frame
            if img is not None:
                # 입구 LPR 영상 보정: 상하 반전
                img = cv2.flip(img, 0)
                # OCR에도 화면과 동일한 보정본을 사용
                self._last_frame = img
                img = np.ascontiguousarray(img)
                h, w, ch = img.shape
                bytes_per_line = ch * w
                qimg = QImage(
                    img.data, w, h, bytes_per_line, QImage.Format.Format_BGR888
                ).copy()
                pix = QPixmap.fromImage(
                    qimg.scaled(
                        self.video_label.width(),
                        self.video_label.height(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                self.video_label.setPixmap(pix)
                self.video_label.setText("")

        # 영상과 별도로, 주기적으로만 LPR에 프레임 전달 (실시간 영상 지연 없음)
        self._refresh_count += 1
        if (
            self._last_frame is not None
            and self._lpr_worker.is_available()
            and (self._refresh_count % 5 == 0)
            and self._tx.should_run_lpr_ocr(is_exit=False)
        ):
            self._lpr_worker.submit_frame(self._last_frame.copy())

        has_frame = self._tx.has_recent_lpr_frame(timeout_sec=5.0)
        status = "영상 수신 중" if has_frame else "영상 없음 (UDP 7070 패킷 대기)"
        self.label_status.setText(f"상태: {status}")

    def closeEvent(self, event) -> None:
        self._tx.set_lpr_ocr_ui_active(is_exit=False, active=False)
        if self._lpr_worker.is_available():
            self._lpr_worker.stop()
            self._lpr_thread.quit()
            self._lpr_thread.wait(2000)
        super().closeEvent(event)
