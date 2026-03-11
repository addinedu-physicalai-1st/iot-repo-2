from __future__ import annotations

from typing import List, Dict, Any, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QGroupBox,
    QTextEdit,
)
from PyQt6.QtGui import QImage, QPixmap

import cv2
import numpy as np
from pathlib import Path
from datetime import datetime

from architect_manager import ArchitectManager
from device_manager import DeviceManager, ENTRY_GATE_GUID
from info_manager import InfoManager
from transmission_manager import TransmissionManager
from gate_test_dialog import GateTestDialog
from exit_gate_test_dialog import ExitGateTestDialog
from parking_guide_test_dialog import ParkingGuideTestDialog
from lpr_enter_test_dialog import LprEnterTestDialog
from lpr_exit_test_dialog import LprExitTestDialog
from rfid_management_tab import RfidManagementTab
from config import settings
from lpr_detector import _extract_plate_text_from_ocr_result

from PyQt6.QtWidgets import QTabWidget
from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot


class DataRefreshWorker(QThread):
    """
    백엔드 서버와 통신하여 데이터를 갱신하는 백그라운드 스레드.
    GUI 동결 방지를 위해 네트워크 집약적인 작업을 수행한다.
    """
    data_updated = pyqtSignal(dict)  # { "devices": [...], "dashboard_snapshot": (...), "managed_ids": [...] }
    error_occurred = pyqtSignal(str)

    def __init__(self, transmission_manager: TransmissionManager) -> None:
        super().__init__()
        self._tx = transmission_manager
        self._running = True

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        while self._running:
            try:
                # 1. 서버로부터 최신 정보 갱신
                self._tx.refresh_from_server()

                # 2. 필요한 데이터 스냅샷 생성
                managed_ids = self._tx.get_my_managed_device_ids()
                all_devices = self._tx._info.devices
                snapshot = self._tx.get_operation_mode_snapshot()
                entry_detected, exit_detected = self._tx.get_entry_exit_detection_snapshot()

                data = {
                    "all_devices": all_devices,
                    "managed_ids": managed_ids,
                    "dashboard_snapshot": snapshot,
                    "detection_snapshot": (entry_detected, exit_detected),
                }

                self.data_updated.emit(data)
            except Exception as e:
                self.error_occurred.emit(str(e))

            # 5초 간격으로 반복
            time.sleep(5)


import time


