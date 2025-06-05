from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime
from uuid import UUID


class GmailOAuthFlowResponse(BaseModel):
    oauth_url: str
    status_message: str
    requires_oauth: bool


class GmailOAuthCallbackCompletionResponse(BaseModel):
    status: str
    status_message: str


# ----------------------------------------------------------------------------


class GmailContactsInitialMessagesFetchRequest(BaseModel):
    project_id: UUID
    channel_id: UUID
    contact_ids: list[UUID]


class GmailContactsInitialMessagesFetchResponse(BaseModel):
    status: str
    status_message: str
