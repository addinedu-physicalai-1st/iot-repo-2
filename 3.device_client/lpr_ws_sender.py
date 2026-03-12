"""
3.device_client → 2.client 로 입구/출구 LPR 실시간 영상을 WebSocket으로 전송.
입구·출구 각각 별도 스레드·연결로 분리해 안정적으로 서비스.
프로토콜: 바이너리 = 1바이트 채널(0=입구, 1=출구) + JPEG 바이트.
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, List, Optional

import cv2

try:
    import websockets
    _WS_AVAILABLE = True
except ImportError:
    _WS_AVAILABLE = False


def _frame_to_jpeg(img: Any) -> Optional[bytes]:
    if img is None:
        return None
    try:
        _, buf = cv2.imencode(".jpg", img)
        return buf.tobytes()
    except Exception:
        return None


async def _entry_sender_loop(ws_url: str, get_entry_frame: Any) -> None:
    """입구 전용: WebSocket 한 연결로 0x00 + JPEG 만 전송."""
    while True:
        try:
            async with websockets.connect(ws_url, max_size=2**20) as ws:
                while True:
                    entry = get_entry_frame()
                    if entry is not None:
                        _, img = entry
                        jpeg = _frame_to_jpeg(img)
                        if jpeg:
                            await ws.send(b"\x00" + jpeg)
                    await asyncio.sleep(0.04)
        except Exception:
            pass
        time.sleep(2.0)


async def _exit_sender_loop(ws_url: str, get_exit_frame: Any) -> None:
    """출구 전용: WebSocket 한 연결로 0x01 + JPEG 만 전송."""
    while True:
        try:
            async with websockets.connect(ws_url, max_size=2**20) as ws:
                while True:
                    exit_f = get_exit_frame()
                    if exit_f is not None:
                        _, img = exit_f
                        jpeg = _frame_to_jpeg(img)
                        if jpeg:
                            await ws.send(b"\x01" + jpeg)
                    await asyncio.sleep(0.04)
        except Exception:
            pass
        time.sleep(2.0)


def _run_entry_sender(ws_url: str, get_entry_frame: Any) -> None:
    """입구 송신 루프 (스레드에서 호출)."""
    if not _WS_AVAILABLE or not ws_url:
        return
    asyncio.run(_entry_sender_loop(ws_url, get_entry_frame))


def _run_exit_sender(ws_url: str, get_exit_frame: Any) -> None:
    """출구 송신 루프 (스레드에서 호출)."""
    if not _WS_AVAILABLE or not ws_url:
        return
    asyncio.run(_exit_sender_loop(ws_url, get_exit_frame))


def start_lpr_ws_sender_thread(
    entry_url: str,
    exit_url: str,
    get_entry_frame: Any,
    get_exit_frame: Any,
) -> Optional[List[threading.Thread]]:
    """입구·출구 각각 별도 WebSocket 송신 스레드 2개 기동. entry_url/exit_url 은 2.client 입구·출구 포트 각각."""
    if not _WS_AVAILABLE:
        return None
    threads: List[threading.Thread] = []
    if entry_url:
        t_entry = threading.Thread(
            target=_run_entry_sender,
            args=(entry_url, get_entry_frame),
            daemon=True,
        )
        t_entry.start()
        threads.append(t_entry)
    if exit_url:
        t_exit = threading.Thread(
            target=_run_exit_sender,
            args=(exit_url, get_exit_frame),
            daemon=True,
        )
        t_exit.start()
        threads.append(t_exit)
    return threads if threads else None
