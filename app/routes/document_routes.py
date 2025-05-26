from fastapi import APIRouter, Depends, Path, Query, UploadFile, File
from typing import List, Optional
from uuid import UUID
from supabase._async.client import AsyncClient
from app.utils.app_states import get_async_supabase_client
from app.utils.user_auth import verify_jwt_and_get_user_id
from app.services.document_services import upload_document_to_project, get_project_documents, delete_document, download_document
from app.models.document_models import DocumentResponse, DocumentDeletionResponse, DocumentDownloadResponse

document_router = APIRouter(prefix="/documents", tags=["documents"])


@document_router.post("/{project_id}", response_model=DocumentResponse)
async def upload_document_handler(
    project_id: UUID = Path(...),
    file: UploadFile = File(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    """Upload a document to a specific project"""
    print("/documents/{project_id} POST route reached")
    return await upload_document_to_project(supabase, project_id, file, user_id)


@document_router.get("/{project_id}", response_model=List[DocumentResponse])
async def get_project_documents_handler(
    project_id: UUID = Path(...),
    source: Optional[str] = Query(None, description="Filter by source: email_attachment or manual_upload"),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    """Get all documents for a specific project"""
    print("/documents/{project_id} GET route reached")
    return await get_project_documents(supabase, project_id, user_id, source)


@document_router.delete("/{document_id}", response_model=DocumentDeletionResponse)
async def delete_document_handler(
    document_id: UUID = Path(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    """Delete a document"""
    print("/documents/{document_id} DELETE route reached")
    return await delete_document(supabase, document_id, user_id)


@document_router.get("/{document_id}/download", response_model=DocumentDownloadResponse)
async def download_document_handler(
    document_id: UUID = Path(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    """Get download URL for a document"""
    print("/documents/{document_id}/download GET route reached")
    return await download_document(supabase, document_id, user_id)
