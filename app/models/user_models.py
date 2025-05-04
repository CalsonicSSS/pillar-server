from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from uuid import UUID


class UserBase(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class UserCreate(UserBase):
    clerk_id: str


class UserResponse(UserBase):
    id: UUID
    clerk_id: str
    created_at: datetime
    updated_at: datetime
