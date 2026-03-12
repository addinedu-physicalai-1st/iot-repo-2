"""
LPR 실시간 영상 수신용 WebSocket 서버.
입구·출구 각각 별도 스레드·포트로 수신해 안정적으로 서비스.
- 입구: port_entry (기본 8765) → queue에 (0, jpeg_bytes)
- 출구: port_exit (기본 8766) → queue에 (1, jpeg_bytes)
"""
from __future__ import annotations

import asyncio
import queue
import threading
from typing import List, Optional

try:
    import websockets
    _WS_AVAILABLE = True
except ImportError:
    _WS_AVAILABLE = False


def _run_entry_server(
    host: str,
    port: int,
    frame_queue: "queue.Queue[tuple[int, bytes]]",
) -> None:
    """입구 전용 서버 스레드: 수신 바이너리 → (0, jpeg) 로 큐에 넣음."""
    if not _WS_AVAILABLE:
        return

    async def _handler(ws: any) -> None:
        try:
            async for raw in ws:
                if isinstance(raw, bytes) and raw:
                    jpeg = raw[1:] if len(raw) >= 1 and raw[0] == 0x00 else raw
                    if jpeg:
                        try:
                            frame_queue.put((0, jpeg), block=False)
                        except queue.Full:
                            pass
        except Exception:
            pass

    async def _main() -> None:
        async with websockets.serve(_handler, host, port, max_size=2**20):
            await asyncio.Future()

    asyncio.run(_main())


def _run_exit_server(
    host: str,
    port: int,
    frame_queue: "queue.Queue[tuple[int, bytes]]",
) -> None:
    """출구 전용 서버 스레드: 수신 바이너리 → (1, jpeg) 로 큐에 넣음."""
    if not _WS_AVAILABLE:
        return

    async def _handler(ws: any) -> None:
        try:
            async for raw in ws:
                if isinstance(raw, bytes) and raw:
                    jpeg = raw[1:] if len(raw) >= 1 and raw[0] == 0x01 else raw
                    if jpeg:
                        try:
                            frame_queue.put((1, jpeg), block=False)
                        except queue.Full:
                            pass
        except Exception:
            pass

    async def _main() -> None:
        async with websockets.serve(_handler, host, port, max_size=2**20):
            await asyncio.Future()

    asyncio.run(_main())


def start_lpr_ws_server_threads(
    host: str,
    port_entry: int,
    port_exit: int,
    frame_queue: "queue.Queue[tuple[int, bytes]]",
) -> Optional[List[threading.Thread]]:
    """입구·출구 각각 별도 WebSocket 서버 스레드 2개 기동."""
    if not _WS_AVAILABLE:
        return None
    t_entry = threading.Thread(
        target=_run_entry_server,
        args=(host, port_entry, frame_queue),
        daemon=True,
    )
    t_exit = threading.Thread(
        target=_run_exit_server,
        args=(host, port_exit, frame_queue),
        daemon=True,
    )
    t_entry.start()
    t_exit.start()
    return [t_entry, t_exit]
