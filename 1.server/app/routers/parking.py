from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db


router = APIRouter(prefix="/parking", tags=["parking"])

# 입/출차 감지 센서 상태(대시보드 버튼 전용). T1/T2 슬롯과 분리해서 관리한다.
ENTRY_EXIT_SENSOR_STATE = {
    "entry_sensor_connected": False,
    "exit_sensor_connected": False,
    "entry_sensor_detected": False,
    "exit_sensor_detected": False,
}


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
        slots=slots,
    )

