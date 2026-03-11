"""
웹캠(또는 USB 카메라) 영상을 이용해
YOLO 번호판 검출 + PaddleOCR 한글 인식을 테스트하는 단독 프로그램.

- 기본 카메라: 0번 (`--camera 0` 으로 변경 가능)
- 모델: 이 폴더의 `best.pt` 가 우선, 없으면 `3.device_client/lpr_models/best.pt`
- ESP32 UDP 없이, 순수 PC 웹캠만으로 인식 파이프라인 점검용
"""

import argparse
import os
import re
import time

import cv2
import numpy as np
from ultralytics import YOLO
from paddleocr import PaddleOCR


def _resolve_plate_model(script_dir: str) -> str:
    """이 스크립트와 동일한 폴더의 best.pt 를 우선 사용하고, 없으면 3.device_client 경로 사용."""
    local_model = os.path.join(script_dir, "best.pt")
    if os.path.isfile(local_model):
        return local_model

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
    fallback = os.path.join(project_root, "3.device_client", "lpr_models", "best.pt")
    return fallback


def run_webcam_ocr(
    camera_id: int | str,
    plate_model_path: str,
    plate_conf_threshold: float = 0.12,
) -> None:
    print(f"[WEB-TEST] Plate model: {plate_model_path}")
    model = YOLO(plate_model_path)

    print("[WEB-TEST] Initializing PaddleOCR (korean)...")
    ocr = PaddleOCR(
        lang="korean",
        use_textline_orientation=True,
        enable_mkldnn=False,
    )

    # 카메라 열기
    if isinstance(camera_id, str) and not camera_id.isdigit():
        cam_source = camera_id
    else:
        cam_source = int(camera_id)

    cap = cv2.VideoCapture(cam_source)
    if not cap.isOpened():
        print(f"[WEB-TEST] Error: Could not open camera: {cam_source}")
        return

    print("[WEB-TEST] Press 'q' to quit.")

    last_ocr_text = ""
    last_trigger_time = 0.0
    COOLDOWN_SECONDS = 3.0
    STABILITY_THRESHOLD = 3
    plate_stability_counter = 0
    consecutive_empty_frames = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[WEB-TEST] Error: Could not read frame.")
            break

        annotated = frame.copy()
        h, w = frame.shape[:2]

        # YOLO로 번호판 박스 검출
        results = model(frame, conf=plate_conf_threshold, verbose=False)
        boxes = results[0].boxes.xyxy.cpu().numpy() if results and results[0].boxes is not None else []

        now = time.time()
        is_cooldown = (now - last_trigger_time) < COOLDOWN_SECONDS

        if len(boxes) == 0:
            consecutive_empty_frames += 1
            if consecutive_empty_frames > 3:
                plate_stability_counter = 0
        else:
            consecutive_empty_frames = 0
            if not is_cooldown:
                plate_stability_counter += 1

        for box in boxes:
            x1, y1, x2, y2 = map(int, box)

            pad_y = max(5, int((y2 - y1) * 0.15))
            pad_x = max(5, int((x2 - x1) * 0.05))
            y1_pad = max(0, y1 - pad_y)
            y2_pad = min(h, y2 + pad_y)
            x1_pad = max(0, x1 - pad_x)
            x2_pad = min(w, x2 + pad_x)

            cropped = frame[y1_pad:y2_pad, x1_pad:x2_pad]
            if cropped.size == 0:
                continue

            ch, cw = cropped.shape[:2]
            scaled = cv2.resize(cropped, (cw * 4, ch * 4), interpolation=cv2.INTER_CUBIC)

            # 안정도 & 쿨다운 조건 만족 시 한 번만 OCR 수행
            if plate_stability_counter >= STABILITY_THRESHOLD and not is_cooldown:
                print("[WEB-TEST] Stable plate detected → OCR...")
                last_trigger_time = now
                plate_stability_counter = 0

                ocr_results = ocr.ocr(scaled)
                raw_text = ""
                if ocr_results:
                    for res in ocr_results:
                        if hasattr(res, "rec_texts") and res.rec_texts:
                            raw_text += "".join(res.rec_texts)
                        elif isinstance(res, dict) and "rec_texts" in res:
                            raw_text += "".join(res["rec_texts"])
                        elif isinstance(res, (list, tuple)) and res:
                            for line in res:
                                if line and len(line) >= 2:
                                    val = line[1]
                                    if isinstance(val, (list, tuple)):
                                        raw_text += str(val[0])
                                    else:
                                        raw_text += str(val)

                final_text = "".join(re.findall(r"[0-9가-힣]", raw_text))
                last_ocr_text = final_text

                if final_text:
                    print(f"[WEB-TEST] OCR: '{final_text}' (raw='{raw_text}')")
                else:
                    print(f"[WEB-TEST] OCR: <no text> (raw='{raw_text}')")

            # 박스 및 텍스트 오버레이
            color = (0, 165, 255) if is_cooldown else (0, 255, 0)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

        if last_ocr_text:
            cv2.putText(
                annotated,
                last_ocr_text,
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 255, 0),
                2,
            )

        cv2.imshow("Webcam LPR OCR Test", annotated)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_model = _resolve_plate_model(script_dir)

    parser = argparse.ArgumentParser(description="Webcam-based LPR OCR tester (YOLO + PaddleOCR)")
    parser.add_argument(
        "--camera",
        type=str,
        default="0",
        help="카메라 인덱스 (예: 0) 또는 비디오 경로",
    )
    parser.add_argument(
        "--plate-model",
        type=str,
        default=default_model,
        help="번호판 YOLO 모델 경로 (기본: 이 폴더의 best.pt 또는 3.device_client/lpr_models/best.pt)",
    )
    parser.add_argument(
        "--plate-conf",
        type=float,
        default=0.12,
        help="YOLO 번호판 검출 confidence 임계값 (기본: 0.12)",
    )
    args = parser.parse_args()

    model_path = os.path.abspath(args.plate_model)
    if not os.path.isfile(model_path):
        print(f"[WEB-TEST] 모델 파일을 찾을 수 없습니다: {model_path}")
        raise SystemExit(1)

    run_webcam_ocr(args.camera, model_path, plate_conf_threshold=args.plate_conf)

