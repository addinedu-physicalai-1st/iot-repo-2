from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


class DeviceBase(BaseModel):
    name: str
    type: str
    ip_address: Optional[str] = None
    config: Optional[str] = None
    is_active: bool = True


class DeviceCreate(DeviceBase):
    pass


class DeviceRead(DeviceBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ParkingSlotBase(BaseModel):
    name: str
    level: Optional[str] = None


class ParkingSlotCreate(ParkingSlotBase):
    pass


class ParkingSlotRead(ParkingSlotBase):
    id: int
    is_occupied: bool
    last_vehicle_plate: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EventLogRead(BaseModel):
    id: int
    device_id: Optional[int] = None
    event_type: str
    message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class DashboardSummary(BaseModel):
    total_slots: int
    occupied_slots: int
    free_slots: int
    active_devices: int
    recent_events: List[EventLogRead]

