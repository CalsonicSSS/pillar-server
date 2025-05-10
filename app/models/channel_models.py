from pydantic import BaseModel
from typing import Optional, Literal, Dict, Any
from datetime import datetime
from uuid import UUID


class ChannelBase(BaseModel):
    channel_type: str


class ChannelCreate(ChannelBase):
    project_id: UUID


class ChannelUpdate(BaseModel):
    is_connected: Optional[bool] = None


class ChannelResponse(ChannelBase):
    id: UUID
    project_id: UUID
    is_connected: bool
    auth_data: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
