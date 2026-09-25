from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from decimal import Decimal

class UserBase(BaseModel):
    username: str
    email: str
    role: str = "user"
    status: bool = True
    # === 新增：运维人员专属字段 ===
    skills: Optional[str] = "初级运维"
    current_lat: Optional[Decimal] = Decimal('31.150000')
    current_lng: Optional[Decimal] = Decimal('121.500000')
    carbon_index: Optional[float] = 0.05
    work_status: Optional[str] = "free"

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None
    status: Optional[bool] = None
    # === 新增：允许更新运维字段 ===
    skills: Optional[str] = None
    current_lat: Optional[Decimal] = None
    current_lng: Optional[Decimal] = None
    carbon_index: Optional[float] = None
    work_status: Optional[str] = None

class UserResponse(UserBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True