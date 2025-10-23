from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr = Field(..., description="Unique email address")


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, description="Raw password that will be hashed")


class UserInDBBase(UserBase):
    id: int

    class Config:
        from_attributes = True


class UserOut(UserInDBBase):
    created_at: datetime
    updated_at: datetime
