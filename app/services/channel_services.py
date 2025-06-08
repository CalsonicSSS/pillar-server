from app.models.channel_models import ChannelCreate, ChannelUpdate, ChannelResponse, ChannelDeletionResponse
from typing import List
from uuid import UUID
from supabase._async.client import AsyncClient
from app.custom_error import DataBaseError, GeneralServerError, UserAuthError
import traceback
from datetime import datetime, timezone


async def create_channel(supabase: AsyncClient, new_channel_payload: ChannelCreate, user_id: UUID) -> ChannelResponse:
    print("create_channel service function runs")
    try:
        # First, verify the project belongs to the user
        project_result = (
            await supabase.table("projects").select("id").eq("id", str(new_channel_payload.project_id)).eq("user_id", str(user_id)).execute()
        )

        if not project_result.data:
            raise UserAuthError(error_detail_message="Project not found or access denied")

        # Create new channel
        channel_data = new_channel_payload.model_dump()
        channel_data["project_id"] = str(channel_data["project_id"])

        channel_result = await supabase.table("channels").insert(channel_data).execute()

        if not channel_result.data:
            raise DataBaseError(error_detail_message="Failed to create channel")

        return ChannelResponse(**channel_result.data[0])

    except (DataBaseError, UserAuthError):
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Something went wrong from our side. Please try again later.")


# --------------------------------------------------------------------------------------------------------------------------


async def get_project_channels(supabase: AsyncClient, project_id: UUID, user_id: UUID) -> List[ChannelResponse]:
    print("get_project_channels service function runs")
    try:
        # First, verify the project belongs to the user
        project_result = await supabase.table("projects").select("id").eq("id", str(project_id)).eq("user_id", str(user_id)).execute()

        if not project_result.data:
            raise UserAuthError(error_detail_message="Project not found or access denied")

        # Get channels for the project
        result = await supabase.table("channels").select("*").eq("project_id", str(project_id)).order("created_at", desc=True).execute()

        return [ChannelResponse(**channel) for channel in result.data]

    except UserAuthError:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Something went wrong from our side. Please try again later.")


# --------------------------------------------------------------------------------------------------------------------------


async def get_channel_by_id(supabase: AsyncClient, channel_id: UUID, user_id: UUID) -> ChannelResponse:
    print("get_channel_by_id service function runs")
    try:
        channel_verification_result = await supabase.rpc(
            "get_channel_with_user_verification", {"channel_id_param": str(channel_id), "user_id_param": str(user_id)}
        ).execute()

        if not channel_verification_result.data:
            raise UserAuthError(error_detail_message="Channel not found or access denied")

        return ChannelResponse(**channel_verification_result.data[0])

    except UserAuthError:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Something went wrong from our side. Please try again later.")


# --------------------------------------------------------------------------------------------------------------------------


async def update_channel(supabase: AsyncClient, channel_id: UUID, user_id: UUID, channel_update: ChannelUpdate) -> ChannelResponse:
    print("update_channel service function runs")
    try:

        # Get only non-None values to update
        channel_update_data = {k: v for k, v in channel_update.model_dump().items() if v is not None}

        if not channel_update_data:
            # If nothing to update, just return the current channel
            return await get_channel_by_id(supabase, channel_id, user_id)

        # Update the channel
        channel_update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        result = await supabase.table("channels").update(channel_update_data).eq("id", str(channel_id)).execute()

        if not result.data:
            raise DataBaseError(error_detail_message="Channel update failed")

        return ChannelResponse(**result.data[0])

    except (DataBaseError, UserAuthError):
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Something went wrong from our side. Please try again later.")


# --------------------------------------------------------------------------------------------------------------------------


async def delete_channel(supabase: AsyncClient, channel_id: UUID, user_id: UUID) -> ChannelDeletionResponse:
    print("delete_channel service function runs")
    try:
        await get_channel_by_id(supabase, channel_id, user_id)

        # Delete the channel
        result = await supabase.table("channels").delete().eq("id", str(channel_id)).execute()

        if not result.data:
            raise DataBaseError(error_detail_message="Channel deletion failed")

        return ChannelDeletionResponse(status="success", status_message="Channel deleted successfully")

    except (DataBaseError, UserAuthError):
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Something went wrong from our side. Please try again later.")
