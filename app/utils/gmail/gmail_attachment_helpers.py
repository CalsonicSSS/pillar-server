import base64
import traceback
from typing import Dict, Any, Optional, List
from app.utils.gmail.gmail_api_service import create_gmail_service
from app.custom_error import UserOauthError
import re
from datetime import datetime
from app.utils.storage.supabase_storage_helpers import (
    upload_file_to_project_storage,
    create_document_record,
    get_project_id_from_contact,
    generate_safe_filename,
)
from uuid import UUID
from supabase._async.client import AsyncClient


# extracts ALL attachments metadata only from a single email (emails can have multiple files)
def extract_gmail_attachments_metadata(fetched_full_gmail_message: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract attachment metadata from Gmail message (without downloading files yet).

    Args:
        fetched_full_gmail_message: Full Gmail message from API

    Returns:
        List of attachment metadata dictionaries
    """
    print("extract_gmail_attachments_metadata runs...")
    attachments = []

    def process_parts_for_attachments(parts):
        """Recursively process message parts to find attachments"""
        if not parts:
            return

        for part in parts:
            # Handle nested multipart messages
            if part.get("mimeType", "").startswith("multipart/"):
                nested_parts = part.get("parts", [])
                process_parts_for_attachments(nested_parts)
                continue

            # Check if this part has an attachment
            body = part.get("body", {})
            if body.get("attachmentId"):  # Gmail API indicates attachment with attachmentId
                filename = part.get("filename", "unknown_file")
                mime_type = part.get("mimeType", "application/octet-stream")
                size = body.get("size", 0)
                attachment_id = body.get("attachmentId")

                # Skip inline images and very small attachments (likely signatures)
                if size > 1024 and not mime_type.startswith("image/"):  # > 1KB and not inline image
                    attachment_info = {
                        "filename": filename,
                        "file_type": mime_type,
                        "file_size": size,
                        "attachment_id": attachment_id,  # Gmail's attachment ID for download
                        "document_id": None,  # Will be set when file is actually stored
                    }
                    attachments.append(attachment_info)
                    print(f"Found attachment: {filename} ({size} bytes)")

    # Process the message payload
    payload = fetched_full_gmail_message.get("payload", {})

    # Handle both single-part and multi-part messages
    if "parts" in payload:
        process_parts_for_attachments(payload["parts"])
    else:
        # Single part message - check if it's an attachment
        body = payload.get("body", {})
        if body.get("attachmentId"):
            filename = payload.get("filename", "unknown_file")
            mime_type = payload.get("mimeType", "application/octet-stream")
            size = body.get("size", 0)
            attachment_id = body.get("attachmentId")

            if size > 1024:  # > 1KB
                attachment_info = {
                    "filename": filename,
                    "file_type": mime_type,
                    "file_size": size,
                    "attachment_id": attachment_id,
                    "document_id": None,
                }
                attachments.append(attachment_info)

    return attachments


# -------------------------------------------------------------------------------------------------------------------------------------


# to retrieve Gmail actual attachment body content based on the specific attachment_id withint that specific email
def retrieve_gmail_attachment_body(oauth_data: Dict[str, Any], message_id: str, attachment_id: str) -> Optional[bytes]:
    """
    Download attachment content from Gmail API.

    Args:
        oauth_data: User's Gmail OAuth credentials
        message_id: Gmail message ID containing the attachment
        attachment_id: Gmail attachment ID

    Returns:
        Raw attachment bytes or None if download fails
    """
    print(f"retrieve_gmail_attachment runs for message {message_id}, attachment {attachment_id}")

    try:
        # Create Gmail service
        gmail_service = create_gmail_service(oauth_data)

        # Download attachment from Gmail
        attachment = gmail_service.users().messages().attachments().get(userId="me", messageId=message_id, id=attachment_id).execute()

        # Gmail returns attachment data as base64url encoded
        attachment_data = attachment.get("data")
        if not attachment_data:
            print(f"No attachment data found for {attachment_id}")
            return None

        # Decode base64url to get raw bytes
        file_bytes = base64.urlsafe_b64decode(attachment_data)

        # len(file_bytes):	File size in bytes (e.g., 1048576 = 1024^2 means 1 MB)
        print(f"Successfully downloaded attachment {attachment_id}, size: {len(file_bytes)} bytes")
        return file_bytes

    except Exception as e:
        print(f"Error downloading Gmail attachment {attachment_id}: {str(e)}")
        print(traceback.format_exc())
        raise UserOauthError(error_detail_message=f"Failed to download attachment: {str(e)}")


# -------------------------------------------------------------------------------------------------------------------------------------


# 1. extract all possible metadata from all possible attachments in that gmail message
# 2. retreive files from Gmail
# 3. upload files to Supabase storage
# 4. create document record in Supabase database
# only used in the transform_and_process_fetched_full_gmail_message_with_attachments function later
async def process_gmail_attachments_with_storage(
    fetched_full_gmail_message: Dict[str, Any], contact_id: str, user_oauth_data: Dict[str, Any], supabase: AsyncClient
) -> List[Dict[str, Any]]:
    """
    Process Gmail attachments: extract metadata, retrieve files attachment, store in Supabase.

    Returns:
        List of attachment metadata with document_ids populated
    """
    print("process_gmail_attachments_with_storage runs...")

    # First, extract attachment(s) metadata for the single full email message
    attachments_metadata = extract_gmail_attachments_metadata(fetched_full_gmail_message)

    if not attachments_metadata:
        return []

    # Get project ID for file organization
    project_id = await get_project_id_from_contact(supabase, UUID(contact_id))  # RENAMED function
    message_id = fetched_full_gmail_message["id"]

    processed_attachments = []

    for attachment_info in attachments_metadata:
        try:
            print(f"Processing attachment: {attachment_info['filename']}")

            # retrieve actual attachment body from this Gmail message for this speific attachment
            file_bytes = retrieve_gmail_attachment_body(user_oauth_data, message_id, attachment_info["attachment_id"])

            if not file_bytes:
                print(f"Failed to download {attachment_info['filename']}, skipping")
                continue

            # Generate safe filename for this specific attachment
            safe_filename = generate_safe_filename(attachment_info["filename"])

            # Upload to Supabase storage
            storage_result = await upload_file_to_project_storage(supabase, project_id, file_bytes, safe_filename, attachment_info["file_type"])

            # Create document record - UPDATED signature
            document_record = await create_document_record(
                supabase,
                project_id,
                storage_result["file_path"],
                safe_filename,  # Safe filename for storage consistency
                attachment_info["filename"],  # Original filename for display
                attachment_info["file_type"],
                len(file_bytes),
                source="email",  # Mark as email attachment
            )

            # Update attachment metadata with document info
            processed_attachment = {
                "filename": attachment_info["filename"],  # Keep original for message display
                "file_type": attachment_info["file_type"],
                "file_size": len(file_bytes),
                "attachment_id": attachment_info["attachment_id"],
                "document_id": document_record["id"],  # Now populated!
            }

            processed_attachments.append(processed_attachment)
            print(f"Successfully processed attachment: {attachment_info['filename']}")

        except Exception as e:
            print(f"Error processing attachment {attachment_info['filename']}: {str(e)}")
            # Continue with other attachments even if one fails
            continue

    return processed_attachments
