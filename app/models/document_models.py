from pydantic import BaseModel
from typing import Optional, List, Literal
from datetime import datetime
from uuid import UUID


class DocumentBase(BaseModel):
    safe_file_name: str  # underscore
    original_file_name: Optional[str] = None  # underscore
    file_type: str
    file_size: int
    file_path: str
    folder_id: Optional[UUID] = None
    source: Literal["email", "manual"]


class DocumentUploadRequest(DocumentBase):
    project_id: UUID


class DocumentResponse(DocumentBase):
    id: UUID
    project_id: UUID
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------------------------


class DocumentDeletionResponse(BaseModel):
    status: str
    status_message: str


class DocumentDownloadResponse(BaseModel):
    download_url: str
    file_name: str
    file_type: str
    file_size: int