class MainWindow(QMainWindow):
    """
    3.device_client 메인 대시보드 창.

    - InfoManager 에 저장된 정보를 읽어와
      서버 연결 상태, 디바이스 리스트, UDP 관련 정보 등을 표시한다.
    - TransmissionManager 를 통해 서버와 통신하여 정보를 갱신한다.
    """

    lpr_popup_signal = pyqtSignal(bool, bool)  # is_exit, show
    rfid_scanned_signal = pyqtSignal(str)

    def __init__(
        self,
        info_manager: InfoManager,
        device_manager: DeviceManager,
        architect_manager: ArchitectManager,
        transmission_manager: TransmissionManager,
    ) -> None:
        super().__init__()
        self._info = info_manager
        self._device_mgr = device_manager
        self._arch_mgr = architect_manager
        self._tx = transmission_manager
        self._gate_dialog: GateTestDialog | None = None
        self._exit_gate_dialog: ExitGateTestDialog | None = None
        self._parking_dialog: ParkingGuideTestDialog | None = None
        self._lpr_dialog: LprEnterTestDialog | None = None
        self._lpr_exit_dialog: LprExitTestDialog | None = None

        # 임시 이미지 저장 & OCR 테스트용 상태
        self._last_entry_manual_image: Optional[Path] = None
        self._manual_yolo = None
        self._manual_ocr = None

        self.lpr_popup_signal.connect(self._handle_lpr_popup)
        self._device_mgr.on_lpr_popup = self._emit_lpr_popup

        self.setWindowTitle("스마트 주차장 - 디바이스 클라이언트 대시보드 (Optimized)")
        self.resize(1100, 700)

        # ───────── 백그라운드 데이터 워커 설정 ─────────
        self._refresh_worker = DataRefreshWorker(self._tx)
        self._refresh_worker.data_updated.connect(self._on_data_refreshed)
        self._refresh_worker.error_occurred.connect(self._on_refresh_error)
        self._refresh_worker.start()

        # 탭 위젯 생성
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # 1. 메인 대시보드 탭
        self.dashboard_tab = QWidget()
        main_layout = QVBoxLayout(self.dashboard_tab)
        
        # 2. 입주민 관리 탭
        self.rfid_tab = RfidManagementTab(self._tx._api)
        self.rfid_scanned_signal.connect(self.rfid_tab.on_rfid_scanned)
        self._device_mgr.on_rfid_scan = self.rfid_scanned_signal.emit

        self.tabs.addTab(self.dashboard_tab, "기기 대시보드")
        self.tabs.addTab(self.rfid_tab, "입주민(RFID) / 캐시 관리")

        # ───────── 상단 요약 영역 (대시보드 탭에 추가) ─────────
        summary_box = QGroupBox("연결 요약")
        summary_layout = QHBoxLayout()
        summary_box.setLayout(summary_layout)

        self.label_server = QLabel("서버 상태: 확인 중...")
        self.label_devices = QLabel("등록 디바이스: -")
        self.label_active_devices = QLabel("활성 디바이스: -")
        self.label_udp = QLabel("UDP 스트림: -")

        for lbl in (self.label_server, self.label_devices, self.label_active_devices, self.label_udp):
            lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            summary_layout.addWidget(lbl)

        # ───────── 중앙 분할 레이아웃 ─────────
        content_layout = QHBoxLayout()
        main_layout.addLayout(content_layout)

        # [LEFT] 카메라 모니터링 영역 (1.5 비율)
        left_layout = QVBoxLayout()
        content_layout.addLayout(left_layout, 2)

        cam_box = QGroupBox("카메라 및 LPR 모니터링")
        cam_box_inner = QVBoxLayout()
        cam_box.setLayout(cam_box_inner)
        left_layout.addWidget(cam_box)

        # 입구 카메라 영역
        entry_cam_layout = QVBoxLayout()
        entry_cam_layout.addWidget(QLabel("<b>[입구]</b> LPR 카메라 (UDP 7070)"))
        self.video_entry = QLabel("영상 대기 중...")
        self.video_entry.setFixedSize(400, 240)
        self.video_entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_entry.setStyleSheet("background-color: #222; border: 1px solid #444;")
        entry_cam_layout.addWidget(self.video_entry)

        # 입구 임시 이미지 저장 / OCR 테스트 버튼들
        entry_btn_row = QHBoxLayout()
        self.btn_entry_save_image = QPushButton("임시 이미지 저장")
        self.btn_entry_save_image.clicked.connect(self._on_entry_save_image)
        entry_btn_row.addWidget(self.btn_entry_save_image)

        self.btn_entry_ocr_test = QPushButton("저장 이미지 OCR 테스트")
        self.btn_entry_ocr_test.clicked.connect(self._on_entry_ocr_test)
        entry_btn_row.addWidget(self.btn_entry_ocr_test)

        # 고정 테스트 이미지용 OCR 버튼 (예: Screenshot_20260311_212956.png)
        self.btn_entry_ocr_test2 = QPushButton("저장 OCR 이미지 테스트2")
        self.btn_entry_ocr_test2.clicked.connect(self._on_entry_ocr_test2)
        entry_btn_row.addWidget(self.btn_entry_ocr_test2)

        entry_cam_layout.addLayout(entry_btn_row)

        self.log_entry = QTextEdit()
        self.log_entry.setReadOnly(True)
        self.log_entry.setMaximumHeight(80)
        self.log_entry.setPlaceholderText("입구 OCR 결과...")
        entry_cam_layout.addWidget(self.log_entry)
        cam_box_inner.addLayout(entry_cam_layout)
        
        cam_box_inner.addSpacing(10)

        # 출구 카메라 영역
        exit_cam_layout = QVBoxLayout()
        exit_cam_layout.addWidget(QLabel("<b>[출구]</b> LPR 카메라 (UDP 7090)"))
        self.video_exit = QLabel("영상 대기 중...")
        self.video_exit.setFixedSize(400, 240)
        self.video_exit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_exit.setStyleSheet("background-color: #222; border: 1px solid #444;")
        exit_cam_layout.addWidget(self.video_exit)
        
        self.log_exit = QTextEdit()
        self.log_exit.setReadOnly(True)
        self.log_exit.setMaximumHeight(80)
        self.log_exit.setPlaceholderText("출구 OCR 결과...")
        exit_cam_layout.addWidget(self.log_exit)
        cam_box_inner.addLayout(exit_cam_layout)

        # [RIGHT] 디바이스 상태 및 제어 (1 비율)
        right_layout = QVBoxLayout()
        content_layout.addLayout(right_layout, 1)

        right_layout.addWidget(summary_box)

        devices_box = QGroupBox("디바이스 목록")
        devices_inner = QVBoxLayout()
        devices_box.setLayout(devices_inner)
        
        self.table_devices = QTableWidget(0, 6)
        self.table_devices.setHorizontalHeaderLabels(["ID", "이름", "타입", "IP", "Port", "상태"])
        self.table_devices.horizontalHeader().setStretchLastSection(True)
        devices_inner.addWidget(self.table_devices)
        right_layout.addWidget(devices_box, 1)

        # 하단 버튼 모음
        btn_box = QGroupBox("수동 제어 및 테스트")
        btn_grid = QVBoxLayout()
        btn_box.setLayout(btn_grid)
        
        self.btn_gate_test = QPushButton("입구 게이트 제어")
        self.btn_gate_test.clicked.connect(self.open_gate_test_dialog)
        btn_grid.addWidget(self.btn_gate_test)

        self.btn_exit_gate_test = QPushButton("출구 게이트 제어")
        self.btn_exit_gate_test.clicked.connect(self.open_exit_gate_test_dialog)
        btn_grid.addWidget(self.btn_exit_gate_test)

        self.btn_refresh = QPushButton("지금 새로고침")
        self.btn_refresh.clicked.connect(self.refresh_from_server)
        btn_grid.addWidget(self.btn_refresh)
        
        right_layout.addWidget(btn_box)

        # ───────── 타이머: 주기적 갱신 (워커가 대체하므로 UI-Only 타이머는 제거 또는 용도 변경) ─────────
        # self._timer = QTimer(self)
        # self._timer.setInterval(5000)
        # self._timer.timeout.connect(self.refresh_from_server)
        # self._timer.start()

        # ───────── LPR 카메라 모니터링 활성화 (워커 시작 및 시그널 연결) ─────────
        self._ensure_lpr_dialogs()
        
        # 실시간 영상 갱신 타이머 (25fps 근사)
        self._video_timer = QTimer(self)
        self._video_timer.setInterval(40)
        self._video_timer.timeout.connect(self._update_videos)
        self._video_timer.start()

        # 초기 한 번 불러오기
        self.refresh_from_server()

        # ───────── LPR 카메라 모니터링 활성화 ─────────
        # 다이얼로그를 미리 생성하여 백그라운드 OCR 워커들이 돌게 한다.
        self._ensure_lpr_dialogs()
        self._tx.set_lpr_ocr_ui_active(is_exit=False, active=True)
        self._tx.set_lpr_ocr_ui_active(is_exit=True, active=True)

    # ───────── 데이터 로드 및 UI 반영 (비동기 콜백) ─────────
    @pyqtSlot(dict)
    def _on_data_refreshed(self, data: dict) -> None:
        """워커에서 데이터 갱신이 완료되었을 때 UI 를 업데이트한다."""
        all_devices = data["all_devices"]
        managed_ids = data["managed_ids"]
        op_snapshot = data["dashboard_snapshot"]
        det_snapshot = data["detection_snapshot"]

        # 1. 디바이스 필터링 및 요약/테이블 갱신
        if managed_ids:
            id_set = set(managed_ids)
            dev_by_id = {int(d.get("id")): d for d in all_devices if d.get("id") is not None}
            devices_to_show = [dev_by_id[i] for i in managed_ids if i in dev_by_id]
        else:
            devices_to_show = all_devices

        self._update_summary(devices_to_show)
        self._update_devices_table(devices_to_show)

        # 2. 게이트 로직 동기화 및 부가 정보 처리
        entry_gate_connected = False
        exit_gate_connected = False
        for dev in all_devices:
            guid = (dev.get("device_guid") or "").strip()
            if guid == ENTRY_GATE_GUID:
                entry_gate_connected = bool(dev.get("is_connected"))
            elif guid == "DEV-GATE-2":
                exit_gate_connected = bool(dev.get("is_connected"))

        operation_mode_on, free_slots, gate_sensor_state, gate_auto_state = op_snapshot
        entry_detected, exit_detected = det_snapshot

        self._device_mgr.sync_entry_gate_mode(
            entry_gate_connected,
            gate_sensor_state,
            entry_detected,
            exit_detected,
            gate_auto_state_from_server=gate_auto_state,
        )
        self._device_mgr.sync_exit_gate_mode(
            exit_gate_connected,
            gate_sensor_state,
            gate_auto_state_from_server=gate_auto_state,
        )
        self._device_mgr.sync_exit_lcd_base(
            operation_mode_on,
            free_slots,
            gate_sensor_state,
            gate_auto_state,
            message_type="default",
        )
        self.statusBar().showMessage("비동기 데이터 갱신 완료", 1000)

    @pyqtSlot(str)
    def _on_refresh_error(self, err_msg: str) -> None:
        self.statusBar().showMessage(f"서버 동기화 오류: {err_msg}", 3000)
        self.label_server.setText(f"서버 상태: 연결 실패 ({err_msg})")

    def refresh_from_server(self) -> None:
        """수동 새로고침 버튼 등을 위해 워커의 run 을 한 번 즉각 유도하거나 로직 유지 (현재는 워커가 5초마다 자동 수행)"""
        if not self._refresh_worker.isRunning():
            self._refresh_worker.start()
        self.statusBar().showMessage("데이터 동기화 요청됨...", 1000)

    def open_gate_test_dialog(self) -> None:
        """입구 차단기(ESP32 보드1_1) 테스트용 팝업을 연다."""
        if self._gate_dialog is None:
            self._gate_dialog = GateTestDialog(self._device_mgr, self)
        self._gate_dialog.show()
        self._gate_dialog.raise_()
        self._gate_dialog.activateWindow()

    def open_exit_gate_test_dialog(self) -> None:
        """출구 차단기(ESP32 보드1_2) 테스트용 팝업을 연다."""
        if self._exit_gate_dialog is None:
            self._exit_gate_dialog = ExitGateTestDialog(self._device_mgr, self)
        self._exit_gate_dialog.show()
        self._exit_gate_dialog.raise_()
        self._exit_gate_dialog.activateWindow()

    def open_parking_guide_test_dialog(self) -> None:
        """esp32_board2(파킹 가이드) 이벤트를 확인하는 팝업을 연다."""
        if self._parking_dialog is None:
            self._parking_dialog = ParkingGuideTestDialog(self._device_mgr, self)
        self._parking_dialog.show()
        self._parking_dialog.raise_()
        self._parking_dialog.activateWindow()

    def _ensure_lpr_dialogs(self) -> None:
        """LPR 다이얼로그를 미리 생성하고 OCR 시그널을 대시보드에 연결한다."""
        if self._lpr_dialog is None:
            self._lpr_dialog = LprEnterTestDialog(
                self._tx,
                on_gate_open=lambda: self._device_mgr.open_gate(target_guid="DEV-GATE-1"),
                parent=self,
            )
            # OCR 인식 결과 시그널을 메인 대시보드 로그창에 연결
            self._lpr_dialog._lpr_worker.result_ready.connect(lambda msg: self.log_entry.append(msg))
            
        if self._lpr_exit_dialog is None:
            self._lpr_exit_dialog = LprExitTestDialog(
                self._tx,
                on_gate_open=lambda: self._device_mgr.open_gate(target_guid="DEV-GATE-2"),
                parent=self,
            )
            self._lpr_exit_dialog._lpr_worker.result_ready.connect(lambda msg: self.log_exit.append(msg))

    def _on_entry_save_image(self) -> None:
        """현재 입구 LPR 최신 프레임을 임시 파일로 저장."""
        try:
            frame_data = self._tx.get_latest_lpr_frame(is_exit=False)
        except Exception:
            frame_data = None

        if not frame_data or frame_data[1] is None:
            self.log_entry.append("[TMP] 저장할 입구 영상 프레임이 없습니다.")
            return

        _, img = frame_data
        try:
            img_bgr = img
            if img_bgr is None or not isinstance(img_bgr, np.ndarray):
                self.log_entry.append("[TMP] 프레임 형식이 올바르지 않습니다.")
                return

            debug_dir = Path(__file__).resolve().parent / "lpr_debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = debug_dir / f"manual_entry_{ts}.jpg"
            cv2.imwrite(str(fname), img_bgr)
            self._last_entry_manual_image = fname
            self.log_entry.append(f"[TMP] 임시 이미지 저장: {fname.name}")
        except Exception as e:
            self.log_entry.append(f"[TMP] 이미지 저장 오류: {e}")

    def _ensure_manual_ocr_models(self) -> bool:
        """임시 OCR 테스트용 YOLO / PaddleOCR 초기화."""
        try:
            if self._manual_yolo is None or self._manual_ocr is None:
                from ultralytics import YOLO
                from paddleocr import PaddleOCR

                model_path = str(Path(settings.lpr_plate_model_path).resolve())
                self._manual_yolo = YOLO(model_path)
                self._manual_ocr = PaddleOCR(
                    lang="korean",
                    use_textline_orientation=True,
                    enable_mkldnn=False,
                )
            return True
        except Exception as e:
            self.log_entry.append(f"[TMP] OCR 모델 로드 오류: {e}")
            return False

    def _on_entry_ocr_test(self) -> None:
        """마지막으로 저장한 임시 입구 이미지를 이용해 OCR 테스트."""
        if not self._last_entry_manual_image or not self._last_entry_manual_image.is_file():
            self.log_entry.append("[TMP] 저장된 임시 이미지가 없습니다. 먼저 '임시 이미지 저장'을 눌러 주세요.")
            return

        if not self._ensure_manual_ocr_models():
            return

        try:
            img = cv2.imread(str(self._last_entry_manual_image))
            if img is None:
                self.log_entry.append("[TMP] 임시 이미지를 불러오지 못했습니다.")
                return

            h, w = img.shape[:2]
            results = self._manual_yolo(img, conf=0.12, verbose=False)
            boxes = results[0].boxes.xyxy.cpu().numpy() if len(results) > 0 and results[0].boxes is not None else []

            if len(boxes) == 0:
                self.log_entry.append("[TMP] YOLO 번호판 박스를 찾지 못했습니다.")
                return

            x1, y1, x2, y2 = map(int, boxes[0])
            pad_y = max(5, int((y2 - y1) * 0.15))
            pad_x = max(5, int((x2 - x1) * 0.05))
            y1_pad = max(0, y1 - pad_y)
            y2_pad = min(h, y2 + pad_y)
            x1_pad = max(0, x1 - pad_x)
            x2_pad = min(w, x2 + pad_x)
            cropped = img[y1_pad:y2_pad, x1_pad:x2_pad]
            if cropped.size == 0:
                self.log_entry.append("[TMP] 크롭된 번호판 영역이 비어 있습니다.")
                return

            ch, cw = cropped.shape[:2]
            scaled = cv2.resize(cropped, (cw * 4, ch * 4), interpolation=cv2.INTER_CUBIC)

            ocr_results = self._manual_ocr.ocr(scaled)
            final_text, confidence = _extract_plate_text_from_ocr_result(ocr_results)

            if final_text:
                self.log_entry.append(f"[TMP] 저장 이미지 OCR → '{final_text}' (conf≈{confidence:.2f})")
            else:
                self.log_entry.append(f"[TMP] 저장 이미지 OCR → <no text> (conf≈{confidence:.2f})")
        except Exception as e:
            self.log_entry.append(f"[TMP] OCR 테스트 오류: {e}")

    def _on_entry_ocr_test2(self) -> None:
        """고정된 테스트 이미지(Screenshot_20260311_212956.png)를 이용해 OCR 테스트."""
        # 프로젝트 루트 기준 경로: 3.device_client/lpr_debug/Screenshot_20260311_212956.png
        fixed_path = (
            Path(__file__).resolve().parent
            / "lpr_debug"
            / "Screenshot_20260311_212956.png"
        )

        if not fixed_path.is_file():
            self.log_entry.append(f"[TMP2] 테스트 이미지가 없습니다: {fixed_path.name}")
            return

        if not self._ensure_manual_ocr_models():
            return

        try:
            img = cv2.imread(str(fixed_path))
            if img is None:
                self.log_entry.append("[TMP2] 테스트 이미지를 불러오지 못했습니다.")
                return

            h, w = img.shape[:2]
            results = self._manual_yolo(img, conf=0.12, verbose=False)
            boxes = results[0].boxes.xyxy.cpu().numpy() if len(results) > 0 and results[0].boxes is not None else []

            if len(boxes) == 0:
                self.log_entry.append("[TMP2] YOLO 번호판 박스를 찾지 못했습니다.")
                return

            x1, y1, x2, y2 = map(int, boxes[0])
            pad_y = max(5, int((y2 - y1) * 0.15))
            pad_x = max(5, int((x2 - x1) * 0.05))
            y1_pad = max(0, y1 - pad_y)
            y2_pad = min(h, y2 + pad_y)
            x1_pad = max(0, x1 - pad_x)
            x2_pad = min(w, x2 + pad_x)
            cropped = img[y1_pad:y2_pad, x1_pad:x2_pad]
            if cropped.size == 0:
                self.log_entry.append("[TMP2] 크롭된 번호판 영역이 비어 있습니다.")
                return

            ch, cw = cropped.shape[:2]
            scaled = cv2.resize(cropped, (cw * 4, ch * 4), interpolation=cv2.INTER_CUBIC)

            ocr_results = self._manual_ocr.ocr(scaled)
            final_text, confidence = _extract_plate_text_from_ocr_result(ocr_results)

            if final_text:
                self.log_entry.append(
                    f"[TMP2] Screenshot OCR → '{final_text}' (conf≈{confidence:.2f})"
                )
            else:
                self.log_entry.append(
                    f"[TMP2] Screenshot OCR → <no text> (conf≈{confidence:.2f})"
                )
        except Exception as e:
            self.log_entry.append(f"[TMP2] OCR 테스트2 오류: {e}")

    def open_lpr_enter_test_dialog(self) -> None:
        """입구 LPR 카메라(esp32_lpr_enter) 테스트용 팝업을 연다."""
        self._ensure_lpr_dialogs()
        self._lpr_dialog.show()
        self._lpr_dialog.raise_()
        self._lpr_dialog.activateWindow()

    def open_lpr_exit_test_dialog(self) -> None:
        """출구 LPR 카메라(esp32_lpr_exit) 테스트용 팝업을 연다."""
        self._ensure_lpr_dialogs()
        self._lpr_exit_dialog.show()
        self._lpr_exit_dialog.raise_()
        self._lpr_exit_dialog.activateWindow()

    def _update_videos(self) -> None:
        """TransmissionManager 로부터 최신 프레임을 가져와 대시보드에 표시 (Non-consuming)."""
        # 입구 영상
        entry_frame_data = self._tx.get_latest_lpr_frame(is_exit=False)
        if entry_frame_data:
            _, img = entry_frame_data
            self._set_pixmap_on_label(self.video_entry, img)
        
        # 출구 영상
        exit_frame_data = self._tx.get_latest_lpr_frame(is_exit=True)
        if exit_frame_data:
            _, img = exit_frame_data
            self._set_pixmap_on_label(self.video_exit, img)

    def _set_pixmap_on_label(self, label: QLabel, cv_img: Any) -> None:
        """OpenCV 이미지를 QLabel 에 맞춰 QPixmap 으로 변환/출력."""
        try:
            h, w, c = cv_img.shape
            bytes_per_line = c * w
            # QImage 는 원본 데이터 포인터를 참조하므로 .copy() 를 수행하여 안전하게 Pixmap 변환
            q_img = QImage(cv_img.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).rgbSwapped().copy()
            pix = QPixmap.fromImage(q_img)
            label.setPixmap(pix.scaled(label.width(), label.height(), Qt.AspectRatioMode.KeepAspectRatio))
        except Exception as e:
            # 디버깅을 위해 에러 무시하지 않음
            pass

    def _emit_lpr_popup(self, is_exit: bool, show: bool) -> None:
        self.lpr_popup_signal.emit(is_exit, show)

    def _handle_lpr_popup(self, is_exit: bool, show: bool) -> None:
        if show:
            if is_exit:
                self.open_lpr_exit_test_dialog()
            else:
                self.open_lpr_enter_test_dialog()
        else:
            if is_exit and self._lpr_exit_dialog is not None:
                self._lpr_exit_dialog.close()
                self._lpr_exit_dialog = None
            elif not is_exit and self._lpr_dialog is not None:
                self._lpr_dialog.close()
                self._lpr_dialog = None

    def _update_summary(self, devices: List[Dict[str, Any]] | None = None) -> None:
        health = self._info.server_health or {}
        status = health.get("status", "unknown")
        self.label_server.setText(
            f"서버 상태: {status} ({self._info.env.server_base_url})",
        )

        if devices is None:
            devices = self._info.devices
        total = len(devices)
        active = sum(1 for d in devices if d.get("is_connected"))
        self.label_devices.setText(f"등록 디바이스: {total}개")
        self.label_active_devices.setText(f"활성 디바이스: {active}개")

        # UDP 관련 정보는 .env + LPR 카메라 서버 config 를 기준으로 단순 표시
        udp_host = self._info.env.udp_listen_host
        udp_port = self._info.env.udp_listen_port
        self.label_udp.setText(f"UDP 수신: {udp_host}:{udp_port}")

    def _update_devices_table(self, devices: List[Dict[str, Any]]) -> None:
        self.table_devices.setRowCount(len(devices))
        for row, dev in enumerate(devices):
            self.table_devices.setItem(
                row,
                0,
                QTableWidgetItem(str(dev.get("id", ""))),
            )
            self.table_devices.setItem(
                row,
                1,
                QTableWidgetItem(dev.get("name", "")),
            )
            self.table_devices.setItem(
                row,
                2,
                QTableWidgetItem(dev.get("type", "")),
            )
            self.table_devices.setItem(
                row,
                3,
                QTableWidgetItem(dev.get("ip_address", "") or ""),
            )
            self.table_devices.setItem(
                row,
                4,
                QTableWidgetItem(dev.get("port_info", "") or ""),
            )
            self.table_devices.setItem(
                row,
                5,
                QTableWidgetItem("연결됨" if dev.get("is_connected") else "미연결"),
            )

            is_conn = bool(dev.get("is_connected"))
            for col in range(6):
                item = self.table_devices.item(row, col)
                if item:
                    item.setForeground(Qt.GlobalColor.white if is_conn else Qt.GlobalColor.gray)
                    if col == 5: # 상태 컬럼 색상 강조
                        item.setBackground(Qt.GlobalColor.darkGreen if is_conn else Qt.GlobalColor.darkRed)

