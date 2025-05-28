from typing import Dict, List, Any
from uuid import UUID
import traceback
from supabase._async.client import AsyncClient
from app.custom_error import DataBaseError, GeneralServerError, UserAuthError
from datetime import datetime, timezone
from app.models.message_models import MessageResponse, MessageFilter, MessageUpdate


async def get_messages_with_filters(supabase: AsyncClient, user_id: UUID, filter_params: MessageFilter) -> List[MessageResponse]:
    """
    Get messages with filtering options using the RPC function.
    """
    print("get_messages_with_filters function runs")
    try:
        # Call the RPC function with user_id and filter parameters
        message_query_result = await supabase.rpc(
            "get_messages_with_filters",
            {
                "user_id_param": str(user_id),
                "project_id_param": str(filter_params.project_id) if filter_params.project_id else None,
                "channel_id_param": str(filter_params.channel_id) if filter_params.channel_id else None,
                "contact_id_param": str(filter_params.contact_id) if filter_params.contact_id else None,
                "thread_id_param": filter_params.thread_id,
                "start_date_param": filter_params.start_date,
                "end_date_param": filter_params.end_date,
                "is_read_param": filter_params.is_read,
                "is_from_contact_param": filter_params.is_from_contact,
                "limit_param": filter_params.limit,
                "offset_param": filter_params.offset,
            },
        ).execute()

        return message_query_result.data

    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to retrieve messages")


async def get_message_by_id(supabase: AsyncClient, message_id: UUID, user_id: UUID) -> MessageResponse:
    """
    Get a specific message by ID with user verification.
    """
    print("get_message_by_id function runs")
    try:
        # Verify message belongs to user's project through channel
        message_verification_result = await supabase.rpc(
            "get_message_with_user_verification", {"message_id_param": str(message_id), "user_id_param": str(user_id)}
        ).execute()

        if not message_verification_result.data:
            raise UserAuthError(error_detail_message="Message not found or access denied")

        return message_verification_result.data[0]

    except UserAuthError:
        raise

    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to retrieve that message")


async def mark_message_as_read(supabase: AsyncClient, message_id: UUID, user_id: UUID, message_update_payload: MessageUpdate) -> MessageResponse:
    """
    Mark a message as read with user verification.
    """
    print("mark_message_as_read service function runs")
    try:
        # Verify message belongs to user's project
        await get_message_by_id(supabase, message_id, user_id)

        message_update_data = message_update_payload.model_dump()
        message_update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Update message read status
        result = await supabase.table("messages").update(message_update_data).eq("id", str(message_id)).execute()

        if not result.data:
            raise DataBaseError(error_detail_message="Failed to mark message as read")

        return result.data[0]

    except (DataBaseError, UserAuthError):
        raise

    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to mark message as read")
