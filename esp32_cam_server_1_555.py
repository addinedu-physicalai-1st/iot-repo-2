# ESP32-CAM 서버 555 — 양방향 REST API 제어 + UDP 영상 수신(별도 스레드)
# REST API: HTTP 5555 (장비 등록, 명령 폴링, UI에서 캠/플래시 명령)
# UDP 7072: 영상 수신 전용 스레드 (222/333과 포트 분리)

import os
import sys
import socket
import threading
import time
from datetime import datetime
from queue import Queue

import re
import numpy as np
import cv2
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QTextEdit, QLineEdit, QGroupBox, QGridLayout, QFileDialog,
    QDialog, QDialogButtonBox,
)
from PyQt6.QtCore import pyqtSignal, QObject, QTimer, Qt
from PyQt6.QtGui import QImage, QPixmap

# REST API (Flask) + requests for UI → API 호출
try:
    from flask import Flask, request, jsonify
except ImportError:
    print("pip install flask")
    sys.exit(1)

# OCR (번호판 판독): pytesseract + 시스템에 tesseract-ocr 설치 필요
try:
    import pytesseract
    _ocr_available = True
except ImportError:
    pytesseract = None
    _ocr_available = False

# --- 설정 ---
REST_PORT = 5555
UDP_PORT = 7072
RECV_CHECK_INTERVAL_SEC = 2

frame_queue = Queue(maxsize=5)

# OCR: N프레임마다 한 번만 실행 (부하 완화)
OCR_INTERVAL_FRAMES = 20

# 영상 캡쳐: 버튼 클릭 시 현재 스크립트 폴더 아래 img 폴더에 저장
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(SCRIPT_DIR, "img")

# REST API용 공유 상태 (Flask 스레드 ↔ 메인/UI)
_api_state = {
    "pending_command": "none",
    "devices": [],  # [{"guid":"...", "name":"...", "ip":"...", "last_seen": float}, ...]
    "server_for_device": {"server_host": "192.168.0.4", "rest_port": 5555, "udp_port": 7072},
    "lock": threading.Lock(),
}


def _set_command(cmd):
    with _api_state["lock"]:
        _api_state["pending_command"] = cmd


def _get_and_clear_command():
    with _api_state["lock"]:
        c = _api_state["pending_command"]
        _api_state["pending_command"] = "none"
        return c


def _register_device(guid, name, ip=None):
    with _api_state["lock"]:
        for d in _api_state["devices"]:
            if d.get("guid") == guid:
                d["name"] = name
                d["last_seen"] = time.monotonic()
                if ip is not None:
                    d["ip"] = ip
                return
        _api_state["devices"].append({
            "guid": guid, "name": name, "last_seen": time.monotonic(),
            "ip": ip or "",
        })


def _get_devices():
    with _api_state["lock"]:
        return list(_api_state["devices"])


def _get_server_for_device():
    with _api_state["lock"]:
        return dict(_api_state["server_for_device"])


def _set_server_for_device(server_host, rest_port, udp_port):
    with _api_state["lock"]:
        _api_state["server_for_device"]["server_host"] = server_host
        _api_state["server_for_device"]["rest_port"] = int(rest_port)
        _api_state["server_for_device"]["udp_port"] = int(udp_port)


def _ocr_image_to_text(img_bgr):
    """이미지에서 OCR 수행 후 (성공여부, 결과문자열) 반환. 로그/다이얼로그 공용."""
    if not _ocr_available:
        return False, "OCR 비활성: pip install pytesseract 및 tesseract-ocr 설치 필요"
    try:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        text = pytesseract.image_to_string(
            thresh,
            config="--psm 7 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ가나다라마거너더러머고노도로모구누두루무"
        )
        text = re.sub(r"\s+", "", text).strip()
        return True, text if text else "(판독된 문자 없음)"
    except Exception as e:
        return False, f"OCR 오류: {e}"


