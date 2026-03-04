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


@router.put("/by-guid/{device_guid}/ip", response_model=schemas.DeviceRead)
def update_device_ip_by_guid(
    device_guid: str,
    payload: schemas.DeviceIpUpdate,
    db: Session = Depends(get_db),
):
    """
    device_guid 로 devices 레코드를 찾아 ip_address 만 갱신하는 엔드포인트.

    - esp32_board1_1 / esp32_board2 가 DHCP 로 IP 가 바뀌었을 때
      3.device_client 에서 등록 패킷을 받아 이 API 를 호출한다.
    """
    device = db.query(models.Device).filter(models.Device.device_guid == device_guid).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    device.ip_address = payload.ip_address
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

