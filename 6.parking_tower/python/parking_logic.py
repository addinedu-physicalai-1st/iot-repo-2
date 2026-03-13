from typing import Optional


class ParkingController:
    def __init__(self, plates, arduino, log_callback=None, move_callback=None):
        self.plates = plates
        self.arduino = arduino
        self.last_parked_plate: Optional[int] = None
        self.log_callback = log_callback or (lambda msg: None)
        self.move_callback = move_callback or (lambda _plate_id: None)

    def log(self, msg: str):
        self.log_callback(msg)

    def is_full(self) -> bool:
        return all(p.occupied for p in self.plates)

    def first_empty_plate(self) -> Optional[int]:
        for p in self.plates:
            if not p.occupied:
                return p.plate_id
        return None

    def find_plate_by_car(self, car_number: str) -> Optional[int]:
        for p in self.plates:
            if p.car_number == car_number:
                return p.plate_id
        return None

    def set_full_status(self):
        self.arduino.send(f"FULL={1 if self.is_full() else 0}")

    def move_plate_to_first_floor(self, plate_id: int) -> bool:
        self.log(f"차판 {plate_id} 을(를) 1층 위치로 이동")
        self.move_callback(plate_id)
        lines = self.arduino.send(f"MOVE={plate_id}")
        for line in lines:
            self.log(line)
        return not any(line.startswith("ERR|") for line in lines)

    def park_car(self, car: str):
        if not car:
            return False, "차량번호를 입력하세요."
        if any(p.car_number == car for p in self.plates):
            return False, "이미 입고된 차량번호입니다."
        if self.arduino.last_status.get("emergency"):
            return False, "비상정지 상태에서는 입고할 수 없습니다."
        if self.is_full():
            return False, "현재 만차입니다."

        empty_plate = self.first_empty_plate()
        if empty_plate is None:
            return False, "빈 차판이 없습니다."

        ok = self.move_plate_to_first_floor(empty_plate)
        if not ok:
            return False, "차판 이동 실패"

        self.plates[empty_plate].car_number = car
        self.last_parked_plate = empty_plate
        self.log(f"차량 {car} 입고 완료 -> 차판 {empty_plate}")

        next_empty = self.first_empty_plate()
        if next_empty is not None and not self.is_full():
            self.move_plate_to_first_floor(next_empty)
            self.log(f"다음 빈 차판 {next_empty} 자동 호출 완료")

        self.set_full_status()
        return True, "입고 완료"

    def retrieve_car(self, car: str):
        if not car:
            return False, "출고할 차량번호를 입력하세요."

        target_plate = self.find_plate_by_car(car)
        if target_plate is None:
            return False, "해당 차량이 없습니다."

        ok = self.move_plate_to_first_floor(target_plate)
        if not ok:
            return False, "차판 이동 실패"

        self.plates[target_plate].car_number = ""
        self.log(f"차량 {car} 출고 완료 <- 차판 {target_plate}")

        # 출고 후에는 방금 출고한 차판을 1층 홈 위치에 그대로 유지한다.
        # 빈 차판 자동 호출은 '입고 후 준비' 용도이므로 출고 직후에는 수행하지 않는다.
        self.set_full_status()
        return True, "출고 완료"
