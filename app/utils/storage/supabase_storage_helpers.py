import traceback
from typing import Dict, Any, Optional
from uuid import UUID
from supabase._async.client import AsyncClient
from app.custom_error import DataBaseError, GeneralServerError
from app.utils.gmail.gmail_attachment_helpers import generate_safe_filename


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
        # Create file path: projects/{project_id}/attachments/{filename}
        file_path = f"projects/{str(project_id)}/attachments/{filename}"

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


async def create_document_record(
    supabase: AsyncClient,
    project_id: UUID,
    file_path: str,
    safe_filename: str,  # UPDATED: Now using safe_filename
    original_filename: str,  # NEW: Keep original for display
    file_type: str,
    file_size: int,
    source: str,  # NEW: Track source of document
) -> Dict[str, Any]:
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
    print(f"create_document_record runs for {original_filename}")

    try:
        document_data = {
            "project_id": str(project_id),
            # "message_id": None,  # REMOVED for MVP simplification
            "folder_id": None,  # No folder assignment for now
            "safe_file_name": safe_filename,  # UPDATED: Using safe filename for consistency
            "original_file_name": original_filename,  # NEW: Keep original for display
            "file_path": file_path,
            "file_type": file_type,
            "file_size": file_size,
            "source": source,  # NEW: Track document source
        }

        result = await supabase.table("documents").insert(document_data).execute()

        if not result.data:
            raise DataBaseError(error_detail_message="Failed to create document record")

        document_record = result.data[0]
        print(f"Created document record with ID: {document_record['id']}")

        return document_record

    except Exception as e:
        print(f"Error creating document record: {str(e)}")
        print(traceback.format_exc())
        raise DataBaseError(error_detail_message=f"Failed to create document record: {str(e)}")


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


# Manual file upload helper
async def upload_manual_file_to_project(
    supabase: AsyncClient, project_id: UUID, file_bytes: bytes, original_filename: str, content_type: str, user_id: UUID  # For access verification
) -> Dict[str, Any]:
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

    # Create corresponding document record
    document_record = await create_document_record(
        supabase, project_id, storage_result["file_path"], safe_filename, original_filename, content_type, len(file_bytes), source="manual"
    )

    return document_record
