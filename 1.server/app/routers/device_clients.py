from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db


router = APIRouter(prefix="/device-clients", tags=["device_clients"])


@router.get("/", response_model=List[schemas.DeviceClientRead])
def list_device_clients(db: Session = Depends(get_db)):
    return db.query(models.DeviceClient).order_by(models.DeviceClient.id).all()


@router.post(
    "/",
    response_model=schemas.DeviceClientRead,
    status_code=status.HTTP_201_CREATED,
)
def create_device_client(
    dc_in: schemas.DeviceClientCreate,
    db: Session = Depends(get_db),
):
    exists = (
        db.query(models.DeviceClient)
        .filter(models.DeviceClient.device_no == dc_in.device_no)
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="device_no already exists")

    dc = models.DeviceClient(**dc_in.model_dump())
    db.add(dc)
    db.commit()
    db.refresh(dc)
    return dc


@router.put("/{dc_id}", response_model=schemas.DeviceClientRead)
def update_device_client(
    dc_id: int,
    dc_in: schemas.DeviceClientCreate,
    db: Session = Depends(get_db),
):
    dc = (
        db.query(models.DeviceClient)
        .filter(models.DeviceClient.id == dc_id)
        .first()
    )
    if not dc:
        raise HTTPException(status_code=404, detail="Device client not found")

    for field, value in dc_in.model_dump().items():
        setattr(dc, field, value)

    db.add(dc)
    db.commit()
    db.refresh(dc)
    return dc


@router.delete("/{dc_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_device_client(dc_id: int, db: Session = Depends(get_db)):
    dc = (
        db.query(models.DeviceClient)
        .filter(models.DeviceClient.id == dc_id)
        .first()
    )
    if not dc:
        raise HTTPException(status_code=404, detail="Device client not found")

    dc.is_active = False
    db.add(dc)
    db.commit()
    return None

