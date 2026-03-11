from __future__ import annotations

from info_manager import InfoManager


class ArchitectManager:
    """
    입차 / 출차 / 요금 계산 / 정보 표시 등
    주차장 비즈니스 로직을 담당할 매니저의 뼈대.

    현재는 InfoManager 에서 제공하는 데이터에만 의존하며,
    세부 로직은 이후 단계에서 채운다.
    """

    def __init__(self, info_manager: InfoManager) -> None:
        self._info = info_manager

    # 예시 메서드: 현재 활성 장비 수, 슬롯 상태 등을 조합해
    # 대시보드에 보여줄 요약 정보를 만들어내는 역할로 확장 가능.
    def get_active_device_count(self) -> int:
        return sum(1 for d in self._info.devices if d.get("is_connected"))

