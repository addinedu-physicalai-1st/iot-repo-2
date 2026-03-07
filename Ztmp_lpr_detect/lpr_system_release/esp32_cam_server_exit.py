# ESP32-CAM LPR 서버 666 — UDP 영상 수신 + 번호판 OCR 인식 결과 표시
# - REST API 없음. UDP 스트림이 들어오면 자동으로 영상 표시
# - YOLO 번호판 검출 + PaddleOCR 한글 인식 후 결과 출력

import os
import sys
import re
import time
import socket
import threading
from queue import Queue, Empty

import numpy as np
import cv2
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap

UDP_PORT = 7090  # 출구 LPR (입구는 7070)
frame_queue = Queue(maxsize=5)
ocr_frame_queue = Queue(maxsize=1)  # 최신 1프레임만 OCR용으로 전달

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(SCRIPT_DIR, "img")
# 번호판 YOLO 모델: 이 스크립트와 같은 폴더(lpr_system_release/best.pt) 우선
PLATE_MODEL_PATH = os.path.join(SCRIPT_DIR, "best.pt")
if not os.path.isfile(PLATE_MODEL_PATH):
    _project_root = os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT_DIR)))
    PLATE_MODEL_PATH = os.path.join(_project_root, "3.device_client", "lpr_models", "best.pt")

# 전역 모델 (worker에서 lazy 로드)
_plate_model = None
_ocr_engine = None
_models_lock = threading.Lock()


def _get_models():
    global _plate_model, _ocr_engine
    with _models_lock:
        if _plate_model is None and os.path.isfile(PLATE_MODEL_PATH):
            from ultralytics import YOLO
            _plate_model = YOLO(PLATE_MODEL_PATH)
        if _ocr_engine is None:
            from paddleocr import PaddleOCR
            _ocr_engine = PaddleOCR(lang='korean', use_textline_orientation=True, enable_mkldnn=False)
    return _plate_model, _ocr_engine


def udp_receiver_thread(log_signal):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    sock.bind(('0.0.0.0', UDP_PORT))
    frames = {}
    last_frame_no = -1
    if log_signal:
        log_signal.emit(f"[666] UDP 수신 시작 (포트 {UDP_PORT}). 스트림 들어오면 영상 표시.")
    while True:
        try:
            data, addr = sock.recvfrom(2048)
            if len(data) < 5:
                continue
            f_no = data[0]
            p_no = data[1]
            is_last = data[2]
            received_checksum = data[3]
            chunk = data[4:]
            if f_no < last_frame_no and (last_frame_no - f_no) < 200:
                continue
            if f_no not in frames:
                if len(frames) > 3:
                    del frames[min(frames.keys())]
                frames[f_no] = {'chunks': {}, 'target_checksum': None}
            frames[f_no]['chunks'][p_no] = chunk
            if is_last == 1:
                frames[f_no]['target_checksum'] = received_checksum
            target = frames[f_no].get('target_checksum')
            if target is not None:
                indices = sorted(frames[f_no]['chunks'].keys())
                if len(indices) > 0 and indices[0] == 0 and indices[-1] == p_no and len(indices) == p_no + 1:
                    full_data = b"".join([frames[f_no]['chunks'][i] for i in indices])
                    calculated_checksum = sum(full_data) % 256
                    if calculated_checksum == target:
                        nparr = np.frombuffer(full_data, dtype=np.uint8)
                        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        if img is not None:
                            if frame_queue.full():
                                frame_queue.get()
                            frame_queue.put((f_no, img.copy()))
                            last_frame_no = f_no
                    frames = {k: v for k, v in frames.items() if k > f_no}
        except Exception as e:
            if log_signal:
                log_signal.emit(f"UDP 수신 오류: {e}")


# OCR 워커: 주기적으로 프레임을 받아 번호판 검출 → OCR → 결과 시그널
OCR_COOLDOWN_SEC = 3.0   # 인식 후 3초 뒤 재시도 (더 자주 시도)
YOLO_CONF = 0.12         # ESP32 저해상도에 맞춰 검출 민감도


