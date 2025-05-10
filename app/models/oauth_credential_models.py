from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime
from uuid import UUID


class OAuthCredentialBase(BaseModel):
    user_id: UUID
    channel_type: str
    oauth_data: Dict[str, Any]


class OAuthCredentialCreate(OAuthCredentialBase):
    pass


class OAuthCredentialUpdate(BaseModel):
    oauth_data: Optional[Dict[str, Any]] = None


class OAuthCredentialResponse(OAuthCredentialBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
