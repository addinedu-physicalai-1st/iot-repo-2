from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship

from .db import Base


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    type = Column(String(50), nullable=False)  # esp32, gate_controller, tower, guide_panel 등
    ip_address = Column(String(45), nullable=True)
    config = Column(String(255), nullable=True)  # JSON 문자열로 간단 설정 저장
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    events = relationship("EventLog", back_populates="device")


class ParkingSlot(Base):
    __tablename__ = "parking_slots"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)  # 예: A-01
    level = Column(String(20), nullable=True)
    is_occupied = Column(Boolean, default=False)
    last_vehicle_plate = Column(String(20), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class EventLog(Base):
    __tablename__ = "event_logs"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)
    event_type = Column(String(50), nullable=False)  # ENTER, EXIT, ERROR, STATUS 등
    message = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    device = relationship("Device", back_populates="events")

