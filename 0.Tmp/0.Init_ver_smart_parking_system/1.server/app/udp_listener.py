import asyncio
import logging

from .config import settings


logger = logging.getLogger("udp-listener")


class UdpVideoProtocol(asyncio.DatagramProtocol):
    def datagram_received(self, data: bytes, addr):
        # 여기서는 단순히 패킷 크기와 보낸 주소만 로그로 남김
        logger.info("UDP packet from %s:%s, size=%d", addr[0], addr[1], len(data))
        # TODO: 향후 영상 프레임 재조립 및 디코딩 로직 추가


async def run_udp_server() -> None:
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: UdpVideoProtocol(),
        local_addr=(settings.udp_host, settings.udp_port),
    )
    logger.info("UDP server listening on %s:%d", settings.udp_host, settings.udp_port)
    try:
        await asyncio.Future()  # run forever
    finally:
        transport.close()

