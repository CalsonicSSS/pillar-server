from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID


class ContactBase(BaseModel):
    name: Optional[str] = None
    account_identifier: str


class ContactCreate(ContactBase):
    channel_id: UUID


class ContactUpdate(BaseModel):
    name: Optional[str] = None


class ContactResponse(ContactBase):
    id: UUID
    channel_id: UUID
    created_at: datetime
    updated_at: datetime
