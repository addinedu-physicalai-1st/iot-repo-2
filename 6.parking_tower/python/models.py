from dataclasses import dataclass

TOTAL_PLATES = 6

@dataclass
class PlateInfo:
    plate_id: int
    car_number: str = ""

    @property
    def occupied(self) -> bool:
        return bool(self.car_number)
