from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db


router = APIRouter(prefix="/sensors", tags=["sensors"])


@router.get("/", response_model=List[schemas.SensorRead])
def list_sensors(db: Session = Depends(get_db)):
    return db.query(models.Sensor).order_by(models.Sensor.id).all()


@router.post("/", response_model=schemas.SensorRead, status_code=status.HTTP_201_CREATED)
def create_sensor(sensor_in: schemas.SensorCreate, db: Session = Depends(get_db)):
    # GUID 중복 체크
    exists = (
        db.query(models.Sensor)
        .filter(models.Sensor.guid == sensor_in.guid)
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="guid already exists")

    sensor = models.Sensor(**sensor_in.model_dump())
    db.add(sensor)
    db.commit()
    db.refresh(sensor)
    return sensor


@router.put("/{sensor_id}", response_model=schemas.SensorRead)
def update_sensor(
    sensor_id: int,
    sensor_in: schemas.SensorCreate,
    db: Session = Depends(get_db),
):
    sensor = (
        db.query(models.Sensor)
        .filter(models.Sensor.id == sensor_id)
        .first()
    )
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")

    for field, value in sensor_in.model_dump().items():
        setattr(sensor, field, value)

    db.add(sensor)
    db.commit()
    db.refresh(sensor)
    return sensor


@router.delete("/{sensor_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_sensor(sensor_id: int, db: Session = Depends(get_db)):
    sensor = (
        db.query(models.Sensor)
        .filter(models.Sensor.id == sensor_id)
        .first()
    )
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")

    # 실제 삭제 대신 is_active 플래그만 끔
    sensor.is_active = False
    db.add(sensor)
    db.commit()
    return None

