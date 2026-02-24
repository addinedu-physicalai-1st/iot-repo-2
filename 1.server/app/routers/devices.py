from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db


router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("/", response_model=List[schemas.DeviceRead])
def list_devices(db: Session = Depends(get_db)):
    return db.query(models.Device).all()


@router.post("/", response_model=schemas.DeviceRead, status_code=status.HTTP_201_CREATED)
def create_device(device_in: schemas.DeviceCreate, db: Session = Depends(get_db)):
    device = models.Device(**device_in.model_dump())
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@router.get("/{device_id}", response_model=schemas.DeviceRead)
def get_device(device_id: int, db: Session = Depends(get_db)):
    device = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.put("/{device_id}", response_model=schemas.DeviceRead)
def update_device(device_id: int, device_in: schemas.DeviceCreate, db: Session = Depends(get_db)):
    device = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    for field, value in device_in.model_dump().items():
        setattr(device, field, value)

    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(device_id: int, db: Session = Depends(get_db)):
    device = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    db.delete(device)
    db.commit()
    return None

