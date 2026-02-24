import asyncio
import logging
from typing import Callable, Optional

from .config import settings


logger = logging.getLogger("udp-video-receiver")


class UdpVideoReceiverProtocol(asyncio.DatagramProtocol):
    def __init__(self, on_packet: Optional[Callable[[bytes], None]] = None) -> None:
        self.on_packet = on_packet

    def datagram_received(self, data: bytes, addr):
        logger.info("UDP video packet from %s:%s size=%d", addr[0], addr[1], len(data))
        if self.on_packet:
            self.on_packet(data)


async def start_udp_receiver(on_packet: Optional[Callable[[bytes], None]] = None) -> None:
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: UdpVideoReceiverProtocol(on_packet),
        local_addr=(settings.udp_listen_host, settings.udp_listen_port),
    )
    logger.info(
        "Client UDP receiver listening on %s:%d",
        settings.udp_listen_host,
        settings.udp_listen_port,
    )
    try:
        await asyncio.Future()
    finally:
        transport.close()

