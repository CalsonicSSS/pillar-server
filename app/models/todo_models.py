from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import UUID


class TodoGenerateRequest(BaseModel):
    start_date: datetime
    end_date: datetime


class TodoItem(BaseModel):
    id: str
    description: str
    is_completed: bool
    completed_at: Optional[datetime] = None
    display_order: int
    created_at: datetime
    updated_at: datetime


class TodoListResponse(BaseModel):
    id: UUID
    project_id: UUID
    start_date: datetime
    end_date: datetime
    summary: str  # Summary of messages in the date range
    items: List[TodoItem]
    created_at: datetime
    updated_at: datetime


class TodoListUpdateRequest(BaseModel):
    items: List[Dict[str, Any]]  # Allow flexible updates to todo items


# -----------------------------------------------------------------------------------------------


# Response models
class TodoGenerateResponse(BaseModel):
    status: str
    status_message: str
