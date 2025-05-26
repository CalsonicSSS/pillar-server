from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID


class MessageBase(BaseModel):
    platform_message_id: str
    contact_id: UUID
    sender_account: str  # UPDATED: matches your naming
    recipient_accounts: List[str]  # UPDATED: matches your naming
    cc_accounts: List[str] = []  # NEW: CC support
    subject: Optional[str] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    registered_at: datetime
    thread_id: Optional[str] = None
    is_read: bool = False
    is_from_contact: bool
    attachments: List[Dict[str, Any]] = []  # NEW: Attachment support


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
    contact_id: Optional[List[UUID]] = None
    project_id: Optional[UUID] = None
    thread_id: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_read: Optional[bool] = None
    is_from_contact: Optional[bool] = None
    limit: int = 50
    offset: int = 0
