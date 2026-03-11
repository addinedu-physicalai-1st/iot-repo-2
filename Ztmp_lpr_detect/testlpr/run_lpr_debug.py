import os
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO
from paddleocr import PaddleOCR


BASE_DIR = Path(__file__).resolve().parent.parent.parent  # repo root

# 3.device_client 기준 경로들 재사용
DEVICE_CLIENT_DIR = BASE_DIR / "3.device_client"
DEBUG_DIR = DEVICE_CLIENT_DIR / "lpr_debug"
DEFAULT_MODEL = DEVICE_CLIENT_DIR / "lpr_models" / "best.pt"


def _extract_text(ocr_results):
    """현재 3.device_client 버전과 유사하게 숫자/한글만 모아 보기."""
    text_parts = []
    conf_sum = 0.0
    conf_count = 0

    if not ocr_results:
        return "", 0.0

    for line in ocr_results:
        if not line:
            continue
        for item in line:
            # item format: [ [box], (text, confidence) ]
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                content = item[1]
                if isinstance(content, (list, tuple)) and len(content) >= 2:
                    txt = str(content[0])
                    conf = float(content[1])
                    text_parts.append(txt)
                    conf_sum += conf
                    conf_count += 1

    raw = "".join(text_parts)
    # 번호판에 쓸 수 있는 문자만 남김
    clean = "".join(ch for ch in raw if ("0" <= ch <= "9") or ("가" <= ch <= "힣"))
    avg_conf = conf_sum / conf_count if conf_count > 0 else 0.0
    return clean, avg_conf


def main() -> None:
    model_path = Path(os.getenv("LPR_DEBUG_MODEL", str(DEFAULT_MODEL))).resolve()
    img_dir = Path(os.getenv("LPR_DEBUG_DIR", str(DEBUG_DIR))).resolve()

    if not model_path.is_file():
        print(f"[LPR-TEST] 모델 파일을 찾을 수 없습니다: {model_path}")
        return
    if not img_dir.is_dir():
        print(f"[LPR-TEST] 디버그 이미지 폴더가 없습니다: {img_dir}")
        return

    print(f"[LPR-TEST] YOLO 모델: {model_path}")
    print(f"[LPR-TEST] 테스트 이미지 폴더: {img_dir}")

    yolo = YOLO(str(model_path))
    ocr = PaddleOCR(lang="korean", use_textline_orientation=True, enable_mkldnn=False)

    images = sorted(img_dir.glob("plate_*.jpg"))
    if not images:
        print("[LPR-TEST] plate_*.jpg 파일이 없습니다. 3.device_client에서 디버그 저장을 먼저 실행해 주세요.")
        return

    for img_path in images:
        img = cv2.imread(str(img_path))
        if img is None:
            print(f"[LPR-TEST] 이미지 로드 실패: {img_path}")
            continue

        h, w = img.shape[:2]
        # 현재 detector 와 동일한 conf=0.12 기준으로 번호판 영역 검출
        results = yolo(img, conf=0.12, verbose=False)
        boxes = results[0].boxes.xyxy.cpu().numpy() if len(results) > 0 and results[0].boxes is not None else []

        if len(boxes) == 0:
            print(f"{img_path.name}: YOLO box 없음")
            continue

        print(f"\n=== {img_path.name} ===")
        for idx, box in enumerate(boxes):
            x1, y1, x2, y2 = map(int, box)
            pad_y = max(5, int((y2 - y1) * 0.15))
            pad_x = max(5, int((x2 - x1) * 0.05))
            y1_pad = max(0, y1 - pad_y)
            y2_pad = min(h, y2 + pad_y)
            x1_pad = max(0, x1 - pad_x)
            x2_pad = min(w, x2 + pad_x)
            cropped = img[y1_pad:y2_pad, x1_pad:x2_pad]
            if cropped.size == 0:
                print(f"  box#{idx}: 크롭 영역 없음")
                continue

            # detector 와 동일하게 4배 확대
            ch, cw = cropped.shape[:2]
            scaled = cv2.resize(cropped, (cw * 4, ch * 4), interpolation=cv2.INTER_CUBIC)

            try:
                ocr_results = ocr.ocr(scaled)
                text, conf = _extract_text(ocr_results)
                if text:
                    print(f"  box#{idx}: '{text}' (conf≈{conf:.2f})")
                else:
                    print(f"  box#{idx}: <no text> (conf≈{conf:.2f})")
            except Exception as e:
                print(f"  box#{idx}: OCR 오류: {e}")


if __name__ == "__main__":
    main()

