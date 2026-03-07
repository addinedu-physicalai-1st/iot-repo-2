import argparse
import os
import cv2
import numpy as np
import time
import re
from ultralytics import YOLO
from PIL import ImageFont, ImageDraw, Image
import torch
import json
from paddleocr import PaddleOCR

KOR_MAPPING = {
    'ba': '바', 'beo': '버', 'bo': '보', 'bu': '부', 'busan': '부산', 
    'da': '다', 'daegu': '대구', 'daejeon': '대전', 'deo': '더', 'do': '도', 'du': '두', 
    'eo': '어', 'ga': '가', 'geo': '거', 'go': '고', 'gu': '구', 'gyeonggi': '경기', 
    'ha': '하', 'heo': '허', 'ho': '호', 'ja': '자', 'jeo': '저', 'jo': '조', 'ju': '주', 
    'ma': '마', 'meo': '머', 'mo': '모', 'mu': '무', 'na': '나', 'neo': '너', 'no': '노', 
    'nu': '누', 'o': '오', 'ra': '라', 'reo': '러', 'ro': '로', 'ru': '루', 
    'sa': '사', 'seo': '서', 'seoul': '서울', 'so': '소', 'su': '수', 'u': '우',
    # Support for models with char_ prefix
    'char_ah': '아', 'char_ba': '바', 'char_bu': '부', 'char_buk': '북', 'char_cha': '차', 'char_chang': '창',
    'char_cheon': '천', 'char_choo': '추', 'char_chung': '충', 'char_dae': '대', 'char_du': '두',
    'char_ga': '가', 'char_geo': '거', 'char_gga': '까', 'char_go': '고', 'char_gu': '구', 'char_gyo': '교',
    'char_heo': '허', 'char_ho': '호', 'char_hole': '홀', 'char_in': '인', 'char_ja': '자', 'char_jang': '장',
    'char_jeon': '전', 'char_ji': '지', 'char_jo': '조', 'char_joo': '주', 'char_jun': '준', 'char_kang': '강',
    'char_ki': '기', 'char_kyung': '경', 'char_mi': '미', 'char_na': '나', 'char_nam': '남', 'char_no': '노',
    'char_oe': '외', 'char_oh': '오', 'char_oul': '울', 'char_ra': '라', 'char_ro': '로', 'char_roo': '루',
    'char_sa': '사', 'char_san': '산', 'char_seo': '서', 'char_si': '시', 'char_won': '원', 'char_woo': '우',
    'char_yook': '육', 'char_young': '영', 'slash': '/', '-': '-'
}

