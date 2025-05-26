import traceback
from typing import Dict, Any, Optional
from uuid import UUID
from supabase._async.client import AsyncClient
from app.custom_error import DataBaseError, GeneralServerError
from app.models.document_models import DocumentUploadRequest, DocumentResponse
import re
from datetime import datetime


# Email attachments can have problematic names
# Timestamp suffix: Perfect for versioning! Same client might send "invoice.pdf" multiple times over months
def generate_safe_filename(original_filename: str, timestamp_suffix: bool = True) -> str:
    """
    Generate a safe filename for storage, avoiding conflicts and special characters.

    Args:
        original_filename: Original filename from email
        timestamp_suffix: Whether to add timestamp to avoid conflicts

    Returns:
        Safe filename for storage
    """

    # Remove or replace unsafe characters
    safe_filename = re.sub(r'[<>:"/\\|?*]', "_", original_filename)

    # Limit length
    if len(safe_filename) > 150:
        name, ext = safe_filename.rsplit(".", 1) if "." in safe_filename else (safe_filename, "")
        safe_filename = name[:140] + ("." + ext if ext else "")

    # Add timestamp suffix to avoid naming conflicts
    if timestamp_suffix:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name, ext = safe_filename.rsplit(".", 1) if "." in safe_filename else (safe_filename, "")
        safe_filename = f"{name}_{timestamp}" + ("." + ext if ext else "")

    return safe_filename


# --------------------------------------------------------------------------------------------------------------------------------


async def upload_file_to_project_storage(
    supabase: AsyncClient, project_id: UUID, file_bytes: bytes, filename: str, content_type: str = "application/octet-stream"
) -> Dict[str, Any]:
    """
    Upload file to Supabase storage organized by project.

    Args:
        supabase: Supabase client
        project_id: Project UUID for organization
        file_bytes: Raw file content
        filename: Safe filename for storage
        content_type: MIME type of the file

    Returns:
        Dictionary with file path and storage info
    """
    print(f"upload_file_to_project_storage runs for project {project_id}, file {filename}")

    try:
        # Create file path: projects/{project_id}/{filename}
        file_path = f"projects/{str(project_id)}/{filename}"

        # Upload to Supabase storage
        result = await supabase.storage.from_("project-attachments").upload(
            path=file_path, file=file_bytes, file_options={"content-type": content_type, "cache-control": "3600"}  # Cache for 1 hour
        )

        if not result:
            raise DataBaseError(error_detail_message="Failed to upload file to storage")

        print(f"Successfully uploaded file to {file_path}")

        return {"file_path": file_path, "bucket": "project-attachments", "size": len(file_bytes), "content_type": content_type}

    except Exception as e:
        print(f"Error uploading file to storage: {str(e)}")
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message=f"Failed to store attachment: {str(e)}")


# --------------------------------------------------------------------------------------------------------------------------------


async def create_document_record(
    supabase: AsyncClient,
    new_document_payload: DocumentUploadRequest,
) -> DocumentResponse:
    """
    Create a document record in the database linking to the stored file.
    SIMPLIFIED for MVP: No message_id field, project-level only.

    Args:
        supabase: Supabase client
        project_id: Project UUID
        file_path: Path in Supabase storage
        safe_filename: Safe filename used in storage
        original_filename: Original filename from email (for display)
        file_type: MIME type
        file_size: File size in bytes
        source: Source of document ("email" or "manual")

    Returns:
        Created document record
    """
    print(f"create_document_record runs")

    try:
        document_data = new_document_payload.model_dump()
        result = await supabase.table("documents").insert(document_data).execute()

        if not result.data:
            raise DataBaseError(error_detail_message="Failed to create document record")

        return DocumentResponse(**result.data[0])

    except Exception as e:
        print(f"Error creating document record: {str(e)}")
        print(traceback.format_exc())
        raise DataBaseError(error_detail_message=f"Failed to create document record: {str(e)}")


# --------------------------------------------------------------------------------------------------------------------------------


# Manual file upload helper
async def upload_manual_file_to_project(
    supabase: AsyncClient, project_id: UUID, file_bytes: bytes, original_filename: str, content_type: str, user_id: UUID  # For access verification
) -> DocumentResponse:
    """
    Upload a manually selected file to a project.

    Args:
        supabase: Supabase client
        project_id: Project UUID
        file_bytes: File content
        original_filename: Original filename from user
        content_type: MIME type
        user_id: User ID for access verification

    Returns:
        Created document record
    """

    # Verify user owns this project
    project_check = await supabase.table("projects").select("id").eq("id", str(project_id)).eq("user_id", str(user_id)).execute()
    if not project_check.data:
        raise DataBaseError(error_detail_message="Project not found or access denied")

    # Generate safe filename
    safe_filename = generate_safe_filename(original_filename)

    # Upload to storage
    storage_result = await upload_file_to_project_storage(supabase, project_id, file_bytes, safe_filename, content_type)

    new_document_payload = DocumentUploadRequest(
        project_id=project_id,
        safe_file_name=safe_filename,
        original_file_name=original_filename,
        file_type=content_type,
        file_size=len(file_bytes),
        file_path=storage_result["file_path"],
        source="manual",
        folder_id=None,  # No folder support in MVP
    )

    # Create corresponding document record
    return await create_document_record(supabase, new_document_payload)


# --------------------------------------------------------------------------------------------------------------------------------


async def get_project_id_from_contact(supabase: AsyncClient, contact_id: UUID) -> UUID:
    """
    Helper to get project_id from contact_id for file organization.
    RENAMED for clarity.

    Args:
        supabase: Supabase client
        contact_id: Contact UUID

    Returns:
        Project UUID
    """
    try:
        result = await supabase.table("contacts").select("channel_id, channels(project_id)").eq("id", str(contact_id)).execute()

        if not result.data:
            raise DataBaseError(error_detail_message="Contact not found")

        project_id = result.data[0]["channels"]["project_id"]
        return UUID(project_id)

    except Exception as e:
        print(f"Error getting project ID: {str(e)}")
        raise DataBaseError(error_detail_message="Failed to get project information")