def _ocr_license_plate(img_bgr, log_callback):
    """영상에서 번호판 문자 판독 후 로그 콜백으로 전달."""
    if log_callback is None:
        return
    ok, text = _ocr_image_to_text(img_bgr)
    if ok and len(text) >= 2 and text != "(판독된 문자 없음)":
        log_callback(f"🚗 번호판 판독: {text}")
    elif not ok:
        log_callback(f"⚠ {text}")


# --- Flask REST API (별도 스레드에서 실행) ---
app = Flask(__name__)


@app.route("/api/device/register", methods=["POST"])
def api_register():
    try:
        j = request.get_json(force=True, silent=True) or {}
        guid = (j.get("guid") or "").strip() or "ESP32-CAM-01"
        name = (j.get("name") or "").strip() or "CamStream"
        ip = (j.get("ip") or "").strip()
        _register_device(guid, name, ip or None)
        return jsonify({"ok": True, "guid": guid, "ip": ip})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/device/config", methods=["GET", "POST", "PUT"])
def api_device_config():
    """GET: 장비가 폴링하여 서버 주소/포트 수신. POST/PUT: UI에서 수정 후 저장."""
    if request.method == "GET":
        return jsonify(_get_server_for_device())
    try:
        j = request.get_json(force=True, silent=True) or {}
        host = (j.get("server_host") or j.get("host") or "").strip() or "192.168.0.4"
        rest_port = int(j.get("rest_port", 5555))
        udp_port = int(j.get("udp_port", 7072))
        _set_server_for_device(host, rest_port, udp_port)
        return jsonify({"ok": True, "server_host": host, "rest_port": rest_port, "udp_port": udp_port})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/device/command", methods=["GET"])
def api_command():
    guid = request.args.get("guid", "").strip() or "ESP32-CAM-01"
    _register_device(guid, "CamStream", None)
    cmd = _get_and_clear_command()
    return jsonify({"command": cmd})


@app.route("/api/device/heartbeat", methods=["POST"])
def api_heartbeat():
    j = request.get_json(force=True, silent=True) or {}
    guid = (j.get("guid") or "").strip() or "ESP32-CAM-01"
    _register_device(guid, "CamStream")
    return jsonify({"ok": True})


@app.route("/api/devices", methods=["GET"])
def api_devices():
    return jsonify({"devices": _get_devices()})


@app.route("/api/cam/start", methods=["POST"])
def api_cam_start():
    _set_command("cam_start")
    return jsonify({"ok": True, "command": "cam_start"})


@app.route("/api/cam/stop", methods=["POST"])
def api_cam_stop():
    _set_command("cam_stop")
    return jsonify({"ok": True, "command": "cam_stop"})


@app.route("/api/flash/on", methods=["POST"])
def api_flash_on():
    _set_command("flash_on")
    return jsonify({"ok": True})


@app.route("/api/flash/off", methods=["POST"])
def api_flash_off():
    _set_command("flash_off")
    return jsonify({"ok": True})


@app.route("/api/flash/blink", methods=["POST"])
def api_flash_blink():
    _set_command("flash_blink")
    return jsonify({"ok": True})


# --- UDP 수신: 전용 스레드 (cam_udp_receive_test_gui.py 로직) ---
def _udp_receiver_thread(log_signal):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    sock.bind(('0.0.0.0', UDP_PORT))
    frames = {}
    last_frame_no = -1
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
                    else:
                        log_signal.emit(f"Frame {f_no}: Checksum Error!")
                    frames = {k: v for k, v in frames.items() if k > f_no}
        except Exception as e:
            log_signal.emit(f"UDP Recv Error: {e}")


