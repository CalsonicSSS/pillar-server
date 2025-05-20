from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID


class ContactBase(BaseModel):
    name: Optional[str] = None
    account_identifier: str
    channel_type: str


class ContactCreate(ContactBase):
    channel_id: UUID
    user_id: UUID


class ContactUpdate(BaseModel):
    name: Optional[str] = None


class ContactResponse(ContactBase):
    id: UUID
    channel_id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
