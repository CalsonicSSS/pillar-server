from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class MessageBase(BaseModel):
    platform_message_id: str
    channel_id: UUID
    contact_id: UUID  # Direct reference to the contact
    sender_email: str
    recipient_emails: List[str]
    subject: Optional[str] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    registered_at: datetime  # Using internalDate from Gmail
    thread_id: Optional[str] = None
    is_read: bool = False
    is_from_contact: bool  # True if sent by contact, False if sent by user


class MessageCreate(MessageBase):
    pass


class MessageUpdate(BaseModel):
    is_read: Optional[bool] = None


class MessageResponse(MessageBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class MessageFilter(BaseModel):
    channel_id: Optional[UUID] = None
    contact_id: Optional[List[UUID]] = None  # Changed to use contact_id instead of emails
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_read: Optional[bool] = None
    is_from_contact: Optional[bool] = None
    limit: int = 50
    offset: int = 0
