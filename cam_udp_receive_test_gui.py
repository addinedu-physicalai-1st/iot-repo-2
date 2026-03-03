import socket
import cv2
import numpy as np
import time
import threading
from queue import Queue

# 1. 설정
UDP_IP = "0.0.0.0"
UDP_PORT = 7070
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024) # 4MB 수신 버퍼
sock.bind((UDP_IP, UDP_PORT))

# 최신 프레임만 유지하는 큐
frame_queue = Queue(maxsize=2)

def udp_receiver():
    """패킷 수집, 체크섬 검증 및 이미지 조립 쓰레드"""
    frames = {}
    last_frame_no = -1
    
    while True:
        try:
            # 헤더 4바이트: f_no, p_no, is_last(1=마지막패킷), checksum
            data, addr = sock.recvfrom(2048)
            if len(data) < 5: continue

            f_no = data[0]
            p_no = data[1]
            is_last = data[2]  # 송신측이 명시한 마지막 패킷 여부 (0xff 0xd9 추측 제거)
            received_checksum = data[3]
            chunk = data[4:]

            # 패킷 들어올 때마다 즉시 출력 (수신 확인용)
            print(f"[PKT] f_no={f_no} p_no={p_no} is_last={is_last} len={len(chunk)}B from {addr[0]}:{addr[1]}")

            if f_no < last_frame_no and (last_frame_no - f_no) < 200:
                continue

            if f_no not in frames:
                if len(frames) > 3:
                    del frames[min(frames.keys())]
                frames[f_no] = {'chunks': {}, 'target_checksum': None}
            
            frames[f_no]['chunks'][p_no] = chunk

            # 마지막 패킷은 송신측 헤더(is_last==1)로만 판별 → 체크섬 오판 방지
            if is_last == 1:
                frames[f_no]['target_checksum'] = received_checksum

            target = frames[f_no].get('target_checksum')
            if target is not None:
                indices = sorted(frames[f_no]['chunks'].keys())
                # 청크 완전성: 0번부터 마지막 패킷 번호까지 모두 있음
                if len(indices) > 0 and indices[0] == 0 and indices[-1] == p_no and len(indices) == p_no + 1:
                    full_data = b"".join([frames[f_no]['chunks'][i] for i in indices])
                    
                    # 2. 체크섬 검증 수행
                    # 파이썬에서 8비트 합산 계산 (Overflow 고려하여 256으로 나눈 나머지)
                    calculated_checksum = sum(full_data) % 256
                    
                    if calculated_checksum == target:
                        nparr = np.frombuffer(full_data, dtype=np.uint8)
                        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                        if img is not None:
                            if frame_queue.full(): frame_queue.get()
                            frame_queue.put((f_no, img))
                            last_frame_no = f_no
                    else:
                        print(f"Frame {f_no}: Checksum Error! (Cal:{calculated_checksum} != Recv:{target})")
                    frames = {k: v for k, v in frames.items() if k > f_no}
        except Exception as e:
            print(f"Recv Error: {e}")

# 쓰레드 실행
threading.Thread(target=udp_receiver, daemon=True).start()

# 2. 메인 루프 (출력 및 처리)
prev_time = 0
while True:
    if not frame_queue.empty():
        f_no, img = frame_queue.get()
        
        # 실제 수신 FPS 계산
        curr_time = time.time()
        fps = 1 / (curr_time - prev_time) if prev_time != 0 else 0
        prev_time = curr_time

        # --- 번호판 인식을 위한 기본 흑백 처리 예시 ---
        # gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        cv2.putText(img, f"Frame: {f_no} | FPS: {fps:.1f}", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.imshow("LPR Real-time Stream", img)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cv2.destroyAllWindows()
sock.close()
