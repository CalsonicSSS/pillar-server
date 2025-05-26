from typing import List, Dict, Any, Optional
from uuid import UUID
from fastapi import UploadFile
from supabase._async.client import AsyncClient
from app.custom_error import DataBaseError, GeneralServerError, UserAuthError
from app.utils.storage.supabase_storage_helpers import upload_manual_file_to_project
from app.models.document_models import DocumentResponse, DocumentDeletionResponse, DocumentDownloadResponse
import traceback


async def upload_document_to_project(supabase: AsyncClient, project_id: UUID, uploaded_file: UploadFile, user_id: UUID) -> DocumentResponse:
    """
    Upload a document file to a specific project.
    """
    print("upload_document_to_project service function runs")
    try:
        # Read file content
        file_content = await uploaded_file.read()

        # Get file info
        filename = uploaded_file.filename or "unknown_file"
        content_type = uploaded_file.content_type or "application/octet-stream"

        # Upload and create document record
        return await upload_manual_file_to_project(supabase, project_id, file_content, filename, content_type, user_id)

    except (DataBaseError, UserAuthError):
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to upload document")


async def get_project_documents(
    supabase: AsyncClient, project_id: UUID, user_id: UUID, source_filter: Optional[str] = None
) -> List[DocumentResponse]:
    """
    Get all documents for a specific project.
    """
    print("get_project_documents service function runs")
    try:
        # Verify project access
        project_result = await supabase.table("projects").select("id").eq("id", str(project_id)).eq("user_id", str(user_id)).execute()
        if not project_result.data:
            raise UserAuthError(error_detail_message="Project not found or access denied")

        # Build query
        query = supabase.table("documents").select("*").eq("project_id", str(project_id))

        if source_filter:
            query = query.eq("source", source_filter)

        result = await query.order("created_at", options={"ascending": False}).execute()

        return [DocumentResponse(**doc) for doc in result.data]

    except UserAuthError:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to retrieve documents")


async def delete_document(supabase: AsyncClient, document_id: UUID, user_id: UUID) -> DocumentDeletionResponse:
    """
    Delete a document from both database and storage.
    """
    print("delete_document service function runs")
    try:
        # Get document with project verification
        doc_result = await supabase.table("documents").select("*, projects!inner(user_id)").eq("id", str(document_id)).execute()

        if not doc_result.data or doc_result.data[0]["projects"]["user_id"] != str(user_id):
            raise UserAuthError(error_detail_message="Document not found or access denied")

        document = doc_result.data[0]
        file_path = document["file_path"]

        # Delete from storage
        await supabase.storage.from_("project-attachments").remove([file_path])

        # Delete from database
        await supabase.table("documents").delete().eq("id", str(document_id)).execute()

        return DocumentDeletionResponse(status="success", status_message="Document deleted successfully")

    except UserAuthError:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to delete document")


async def download_document(supabase: AsyncClient, document_id: UUID, user_id: UUID) -> Dict[str, Any]:
    """
    Get download URL for a document.
    """
    print("download_document service function runs")
    try:
        # Get document with access verification
        doc_result = await supabase.table("documents").select("*, projects!inner(user_id)").eq("id", str(document_id)).execute()

        if not doc_result.data or doc_result.data[0]["projects"]["user_id"] != str(user_id):
            raise UserAuthError(error_detail_message="Document not found or access denied")

        document = doc_result.data[0]
        file_path = document["file_path"]

        # Generate signed URL (expires in 1 hour)
        signed_url_result = supabase.storage.from_("project-attachments").create_signed_url(file_path, expires_in=3600)

        return DocumentDownloadResponse(
            download_url=signed_url_result["signedURL"],
            filename=document["safe_file_name"],
            file_type=document["file_type"],
            file_size=document["file_size"],
        )

    except UserAuthError:
        raise

    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to generate download URL")
