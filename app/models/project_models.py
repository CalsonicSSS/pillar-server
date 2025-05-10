from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime
from uuid import UUID

# None value corresponds to SQL NULL value
# be aware of not nullable fields in SQL table


class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    project_type: Literal["business", "individual"]
    project_context_detail: str


class ProjectCreate(ProjectBase):
    # send a string like "2025-04-25T00:00:00Z" (an ISO 8601 UTC datetime string) into a Pydantic model, it will automatically parse it into a datetime object
    start_date: datetime


# Use "= None" when you want it to be TRULY OPTIONAL with a default "None" value.
# Don't use "= None or other value" if you want it to always be explicitly set a value when instanitate.
class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[Literal["Active", "Archived"]] = None
    project_context_detail: Optional[str] = None
    project_type: Optional[Literal["Business", "Individual"]] = None


class ProjectResponse(ProjectBase):
    id: UUID
    status: Literal["Active", "Archived"]
    start_date: datetime
    created_at: datetime
    updated_at: datetime
    user_id: UUID
    avatar_letter: str
