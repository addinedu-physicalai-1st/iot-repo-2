from __future__ import annotations

from typing import Optional

import numpy as np
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QVBoxLayout,
)

from transmission_manager import TransmissionManager


class LprExitTestDialog(QDialog):
    """
    출구 LPR 카메라(esp32_lpr_exit) 테스트용 팝업.

    - 연결 상태: UDP 7090 패킷 수신 여부 (패킷 있으면 연결, 없으면 끊김)
    - 테스트 버튼 클릭 시 이 다이얼로그를 열면 UDP 스트림 영상 재생
    - TransmissionManager 가 UDP 7090 으로 수신한 프레임을 표시
    """

    def __init__(
        self,
        transmission_manager: TransmissionManager,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._tx = transmission_manager

        self.setWindowTitle("출구 LPR 카메라 테스트 (esp32_lpr_exit)")
        self.resize(640, 480)

        layout = QVBoxLayout()

        self.label_status = QLabel("상태: UDP 스트림 대기 중...")
        layout.addWidget(self.label_status)

        layout.addWidget(QLabel("출구 LPR UDP 영상 (포트 7090):"))
        self.video_label = QLabel()
        self.video_label.setMinimumSize(320, 240)
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: #333; color: #aaa;")
        self.video_label.setText("영상 대기 중... (ESP32에서 UDP 전송 시 표시)")
        layout.addWidget(self.video_label, 1)

        self._last_frame: Optional[np.ndarray] = None

        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._refresh_ui)
        self._timer.start()

        self.setLayout(layout)

    def _refresh_ui(self) -> None:
        # TransmissionManager 가 UDP 로 수신한 출구 프레임 가져와서 표시
        frame = self._tx.get_lpr_exit_frame()
        if frame is not None:
            fno, img = frame
            if img is not None:
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

        has_frame = self._tx.has_recent_lpr_exit_frame(timeout_sec=5.0)
        status = "영상 수신 중" if has_frame else "영상 없음 (UDP 7090 패킷 대기)"
        self.label_status.setText(f"상태: {status}")