def load_cnn_model(model_path, classes_path):
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    with open(classes_path, 'r') as f:
        class_names = json.load(f)
    model = models.mobilenet_v2()
    num_ftrs = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(num_ftrs, len(class_names))
    model.load_state_dict(torch.load(model_path, map_location=device, weights_only=True))
    model = model.to(device)
    model.eval()
    
    transform = transforms.Compose([
        transforms.ToPILImage(),
        transforms.Resize((64, 64)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
    return model, class_names, transform, device


import socket
import threading
import time

class Esp32UdpReceiver:
    def __init__(self, port=7070):
        self.port = port
        self._sock = None
        self._thread = None
        self._running = False
        self.latest_frame = None

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        try:
            self._sock.bind(("0.0.0.0", self.port))
        except OSError as e:
            if "Address already in use" in str(e) or e.errno == 98:
                print(f"[ERROR] Port {self.port} is already in use. Stop 3.device_client (or any other app using this port) and try again.")
            raise
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[ESP32] UDP listening on port {self.port}" + (f" (exit gate / 출구 LPR)" if self.port == 7090 else " (enter / 입구 LPR)"))

    def _loop(self):
        # Same protocol as 3.device_client/esp32_receiver.py:
        # - Legacy: [f_no, p_no, checksum] + data; EOI (0xFFD9) in chunk → use that checksum.
        # - 555:    [f_no, p_no, is_last, checksum] + data; is_last==1 → use that checksum.
        frames = {}
        last_frame_no = -1
        first_packet_received = False

        while self._running:
            try:
                data, addr = self._sock.recvfrom(2048)
                if not first_packet_received:
                    print(f"DEBUG: Received first UDP packet from {addr}")
                    first_packet_received = True

                if len(data) < 4:
                    continue

                f_no = data[0]
                p_no = data[1]

                # Header format auto-detect (match esp32_receiver.py)
                if len(data) >= 5 and data[2] in (0, 1):
                    # 555 format: [f_no, p_no, is_last, checksum] + data
                    is_last = data[2]
                    received_checksum = data[3]
                    chunk = data[4:]
                else:
                    # Legacy: [f_no, p_no, checksum] + data
                    is_last = -1
                    received_checksum = data[2]
                    chunk = data[3:]

                if f_no < last_frame_no and (last_frame_no - f_no) < 200:
                    continue

                if f_no not in frames:
                    if len(frames) > 3:
                        del frames[min(frames.keys())]
                    frames[f_no] = {"chunks": {}, "target_checksum": None}

                entry = frames[f_no]
                chunks = entry["chunks"]
                chunks[p_no] = chunk

                # 555: set target_checksum on last packet; legacy: set when EOI in chunk
                if is_last == 1:
                    entry["target_checksum"] = received_checksum
                elif is_last != 0 and b"\xff\xd9" in chunk:
                    entry["target_checksum"] = received_checksum

                target = entry.get("target_checksum")
                if target is not None:
                    indices = sorted(chunks.keys())
                    if indices and indices[0] == 0 and len(indices) == indices[-1] + 1:
                        full_data = b"".join(chunks[i] for i in indices)
                        calculated_checksum = sum(full_data) % 256
                        if calculated_checksum == target:
                            nparr = np.frombuffer(full_data, dtype=np.uint8)
                            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                            if img is not None:
                                self.latest_frame = img
                                last_frame_no = f_no
                        frames = {k: v for k, v in frames.items() if k > f_no}
            except Exception as e:
                pass

    def stop(self):
        self._running = False
        if self._sock:
            self._sock.close()

def put_korean_text(img, text, position, font_size=40, color=(0, 255, 0)):
    font_paths = [
        "/home/joey/Desktop/data/NanumGothic.ttf", 
        "NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
    ]
    font = None
    for path in font_paths:
        try:
            font = ImageFont.truetype(path, font_size)
            break
        except IOError:
            continue
            
    if font is None:
        cv2.putText(img, text, position, cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
        return img
        
    img_pil = Image.fromarray(img)
    draw = ImageDraw.Draw(img_pil)
    rgb_color = (color[2], color[1], color[0]) 
    draw.text(position, text, font=font, fill=rgb_color)
    return np.array(img_pil)

def detect_camera(camera_id, plate_model_path, plate_conf_threshold=0.25, udp_port=7070):
    print(f"Loading Plate Model from {plate_model_path}...")
    plate_model = YOLO(plate_model_path)
    
    print("Initializing PaddleOCR...")
    # PP-OCRv5 requires use_textline_orientation instead of use_angle_cls
    # Disabling mkldnn to avoid Attribute error in OneDNN/PIR environment
    ocr = PaddleOCR(
        lang='korean', 
        use_textline_orientation=True, 
        enable_mkldnn=False
    )
    
    udp_receiver = None
    if str(camera_id).lower() == 'udp':
        print(f"Starting UDP Receiver for ESP32 on port {udp_port}...")
        udp_receiver = Esp32UdpReceiver(port=udp_port)
        udp_receiver.start()
    else:
        print(f"Opening camera ID: {camera_id}...")
        cap = cv2.VideoCapture(camera_id)
        if not cap.isOpened():
            print("Error: Could not open camera.")
            return

    print("Press 'q' to quit.")
    
    # --- Tracking variables for stabilization ---
    plate_history = []
    MAX_HISTORY = 10  # Reduced from 30 for faster adaptation
    frames_since_last_detect = 0
    stable_text = ""
    last_ocr_time = 0
    last_ocr_text = ""
    # Smart Trigger variables
    plate_stability_counter = 0
    consecutive_empty_frames = 0
    last_trigger_time = 0
    COOLDOWN_SECONDS = 5.0
    STABILITY_THRESHOLD = 5
    # ----------------------------------------
    
    # --- YOLO Asynchronous Threading Setup ---
    import threading
    yolo_lock = threading.Lock()
    shared_boxes = []
    latest_frame_for_yolo = None
    yolo_running = True
    
    def yolo_worker():
        nonlocal shared_boxes, latest_frame_for_yolo
        while yolo_running:
            frame_to_process = None
            with yolo_lock:
                if latest_frame_for_yolo is not None:
                    frame_to_process = latest_frame_for_yolo
                    latest_frame_for_yolo = None
                    
            if frame_to_process is not None:
                # Run heavy YOLO inference in background
                results = plate_model(frame_to_process, conf=plate_conf_threshold, verbose=False)
                new_boxes = results[0].boxes.xyxy.cpu().numpy()
                with yolo_lock:
                    shared_boxes = new_boxes
            else:
                time.sleep(0.01) # Sleep to avoid pegging CPU when no frames arrive
                
    yolo_thread = threading.Thread(target=yolo_worker, daemon=True)
    yolo_thread.start()
    # -----------------------------------------
    
    cv2.namedWindow('Cascaded YOLO LPR Real-time', cv2.WINDOW_NORMAL)
    # Placeholder so the window opens immediately (before any UDP frame arrives)
    placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
    placeholder[:] = (40, 40, 40)
    cv2.putText(placeholder, f"Waiting for UDP stream on port {udp_port}...", (30, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
    if udp_port == 7090:
        cv2.putText(placeholder, "Exit gate LPR camera (7090).", (30, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 255, 100), 2)
    cv2.putText(placeholder, "Connect ESP32 LPR to this port. Close 3.device_client if port in use.", (30, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (150, 150, 150), 2)
    cv2.imshow('Cascaded YOLO LPR Real-time', placeholder)
    cv2.waitKey(1)
    
    while True:
        if udp_receiver:
            if udp_receiver.latest_frame is None:
                cv2.imshow('Cascaded YOLO LPR Real-time', placeholder)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                time.sleep(0.01)
                continue
            frame = udp_receiver.latest_frame.copy()
            # Clear latest frame so we don't process it twice if it hasn't updated
            udp_receiver.latest_frame = None 
            
            # Flip the frame horizontally to fix the mirrored ESP32 camera view
            frame = cv2.flip(frame, 1)
        else:
            ret, frame = cap.read()
            if not ret:
                print("Error: Could not read frame.")
                break
                
            
        # Main camera feed is now color (Grayscale conversion removed)
        annotated_frame = frame.copy() # Use raw frame so we don't draw false positive boxes
        
        # Pass the latest frame to the background thread
        with yolo_lock:
            latest_frame_for_yolo = frame.copy()
            # Grab the latest detection boxes computed by the background thread
            boxes = shared_boxes
        
        # Smart Trigger: Track if a plate is currently visible
        current_time = time.time()
        is_cooldown = (current_time - last_trigger_time) < COOLDOWN_SECONDS
        
        if len(boxes) == 0:
            consecutive_empty_frames += 1
            if consecutive_empty_frames > 3:
                plate_stability_counter = 0 # Reset counter if plate is lost
        else:
            consecutive_empty_frames = 0
            if not is_cooldown:
                plate_stability_counter += 1
            
        for idx, box in enumerate(boxes):
            x1, y1, x2, y2 = map(int, box)
            
            # Ensure coordinates are within frame bounds and add padding
            h, w = frame.shape[:2]
            pad_y = max(5, int((y2 - y1) * 0.15))
            pad_x = max(5, int((x2 - x1) * 0.05))
            y1_pad = max(0, y1 - pad_y)
            y2_pad = min(h, y2 + pad_y)
            x1_pad = max(0, x1 - pad_x)
            x2_pad = min(w, x2 + pad_x)
            
            # Crop the license plate area from original frame with padding
            cropped_plate = frame[y1_pad:y2_pad, x1_pad:x2_pad]
            
            if cropped_plate.size > 0:
                # 1. Scale up further (4x) for low-resolution ESP32 Korean characters
                h_crop, w_crop = cropped_plate.shape[:2]
                scaled_plate = cv2.resize(cropped_plate, (w_crop * 4, h_crop * 4), interpolation=cv2.INTER_CUBIC)
                
                # We skip color and edge enhancements to save CPU and maximize FPS for the ESP32 stream
                processed_plate = scaled_plate
                
                # -- SMART TRIGGER OCR EVENT --
                if plate_stability_counter >= STABILITY_THRESHOLD and not is_cooldown:
                    print("\n[TRIGGER] Stable plate detected. Running OCR...")
                    # Update trigger time so we enter cooldown immediately
                    last_trigger_time = current_time
                    plate_stability_counter = 0
                    
                    # Save the latest capture quietly
                    # cv2.imshow("Captured Plate (Raw)", processed_plate)
                    cv2.imwrite("latest_capture.jpg", processed_plate)
                    
                    # 4. PaddleOCR Inference (Heavy, done only once per trigger)
                    ocr_results = ocr.ocr(processed_plate)
                    
                    final_text = ""
                    if ocr_results:
                        for res in ocr_results:
                            if hasattr(res, 'rec_texts') and res.rec_texts:
                                final_text += "".join(res.rec_texts)
                            elif isinstance(res, dict) and 'rec_texts' in res:
                                 final_text += "".join(res['rec_texts'])
    
                        # Extract only Korean characters and digits
                        final_text = "".join(re.findall(r'[0-9가-힣]', final_text))
                        last_ocr_text = final_text
                    else:
                        final_text = ""
                        last_ocr_text = ""
                        
                    if len(final_text) >= 5: # Typical plate length
                        # Print JSON to simulate server response
                        import json
                        response = {
                            "success": True,
                            "plate_text": final_text,
                            "box": [x1, y1, x2, y2],
                            "event": "SmartTrigger"
                        }
                        print(f"--- TRIGGER EVENT RESPONSE ---\n{json.dumps(response, ensure_ascii=False)}\n")
                    else:
                        print(f"OCR failed or text too short: '{final_text}'. Please push the car a little bit front.\n")
                        last_ocr_text = ""
                        
            # Draw standard YOLO box (green if ready, orange if cooldown)
            box_color = (0, 165, 255) if is_cooldown else (0, 255, 0)
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), box_color, 2)
            
            if last_ocr_text:
                # Use PIL for Korean text overlay
                annotated_frame = put_korean_text(annotated_frame, last_ocr_text, (x1, max(30, y1 - 40)), font_size=30, color=(0, 255, 0))
                
        # ---------------------------
        
        # Display the frame
        cv2.imshow("Cascaded YOLO LPR Real-time", annotated_frame)

        # Break the loop if 'q' is pressed
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
            
    yolo_running = False
            
    if udp_receiver:
        udp_receiver.stop()
    else:
        cap.release()
    cv2.destroyAllWindows()


def detect_camera_dual(plate_model_path, plate_conf_threshold=0.25):
    """
    Both ESP32 LPR cams (7070 enter, 7090 exit) – one window, side by side.
    Use when both cams are up; both streams open in a single view.
    """
    print("Starting UDP receivers for BOTH cams (Enter 7070, Exit 7090)...")
    recv_7070 = Esp32UdpReceiver(port=7070)
    recv_7090 = Esp32UdpReceiver(port=7090)
    try:
        recv_7070.start()
    except OSError as e:
        print(f"[ERROR] Port 7070 in use: {e}")
        return
    try:
        recv_7090.start()
    except OSError as e:
        print(f"[ERROR] Port 7090 in use: {e}")
        recv_7070.stop()
        return

    H = 360
    W = 640
    placeholder = np.zeros((H, W, 3), dtype=np.uint8)
    placeholder[:] = (40, 40, 40)
    cv2.putText(placeholder, "Waiting...", (W//2 - 80, H//2 - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (180, 180, 180), 2)

    cv2.namedWindow("LPR Dual – Enter (7070) | Exit (7090)", cv2.WINDOW_NORMAL)
    combined = np.zeros((H, W * 2, 3), dtype=np.uint8)
    combined[:, :W] = placeholder
    combined[:, W:] = placeholder
    cv2.putText(combined, "Enter 7070", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
    cv2.putText(combined, "Exit 7090", (W + 20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
    cv2.imshow("LPR Dual – Enter (7070) | Exit (7090)", combined)
    cv2.waitKey(1)

    try:
        while True:
            frame_enter = recv_7070.latest_frame
            frame_exit = recv_7090.latest_frame
            if frame_enter is not None:
                recv_7070.latest_frame = None
                frame_enter = cv2.flip(frame_enter, 1)
            if frame_exit is not None:
                recv_7090.latest_frame = None
                frame_exit = cv2.flip(frame_exit, 1)

            left = cv2.resize(frame_enter, (W, H), interpolation=cv2.INTER_AREA) if frame_enter is not None else placeholder.copy()
            right = cv2.resize(frame_exit, (W, H), interpolation=cv2.INTER_AREA) if frame_exit is not None else placeholder.copy()
            cv2.putText(left, "Enter 7070", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(right, "Exit 7090", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            combined = np.hstack([left, right])
            cv2.imshow("LPR Dual – Enter (7070) | Exit (7090)", combined)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        recv_7070.stop()
        recv_7090.stop()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    # 기본 모델 경로: 이 스크립트와 같은 폴더의 best.pt (실행 위치와 무관)
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    _default_plate_model = os.path.join(_script_dir, "best.pt")

    parser = argparse.ArgumentParser(description="LPR Controller for Camera Feed with Cascaded YOLO")
    parser.add_argument("--plate-model", type=str, default=_default_plate_model, help="Path to plate YOLO model (default: same dir as script)")
    parser.add_argument("--camera", type=str, default="udp", help="Camera device index (e.g., 0) or 'udp' for ESP32-CAM stream")
    parser.add_argument("--udp-port", type=int, default=7070, help="UDP port for ESP32 stream (입구 7070, 출구 7090, default: 7070)")
    parser.add_argument("--plate-conf", type=float, default=0.10, help="Confidence threshold for plate detection (default: 0.10)")
    args = parser.parse_args()

    plate_path = os.path.abspath(args.plate_model)
    if not os.path.isfile(plate_path):
        print(f"[오류] 모델 파일 없음: {plate_path}")
        print("  - 이 폴더(lpr_system_release)에 best.pt 를 두거나")
        print("  - --plate-model 3.device_client/lpr_models/best.pt 처럼 경로를 지정하세요.")
        raise SystemExit(1)

    # Check if camera argument is a digit (local webcam) or a URL (IP cam like ESP32)
    cam_source = int(args.camera) if args.camera.isdigit() else args.camera
    detect_camera(cam_source, plate_path, args.plate_conf, udp_port=args.udp_port)