def ocr_worker_thread(result_signal, log_signal):
    plate_model, ocr_engine = None, None
    last_trigger_time = 0.0

    while True:
        try:
            frame = ocr_frame_queue.get(timeout=0.5)
        except Empty:
            continue
        if frame is None:
            continue

        try:
            if plate_model is None or ocr_engine is None:
                if log_signal:
                    log_signal.emit("OCR 모델 로딩 중...")
                plate_model, ocr_engine = _get_models()
            if plate_model is None:
                if log_signal:
                    log_signal.emit(f"모델 없음. best.pt 를 이 폴더에 두거나 3.device_client/lpr_models/ 에 두세요.")
                continue
        except Exception as e:
            if log_signal:
                log_signal.emit(f"모델 로드 오류: {e}")
            continue

        results = plate_model(frame, conf=YOLO_CONF, verbose=False)
        boxes = results[0].boxes.xyxy.cpu().numpy()

        if len(boxes) == 0:
            continue

        current_time = time.time()
        if (current_time - last_trigger_time) < OCR_COOLDOWN_SEC:
            continue

        if log_signal:
            log_signal.emit("번호판 검출 → OCR 실행 중...")
        last_trigger_time = current_time

        x1, y1, x2, y2 = map(int, boxes[0])
        h, w = frame.shape[:2]
        pad_y = max(5, int((y2 - y1) * 0.15))
        pad_x = max(5, int((x2 - x1) * 0.05))
        y1_pad = max(0, y1 - pad_y)
        y2_pad = min(h, y2 + pad_y)
        x1_pad = max(0, x1 - pad_x)
        x2_pad = min(w, x2 + pad_x)
        cropped = frame[y1_pad:y2_pad, x1_pad:x2_pad]
        if cropped.size == 0:
            continue
        h_c, w_c = cropped.shape[:2]
        scaled = cv2.resize(cropped, (w_c * 4, h_c * 4), interpolation=cv2.INTER_CUBIC)

        ocr_results = ocr_engine.ocr(scaled)
        final_text = ""
        if ocr_results:
            for res in ocr_results:
                if hasattr(res, 'rec_texts') and res.rec_texts:
                    final_text += "".join(res.rec_texts)
                elif isinstance(res, dict) and 'rec_texts' in res:
                    final_text += "".join(res['rec_texts'])
                elif isinstance(res, (list, tuple)) and res:
                    for line in res:
                        if line and len(line) >= 2:
                            final_text += str(line[1][0]) if isinstance(line[1], (list, tuple)) else str(line[1])
        final_text = "".join(re.findall(r'[0-9가-힣]', final_text))

        if len(final_text) >= 5:
            result_signal.emit(final_text)
            if log_signal:
                log_signal.emit(f"인식: {final_text}")
        else:
            if log_signal:
                short = final_text if final_text else "(없음)"
                log_signal.emit(f"OCR 결과 짧음: '{short}' (5자 이상 필요)")

        try:
            ocr_frame_queue.get_nowait()
        except Empty:
            pass


class CamApp666(QWidget):
    log_signal = pyqtSignal(str)
    result_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._last_frame = None
        self._last_ocr_text = ""
        self._ocr_frame_count = 0
        os.makedirs(IMG_DIR, exist_ok=True)
        self.setWindowTitle("ESP32-CAM LPR 666 — UDP 영상 + OCR")
        layout = QVBoxLayout()
        layout.addWidget(QLabel("UDP 스트림 수신 시 영상 표시 + 번호판 인식"))
        self.video_label = QLabel()
        self.video_label.setMinimumSize(320, 240)
        self.video_label.setStyleSheet("background-color: #333; color: #888;")
        self.video_label.setText("UDP 대기 중... (ESP32 LPR 666 기동 후 자동 전송)")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.video_label)
        self.result_label = QLabel("인식 결과: —")
        self.result_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #0a0;")
        layout.addWidget(self.result_label)
        self.log_label = QLabel("상태: UDP 수신 대기")
        layout.addWidget(self.log_label)
        self.setLayout(layout)
        self.resize(400, 380)
        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._update_video_frame)
        self._frame_timer.start(40)
        self.log_signal.connect(self._on_log)
        self.result_signal.connect(self._on_ocr_result)
        threading.Thread(target=udp_receiver_thread, args=(self.log_signal,), daemon=True).start()
        threading.Thread(target=ocr_worker_thread, args=(self.result_signal, self.log_signal), daemon=True).start()

    def _on_log(self, msg):
        self.log_label.setText(msg)

    def _on_ocr_result(self, plate_text):
        self._last_ocr_text = plate_text
        self.result_label.setText(f"인식 결과: {plate_text}")
        self.log_label.setText(f"인식: {plate_text}")

    def _update_video_frame(self):
        if frame_queue.empty():
            return
        try:
            f_no, img = frame_queue.get_nowait()
        except Exception:
            return
        if img is None:
            return
        # 좌우 반전만 (번호판 글자 정상 방향으로 보이도록)
        #img = cv2.flip(img, 1)
        #img = cv2.flip(img, 0)
        img = np.ascontiguousarray(img)
        # OCR 워커에 프레임 전달 (매 5프레임마다, 큐 비었을 때만)
        self._ocr_frame_count += 1
        if self._ocr_frame_count >= 5 and ocr_frame_queue.empty():
            self._ocr_frame_count = 0
            try:
                ocr_frame_queue.put_nowait(img.copy())
            except Exception:
                pass
        # 화면에 표시 (마지막 인식 결과 오버레이)
        display = img.copy()
        if self._last_ocr_text:
            cv2.putText(display, self._last_ocr_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
        h, w, ch = display.shape
        bytes_per_line = ch * w
        qimg = QImage(display.data, w, h, bytes_per_line, QImage.Format.Format_BGR888).copy()
        self.video_label.setPixmap(
            QPixmap.fromImage(qimg).scaled(
                self.video_label.width(), self.video_label.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.video_label.setText("")
        self._last_frame = display.copy()
        self.log_label.setText(f"수신 중 (프레임 {f_no})")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    ex = CamApp666()
    ex.show()
    sys.exit(app.exec())
