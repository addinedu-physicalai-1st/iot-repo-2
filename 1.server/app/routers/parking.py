from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import set_env_value, settings
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

