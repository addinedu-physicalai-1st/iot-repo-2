from pathlib import Path
from typing import List
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import BASE_DIR, set_env_value, settings
from ..db import get_db


router = APIRouter(prefix="/parking", tags=["parking"])

# 입/출차 감지 센서 상태(대시보드 버튼 전용). T1/T2 슬롯과 분리해서 관리한다.
ENTRY_EXIT_SENSOR_STATE = {
    "entry_sensor_connected": False,
    "exit_sensor_connected": False,
    "entry_sensor_detected": False,
    "exit_sensor_detected": False,
}
OPERATION_MODE_ON = settings.operation_mode_on
# 0: 연결안됨, 1: 닫힘, 2: 열림, 3: 자동
GATE_SENSOR_STATE = settings.gate_sensor_state
# 0: 동작하지 않음, 1: 열림, 2: 닫힘
GATE_AUTO_STATE = settings.gate_auto_state


_LOG_DIR = BASE_DIR / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_PARKING_EVENT_LOG = _LOG_DIR / "parking_events.log"


def _append_event_log(kind: str, message: str) -> None:
    """
    입·출차 이벤트를 파일로 남겨서, 콘솔 로그가 너무 길어져도
    parking_events.log 하나만 보면 흐름을 확인할 수 있게 한다.
    """
    try:
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{ts} [{kind}] {message}\n"
        with _PARKING_EVENT_LOG.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        # 파일 쓰기 에러가 전체 API 동작을 막지 않도록 무시
        pass


@router.get("/slots", response_model=List[schemas.ParkingSlotRead])
def list_slots(db: Session = Depends(get_db)):
    return db.query(models.ParkingSlot).all()


@router.post("/slots", response_model=schemas.ParkingSlotRead)
def create_slot(slot_in: schemas.ParkingSlotCreate, db: Session = Depends(get_db)):
    slot = models.ParkingSlot(**slot_in.model_dump())
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


