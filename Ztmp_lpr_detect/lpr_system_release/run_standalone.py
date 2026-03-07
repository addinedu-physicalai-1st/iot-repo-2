#!/usr/bin/env python3
"""
LPR 샘플 단독 실행 런처.

- 모델: 3.device_client/lpr_models/best.pt
- 포트 확인:     python run_standalone.py check
- UDP 입구 7070: python run_standalone.py 7070
- UDP 출구 7090: python run_standalone.py 7090
- 둘 다 동시 (입구+출구 한 창): python run_standalone.py both
- 웹캠 (ESP32 없이 OCR 테스트): python run_standalone.py webcam
"""
import os
import socket
import sys

# 프로젝트 루트 = 이 파일 기준 상위 두 단계 (run_standalone.py -> lpr_system_release -> Ztmp_lpr_detect -> 루트)
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))
_MODEL_PATH = os.path.join(_PROJECT_ROOT, "3.device_client", "lpr_models", "best.pt")


def check_udp_ports():
    """Check if UDP ports 7070 and 7090 are in use (e.g. 3.device_client running)."""
    print("Checking UDP ports (LPR enter 7070, exit 7090)...")
    for port in [7070, 7090]:
        label = "7070 (enter/입구)" if port == 7070 else "7090 (exit/출구)"
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.bind(("0.0.0.0", port))
            print(f"  Port {port}: FREE  – {label}")
        except OSError:
            print(f"  Port {port}: IN USE – {label} (e.g. 3.device_client running)")
        finally:
            s.close()
    print("If a port is IN USE, stop that app before running LPR standalone on that port.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower() in ("check", "--check", "-c"):
        check_udp_ports()
        sys.exit(0)

    os.chdir(_THIS_DIR)
    sys.path.insert(0, _THIS_DIR)
    import camera_controller

    # 둘 다 동시: 7070 + 7090 한 창에 표시 (모델 불필요)
    if len(sys.argv) > 1 and sys.argv[1].lower() == "both":
        camera_controller.detect_camera_dual(_MODEL_PATH, 0.10)
        sys.exit(0)

    if not os.path.isfile(_MODEL_PATH):
        print(f"[오류] 모델 없음: {_MODEL_PATH}")
        sys.exit(1)

    # UDP 포트: 기본 7070(입구), 출구는 7090 → python run_standalone.py 7090
    udp_port = 7070
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        udp_port = int(sys.argv[1])
        print(f"UDP port: {udp_port}")
    camera_controller.detect_camera("udp", _MODEL_PATH, 0.10, udp_port=udp_port)