class OcrResultDialog(QDialog):
    """이미지로 OCR 확인 결과 표시 다이얼로그"""
    def __init__(self, image_path, img_bgr, ocr_ok, ocr_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OCR 확인 결과")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"선택 이미지: {os.path.basename(image_path)}"))
        if img_bgr is not None:
            h, w, ch = img_bgr.shape
            bytes_per_line = ch * w
            qimg = QImage(img_bgr.data, w, h, bytes_per_line, QImage.Format.Format_BGR888).copy()
            pix = QPixmap.fromImage(qimg.scaled(320, 240, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            img_label = QLabel()
            img_label.setPixmap(pix)
            layout.addWidget(img_label)
        layout.addWidget(QLabel("OCR 결과:"))
        self.result_edit = QTextEdit()
        self.result_edit.setReadOnly(True)
        self.result_edit.setMinimumHeight(80)
        status = "✅ OCR 정상 동작" if ocr_ok else "⚠ OCR 실패 또는 비활성"
        self.result_edit.setPlainText(f"{status}\n\n{ocr_text}")
        layout.addWidget(self.result_edit)
        btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn.accepted.connect(self.accept)
        layout.addWidget(btn)


class CamServerWorker555(QObject):
    log_signal = pyqtSignal(str)
    device_list_signal = pyqtSignal(list)

    def __init__(self):
        super().__init__()

    def start(self):
        # 1) UDP 수신 전용 스레드
        threading.Thread(target=_udp_receiver_thread, args=(self.log_signal,), daemon=True).start()
        self.log_signal.emit(f"[555] UDP 수신 스레드 시작 (포트 {UDP_PORT})")
        # 2) REST API 서버 (Flask, 별도 스레드)
        def run_flask():
            app.run(host='0.0.0.0', port=REST_PORT, threaded=True, use_reloader=False)
        threading.Thread(target=run_flask, daemon=True).start()
        self.log_signal.emit(f"[555] REST API 스레드 시작 (포트 {REST_PORT})")
        # 3) 주기적으로 장비 목록 시그널 (등록된 장비가 있으면 UI에 전달)
        while True:
            time.sleep(1.0)
            devs = _get_devices()
            if devs:
                self.device_list_signal.emit(devs)


class CamApp555(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = CamServerWorker555()
        self.worker.log_signal.connect(self.log_append)
        self.worker.device_list_signal.connect(self.on_device_list)
        threading.Thread(target=self.worker.start, daemon=True).start()
        self.initUI()
        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._update_video_frame)
        self._frame_timer.start(40)
        self._ocr_frame_count = 0
        self._last_frame = None
        os.makedirs(IMG_DIR, exist_ok=True)

    def initUI(self):
        layout = QVBoxLayout()
        layout.addWidget(QLabel("ESP32-CAM 서버 555 (REST API 5555, UDP 7072)"))
        btn_layout = QHBoxLayout()
        self.btn_cam_start = QPushButton("캠 영상 전송")
        self.btn_cam_stop = QPushButton("캠 영상 전송 중지")
        btn_layout.addWidget(self.btn_cam_start)
        btn_layout.addWidget(self.btn_cam_stop)
        layout.addLayout(btn_layout)
        flash_btn_layout = QHBoxLayout()
        self.btn_flash_on = QPushButton("플래시 ON")
        self.btn_flash_off = QPushButton("플래시 OFF")
        self.btn_flash_blink = QPushButton("플래시 깜빡임")
        flash_btn_layout.addWidget(self.btn_flash_on)
        flash_btn_layout.addWidget(self.btn_flash_off)
        flash_btn_layout.addWidget(self.btn_flash_blink)
        layout.addLayout(flash_btn_layout)
        # --- 장비/서버 설정 에디터 ---
        grp = QGroupBox("장비·서버 설정")
        grp_layout = QVBoxLayout()
        grp_layout.addWidget(QLabel("장비가 보고한 정보 (등록 시 수신):"))
        self.editor_device_info = QTextEdit()
        self.editor_device_info.setReadOnly(True)
        self.editor_device_info.setMaximumHeight(72)
        self.editor_device_info.setPlaceholderText("장비가 POST /api/device/register 호출 시 guid, name, ip 표시")
        grp_layout.addWidget(self.editor_device_info)
        grp_layout.addWidget(QLabel("서버 주소 (장비에 내려보낼 값, 수정 후 저장):"))
        grid = QGridLayout()
        grid.addWidget(QLabel("서버 호스트:"), 0, 0)
        self.edit_server_host = QLineEdit()
        self.edit_server_host.setPlaceholderText("192.168.0.4")
        self.edit_server_host.setText("192.168.0.4")
        grid.addWidget(self.edit_server_host, 0, 1)
        grid.addWidget(QLabel("REST 포트:"), 1, 0)
        self.edit_rest_port = QLineEdit()
        self.edit_rest_port.setPlaceholderText("5555")
        self.edit_rest_port.setText("5555")
        grid.addWidget(self.edit_rest_port, 1, 1)
        grid.addWidget(QLabel("UDP 포트:"), 2, 0)
        self.edit_udp_port = QLineEdit()
        self.edit_udp_port.setPlaceholderText("7072")
        self.edit_udp_port.setText("7072")
        grid.addWidget(self.edit_udp_port, 2, 1)
        grp_layout.addLayout(grid)
        self.btn_save_config = QPushButton("저장 후 장비에 반영")
        self.btn_save_config.clicked.connect(self._save_server_config)
        grp_layout.addWidget(self.btn_save_config)
        grp.setLayout(grp_layout)
        layout.addWidget(grp)
        self._refresh_server_edits_from_state()
        layout.addWidget(QLabel("캠 장비 목록 (REST 등록):"))
        self.device_list_widget = QListWidget()
        self.device_list_widget.setMaximumHeight(60)
        layout.addWidget(self.device_list_widget)
        layout.addWidget(QLabel("캠 영상 (UDP 수신):"))
        self.video_label = QLabel()
        self.video_label.setMinimumSize(320, 240)
        self.video_label.setStyleSheet("background-color: #333; color: #888;")
        self.video_label.setText("영상 대기 중...")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.video_label)
        capture_btn_layout = QHBoxLayout()
        self.btn_capture = QPushButton("캡쳐 저장")
        self.btn_capture.clicked.connect(self._save_capture)
        self.btn_ocr_test = QPushButton("이미지로 OCR 확인")
        self.btn_ocr_test.clicked.connect(self._ocr_test_from_image)
        capture_btn_layout.addWidget(self.btn_capture)
        capture_btn_layout.addWidget(self.btn_ocr_test)
        layout.addLayout(capture_btn_layout)
        layout.addWidget(QLabel("로그:"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)
        self.setLayout(layout)
        self.btn_cam_start.clicked.connect(self._api_cam_start)
        self.btn_cam_stop.clicked.connect(self._api_cam_stop)
        self.btn_flash_on.clicked.connect(self._api_flash_on)
        self.btn_flash_off.clicked.connect(self._api_flash_off)
        self.btn_flash_blink.clicked.connect(self._api_flash_blink)
        self.setWindowTitle("ESP32-CAM 서버 (555 REST)")
        self.resize(480, 640)
        if not _ocr_available:
            self.log_append("⚠ 번호판 OCR 비활성: pip install pytesseract 및 시스템에 tesseract-ocr 설치 후 사용")

    def _api_cam_start(self):
        _set_command("cam_start")
        self.log_append("📡 [명령] 캠 영상 전송 시작 (다음 폴링 시 ESP32에 전달)")

    def _api_cam_stop(self):
        _set_command("cam_stop")
        self.log_append("📡 [명령] 캠 영상 전송 중지")

    def _api_flash_on(self):
        _set_command("flash_on")
        self.log_append("📡 [명령] 플래시 ON")

    def _api_flash_off(self):
        _set_command("flash_off")
        self.log_append("📡 [명령] 플래시 OFF")

    def _api_flash_blink(self):
        _set_command("flash_blink")
        self.log_append("📡 [명령] 플래시 깜빡임(3회)")

    def _save_capture(self):
        if self._last_frame is None:
            self.log_append("⚠ 저장할 영상이 없습니다. 캠 영상을 먼저 재생하세요.")
            return
        fname = f"capture_{datetime.now():%Y%m%d_%H%M%S}.jpg"
        path = os.path.join(IMG_DIR, fname)
        try:
            cv2.imwrite(path, self._last_frame)
            self.log_append(f"📷 캡쳐 저장: {fname}")
        except Exception as e:
            self.log_append(f"⚠ 캡쳐 저장 실패: {e}")

    def _ocr_test_from_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "OCR 확인할 이미지 선택", IMG_DIR,
            "이미지 (*.jpg *.jpeg *.png *.bmp);;모든 파일 (*)"
        )
        if not path:
            return
        img = cv2.imread(path)
        if img is None:
            self.log_append("⚠ 이미지를 열 수 없습니다.")
            return
        ocr_ok, ocr_text = _ocr_image_to_text(img)
        dlg = OcrResultDialog(path, img, ocr_ok, ocr_text, self)
        dlg.exec()

    def on_device_list(self, lst):
        self.device_list_widget.clear()
        lines = []
        for item in lst:
            guid = (item.get("guid") or "").strip()
            name = (item.get("name") or "").strip()
            ip = (item.get("ip") or "").strip()
            self.device_list_widget.addItem(f"✓ {guid}  →  {name}" + (f"  [IP: {ip}]" if ip else ""))
            lines.append(f"guid: {guid}\nname: {name}\nip: {ip or '(미보고)'}")
        self.editor_device_info.setText("\n---\n".join(lines) if lines else "")
        self.log_append("📋 캠 장비 목록 갱신(555).")

    def _refresh_server_edits_from_state(self):
        cfg = _get_server_for_device()
        self.edit_server_host.setText(cfg.get("server_host", "192.168.0.4"))
        self.edit_rest_port.setText(str(cfg.get("rest_port", 5555)))
        self.edit_udp_port.setText(str(cfg.get("udp_port", 7072)))

    def _save_server_config(self):
        host = self.edit_server_host.text().strip() or "192.168.0.4"
        try:
            rp = int(self.edit_rest_port.text().strip() or "5555")
            up = int(self.edit_udp_port.text().strip() or "7072")
        except ValueError:
            self.log_append("⚠ 포트는 숫자로 입력하세요.")
            return
        _set_server_for_device(host, rp, up)
        self.log_append(f"✅ 서버 설정 저장됨 → host={host}, rest_port={rp}, udp_port={up}. 장비가 GET /api/device/config 폴링 시 자동 반영.")

    def _update_video_frame(self):
        if frame_queue.empty():
            return
        try:
            f_no, img = frame_queue.get_nowait()
        except Exception:
            return
        if img is None:
            return
        img = cv2.rotate(img, cv2.ROTATE_180)
        img = cv2.flip(img, 1)  # 좌우 반전
        img = np.ascontiguousarray(img)
        h, w, ch = img.shape
        bytes_per_line = ch * w
        qimg = QImage(img.data, w, h, bytes_per_line, QImage.Format.Format_BGR888).copy()
        self.video_label.setPixmap(
            QPixmap.fromImage(qimg).scaled(
                self.video_label.width(), self.video_label.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.video_label.setText("")
        self._last_frame = img.copy()
        # N프레임마다 번호판 OCR (별도 스레드로 UI 블로킹 방지)
        self._ocr_frame_count += 1
        if _ocr_available and self._ocr_frame_count % OCR_INTERVAL_FRAMES == 0:
            img_copy = img.copy()
            log_append = self.log_append
            def run_ocr():
                _ocr_license_plate(img_copy, lambda s: QTimer.singleShot(0, lambda: log_append(s)))
            threading.Thread(target=run_ocr, daemon=True).start()

    def log_append(self, line):
        self.log.append(line)
        self.log.moveCursor(self.log.textCursor().MoveOperation.End)


if __name__ == "__main__":
    app_qt = QApplication(sys.argv)
    app_qt.setStyle("Fusion")
    ex = CamApp555()
    ex.show()
    sys.exit(app_qt.exec())