@router.post("/slots/{slot_id}/occupy")
def occupy_slot(slot_id: int, plate: str | None = None, db: Session = Depends(get_db)):
    slot = db.query(models.ParkingSlot).filter(models.ParkingSlot.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    slot.is_occupied = True
    slot.sensor_connected = True
    slot.last_vehicle_plate = plate
    db.add(slot)
    db.commit()
    return {"ok": True}


@router.post("/slots/{slot_id}/release")
def release_slot(slot_id: int, db: Session = Depends(get_db)):
    slot = db.query(models.ParkingSlot).filter(models.ParkingSlot.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    slot.is_occupied = False
    slot.sensor_connected = True
    db.add(slot)
    db.commit()
    return {"ok": True}


@router.post("/slots/{slot_id}/sensor-connected")
def set_slot_sensor_connected(
    slot_id: int,
    connected: bool,
    db: Session = Depends(get_db),
):
    slot = db.query(models.ParkingSlot).filter(models.ParkingSlot.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    slot.sensor_connected = connected
    db.add(slot)
    db.commit()
    return {"ok": True}


@router.post("/entry-exit-sensors")
def set_entry_exit_sensor_state(
    entry_sensor_connected: bool | None = None,
    exit_sensor_connected: bool | None = None,
    entry_sensor_detected: bool | None = None,
    exit_sensor_detected: bool | None = None,
):
    if entry_sensor_connected is not None:
        ENTRY_EXIT_SENSOR_STATE["entry_sensor_connected"] = entry_sensor_connected
    if exit_sensor_connected is not None:
        ENTRY_EXIT_SENSOR_STATE["exit_sensor_connected"] = exit_sensor_connected
    if entry_sensor_detected is not None:
        ENTRY_EXIT_SENSOR_STATE["entry_sensor_detected"] = entry_sensor_detected
    if exit_sensor_detected is not None:
        ENTRY_EXIT_SENSOR_STATE["exit_sensor_detected"] = exit_sensor_detected
    return {"ok": True, **ENTRY_EXIT_SENSOR_STATE}


@router.get("/operation-mode")
def get_operation_mode():
    return {"operation_mode_on": OPERATION_MODE_ON}


@router.post("/operation-mode")
def set_operation_mode(operation_mode_on: bool):
    global OPERATION_MODE_ON
    OPERATION_MODE_ON = operation_mode_on
    set_env_value("OPERATION_MODE_ON", "true" if OPERATION_MODE_ON else "false")
    return {"ok": True, "operation_mode_on": OPERATION_MODE_ON}


@router.get("/gate-state")
def get_gate_state():
    return {
        "gate_sensor_state": GATE_SENSOR_STATE,
        "gate_auto_state": GATE_AUTO_STATE,
    }


@router.post("/gate-state")
def set_gate_state(
    gate_sensor_state: int | None = None,
    gate_auto_state: int | None = None,
):
    global GATE_SENSOR_STATE, GATE_AUTO_STATE

    if gate_sensor_state is not None:
        GATE_SENSOR_STATE = int(gate_sensor_state)
        set_env_value("GATE_SENSOR_STATE", str(GATE_SENSOR_STATE))
    if gate_auto_state is not None:
        GATE_AUTO_STATE = int(gate_auto_state)
        set_env_value("GATE_AUTO_STATE", str(GATE_AUTO_STATE))

    return {
        "ok": True,
        "gate_sensor_state": GATE_SENSOR_STATE,
        "gate_auto_state": GATE_AUTO_STATE,
    }


@router.get("/dashboard", response_model=schemas.DashboardSummary)
def dashboard_summary(db: Session = Depends(get_db)):
    total_slots = db.query(func.count(models.ParkingSlot.id)).scalar() or 0
    occupied_slots = (
        db.query(func.count(models.ParkingSlot.id))
        .filter(models.ParkingSlot.is_occupied.is_(True))
        .scalar()
        or 0
    )
    active_devices = (
        db.query(func.count(models.Device.id))
        .filter(models.Device.is_active.is_(True))
        .scalar()
        or 0
    )
    recent_events = (
        db.query(models.EventLog)
        .order_by(models.EventLog.created_at.desc())
        .limit(20)
        .all()
    )
    slots = db.query(models.ParkingSlot).all()

    return schemas.DashboardSummary(
        total_slots=total_slots,
        occupied_slots=occupied_slots,
        free_slots=total_slots - occupied_slots,
        active_devices=active_devices,
        recent_events=recent_events,
        entry_sensor_connected=ENTRY_EXIT_SENSOR_STATE["entry_sensor_connected"],
        exit_sensor_connected=ENTRY_EXIT_SENSOR_STATE["exit_sensor_connected"],
        entry_sensor_detected=ENTRY_EXIT_SENSOR_STATE["entry_sensor_detected"],
        exit_sensor_detected=ENTRY_EXIT_SENSOR_STATE["exit_sensor_detected"],
        operation_mode_on=OPERATION_MODE_ON,
        gate_sensor_state=GATE_SENSOR_STATE,
        gate_auto_state=GATE_AUTO_STATE,
        slots=slots,
    )


# ----- parking_records (입·출차 기록 + 번호판 이미지 경로) -----
@router.get("/records", response_model=List[schemas.ParkingRecordRead])
def list_parking_records(
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """입·출차 기록 목록 (entry_img_path, exit_img_path 포함). 2.client에서 조회용."""
    return (
        db.query(models.ParkingRecord)
        .order_by(models.ParkingRecord.entry_timestamp.desc())
        .limit(limit)
        .all()
    )


@router.get("/records/{record_id}", response_model=schemas.ParkingRecordRead)
def get_parking_record(record_id: int, db: Session = Depends(get_db)):
    """단일 입·출차 기록 조회."""
    rec = db.query(models.ParkingRecord).filter(models.ParkingRecord.record_id == record_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Record not found")
    return rec


@router.patch("/records/{record_id}", response_model=schemas.ParkingRecordRead)
def update_parking_record(
    record_id: int,
    rec_in: schemas.ParkingRecordUpdate,
    db: Session = Depends(get_db),
):
    """입·출차 기록 일부 수정 (번호판, 등록 여부, 요금, resident_id 등)."""
    rec = (
        db.query(models.ParkingRecord)
        .filter(models.ParkingRecord.record_id == record_id)
        .first()
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Record not found")
    data = rec_in.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(rec, field, value)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _safe_record_image_path(subdir: str, filename: str | None) -> Path | None:
    """lpr_record/{subdir}/{filename} 절대 경로. filename에 경로 조작 방지."""
    if not filename or "/" in filename or "\\" in filename:
        return None
    base = (settings.lpr_record_dir / subdir).resolve()
    path = (base / filename).resolve()
    if not path.is_file():
        return None
    try:
        path.relative_to(base)
    except ValueError:
        return None
    return path


@router.get("/records/{record_id}/entry-image")
def get_record_entry_image(record_id: int, db: Session = Depends(get_db)):
    """입차 번호판 이미지 파일 반환 (entry_img_path 기준)."""
    rec = db.query(models.ParkingRecord).filter(models.ParkingRecord.record_id == record_id).first()
    if not rec or not rec.entry_img_path:
        raise HTTPException(status_code=404, detail="Entry image not found")
    path = _safe_record_image_path("entry", rec.entry_img_path)
    if not path:
        raise HTTPException(status_code=404, detail="Entry image file not found")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/records/{record_id}/exit-image")
def get_record_exit_image(record_id: int, db: Session = Depends(get_db)):
    """출차 번호판 이미지 파일 반환 (exit_img_path 기준)."""
    rec = db.query(models.ParkingRecord).filter(models.ParkingRecord.record_id == record_id).first()
    if not rec or not rec.exit_img_path:
        raise HTTPException(status_code=404, detail="Exit image not found")
    path = _safe_record_image_path("exit", rec.exit_img_path)
    if not path:
        raise HTTPException(status_code=404, detail="Exit image file not found")
    return FileResponse(path, media_type="image/jpeg")


# ----- 입·출차 이벤트 API (LPR/센서 → 서버 → DB 반영) -----
@router.post("/entry-event", response_model=schemas.ParkingRecordRead)
def parking_entry_event(
    payload: schemas.ParkingEntryEvent,
    db: Session = Depends(get_db),
):
    """
    입구 트리거 + LPR 결과로 서버에 입차 이벤트를 기록한다.

    - license_plate 로 residents 를 조회하여 등록 차량 여부를 판단
    - parking_records 에 새 레코드를 생성 (exit_timestamp 는 NULL)
    """
    plate = payload.license_plate.strip()
    if not plate:
        _append_event_log("ENTRY_ERROR", "license_plate is empty")
        raise HTTPException(status_code=400, detail="license_plate is required")

    resident = (
        db.query(models.Resident)
        .filter(models.Resident.car_plate == plate)
        .first()
    )
    is_registered = 1 if resident else 0
    resident_id = resident.id if resident else None

    # 이미 활성화된 입차 레코드가 있으면 중복 생성 방지
    # - resident_id 가 있으면 resident_id 기준으로 우선 검색
    # - 없으면 license_plate 기준
    # - 최근 2분 이내 레코드만 대상으로 한다.
    active_q = db.query(models.ParkingRecord).filter(
        models.ParkingRecord.exit_timestamp.is_(None),
    )
    recent_since = datetime.utcnow() - timedelta(minutes=2)
    active_q = active_q.filter(models.ParkingRecord.entry_timestamp >= recent_since)

    rec: models.ParkingRecord | None = None
    if resident_id is not None:
        rec = (
            active_q.filter(models.ParkingRecord.resident_id == resident_id)
            .order_by(models.ParkingRecord.entry_timestamp.desc())
            .first()
        )
    if rec is None:
        rec = (
            active_q.filter(models.ParkingRecord.license_plate == plate)
            .order_by(models.ParkingRecord.entry_timestamp.desc())
            .first()
        )

    if rec is not None:
        # 이미 최근에 활성 입차 레코드가 있으면 그대로 재사용하고, 필요 시 이미지 경로만 업데이트
        if payload.entry_img_path and not rec.entry_img_path:
            rec.entry_img_path = payload.entry_img_path
            db.add(rec)
            db.commit()
            db.refresh(rec)
        _append_event_log(
            "ENTRY_DUP",
            f"record_id={rec.record_id} plate={plate} "
            f"is_registered={rec.is_registered} resident_id={rec.resident_id}",
        )
        return rec

    now = datetime.utcnow()
    rec = models.ParkingRecord(
        license_plate=plate,
        entry_timestamp=now,
        exit_timestamp=None,
        is_registered=is_registered,
        charge_amount=0,
        resident_id=resident_id,
        entry_img_path=payload.entry_img_path,
        exit_img_path=None,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    _append_event_log(
        "ENTRY",
        f"record_id={rec.record_id} plate={plate} "
        f"is_registered={is_registered} resident_id={resident_id}",
    )
    return rec


@router.post("/exit-event", response_model=schemas.ParkingRecordRead)
def parking_exit_event(
    payload: schemas.ParkingExitEvent,
    db: Session = Depends(get_db),
):
    """
    출구 트리거 + LPR/RFID 결과로 서버에 출차 이벤트를 기록한다.

    - 가능한 경우 활성 parking_records (exit_timestamp IS NULL)를 찾는다.
      우선순위: resident_id → license_plate
    - 등록 차량이면 요금 0, 비등록 차량이면 경과 시간 기반 요금 계산(분당 100원 예시)
    - RFID 카드가 찍힌 경우, 비등록 차량이더라도 resident_id 를 연결하여 등록 출차로 처리 가능
    """
    plate = payload.license_plate.strip()
    if not plate:
        _append_event_log("EXIT_ERROR", "license_plate is empty")
        raise HTTPException(status_code=400, detail="license_plate is required")

    # RFID 카드로 resident 식별 (있으면 우선 사용)
    resident = None
    if payload.rfid_card_uid:
        card = (
            db.query(models.RfidCard)
            .filter(
                models.RfidCard.card_uid == payload.rfid_card_uid,
                models.RfidCard.is_active.is_(True),
            )
            .first()
        )
        if card and card.resident_id:
            resident = (
                db.query(models.Resident)
                .filter(models.Resident.id == card.resident_id)
                .first()
            )

    if resident is None:
        resident = (
            db.query(models.Resident)
            .filter(models.Resident.car_plate == plate)
            .first()
        )

    active_q = db.query(models.ParkingRecord).filter(
        models.ParkingRecord.exit_timestamp.is_(None),
    )
    rec = None
    if resident is not None:
        rec = (
            active_q.filter(models.ParkingRecord.resident_id == resident.id)
            .order_by(models.ParkingRecord.entry_timestamp.desc())
            .first()
        )
    if rec is None:
        rec = (
            active_q.filter(models.ParkingRecord.license_plate == plate)
            .order_by(models.ParkingRecord.entry_timestamp.desc())
            .first()
        )

    if rec is None:
        _append_event_log(
            "EXIT_ERROR",
            f"active record not found for plate={plate} rfid={payload.rfid_card_uid}",
        )
        raise HTTPException(status_code=404, detail="Active parking record not found")

    now = datetime.utcnow()
    rec.exit_timestamp = now
    rec.exit_img_path = payload.exit_img_path or rec.exit_img_path

    # resident_id 연결/등록 전환 로직
    if resident is not None:
        rec.resident_id = resident.id
        # 비등록 차량이었지만 resident 가 확인되면 등록 차량으로 전환
        rec.is_registered = 1

    # 요금 계산: 비등록 차량만, 입차~출차 경과 시간(분) * 100원
    if rec.is_registered:
        # 등록 차량은 요금 0 (추후 정책 바뀌면 여기 수정)
        rec.charge_amount = rec.charge_amount or 0
    else:
        if rec.entry_timestamp is None:
            elapsed_minutes = 0
        else:
            delta = now - rec.entry_timestamp
            elapsed_minutes = int(delta.total_seconds() // 60)
            if delta.total_seconds() % 60 > 0:
                elapsed_minutes += 1
        unit_fee = 100
        rec.charge_amount = max(rec.charge_amount, elapsed_minutes * unit_fee)

    db.add(rec)
    db.commit()
    db.refresh(rec)
    _append_event_log(
        "EXIT",
        f"record_id={rec.record_id} plate={plate} "
        f"is_registered={rec.is_registered} resident_id={rec.resident_id} "
        f"charge={rec.charge_amount}",
    )
    return rec

