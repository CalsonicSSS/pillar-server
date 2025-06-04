from typing import Dict, Any, Optional
from uuid import UUID
from supabase._async.client import AsyncClient
from app.custom_error import DataBaseError, GeneralServerError
import traceback
from datetime import datetime, timezone


# based on the user oauth data structure, we can always find specifc one by user_id and channel_type combined
async def get_user_oauth_credentials_by_channel_type(supabase: AsyncClient, user_id: UUID, channel_type: str) -> Optional[Dict[str, Any]]:
    """
    Get OAuth credentials for a specific user and channel type.
    Returns None if credentials don't exist.
    """
    print("get_user_oauth_credentials_by_channel_type service function runs")
    try:
        result = await supabase.table("user_oauth_credentials").select("*").eq("user_id", str(user_id)).eq("channel_type", channel_type).execute()

        if not result.data:
            return None

        return result.data[0]

    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to retrieve OAuth credentials")


# -----------------------------------------------------------------------------------------------------------------------------


async def create_user_oauth_credentials_by_channel_type(
    supabase: AsyncClient, user_id: UUID, channel_type: str, oauth_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Create new OAuth credentials for a user and channel type.
    Raises an error if credentials already exist.
    """
    print("create_user_oauth_credentials_by_channel_type service function runs")
    try:
        # Check if credentials already exist
        existing_credentials = await get_user_oauth_credentials_by_channel_type(supabase, user_id, channel_type)

        if existing_credentials:
            raise DataBaseError(error_detail_message=f"{channel_type} OAuth credentials already exist for user")

        # Create new credentials (for the flexibility, we don't create the model schema for the user oauth as "oauth_data" field in other type can vary)
        user_new_credentials = {"user_id": str(user_id), "channel_type": channel_type, "oauth_data": oauth_data}
        result = await supabase.table("user_oauth_credentials").insert(user_new_credentials).execute()

        if not result.data:
            raise DataBaseError(error_detail_message="Failed to create OAuth credentials")

        return result.data[0]

    except DataBaseError:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to create OAuth credentials")


# -----------------------------------------------------------------------------------------------------------------------------


async def update_user_oauth_credentials_by_channel_type(
    supabase: AsyncClient, user_id: UUID, channel_type: str, oauth_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Update existing OAuth credentials for a user and channel type.
    Raises an error if credentials don't exist.
    """
    print("update_user_oauth_credentials_by_channel_type service function runs")
    try:
        # Check if credentials exist
        existing_credentials = await get_user_oauth_credentials_by_channel_type(supabase, user_id, channel_type)

        if not existing_credentials:
            raise DataBaseError(error_detail_message=f"No {channel_type} OAuth credentials found for user to update upon")

        # Update existing credentials
        result = (
            await supabase.table("user_oauth_credentials")
            .update({"oauth_data": oauth_data, "updated_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", existing_credentials["id"])
            .execute()
        )

        if not result.data:
            raise DataBaseError(error_detail_message="Failed to update OAuth credentials")

        return result.data[0]

    except DataBaseError:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to update OAuth credentials")
