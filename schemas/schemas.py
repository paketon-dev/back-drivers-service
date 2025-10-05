from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from models import RoutePointStatusEnum, StatusEnum


class UserCreate(BaseModel):
    username: str
    first_name: str
    last_name: str
    middle_name: str
    rate: float
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    first_name: str
    last_name: str
    middle_name: str
    rate: float
    
    class Config:
        orm_mode = True


class VehicleCreate(BaseModel):
    plate_number: str
    model: str


class VehicleOut(BaseModel):
    id: int
    plate_number: str
    model: str
    class Config:
        orm_mode = True


class LogCreate(BaseModel):
    status: StatusEnum
    latitude: Optional[float]
    longitude: Optional[float]


class LogOut(BaseModel):
    id: int
    status: StatusEnum
    latitude: Optional[float]
    longitude: Optional[float]
    timestamp: datetime
    class Config:
        orm_mode = True



class PointStatusUpdate(BaseModel):
    new_status: RoutePointStatusEnum
    lat: Optional[float] = None
    lng: Optional[float] = None
    timestamp: Optional[datetime] = None