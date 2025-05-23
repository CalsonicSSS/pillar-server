from pydantic import BaseModel
from typing import Optional, List, Literal
from datetime import datetime
from uuid import UUID


class DocumentBase(BaseModel):
    safe_file_name: str
    original_file_name: Optional[str] = None
    file_type: str
    file_size: int
    source: Literal["email", "manual"]


class DocumentUploadRequest(BaseModel):
    project_id: UUID
    # Note: File content will be handled separately via FastAPI's UploadFile


class DocumentResponse(DocumentBase):
    id: UUID
    project_id: UUID
    folder_id: Optional[UUID] = None
    file_path: str
    created_at: datetime
    updated_at: datetime
