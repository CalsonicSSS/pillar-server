from typing import Dict, Any, Optional
from uuid import UUID
from supabase._async.client import AsyncClient
from app.custom_error import DataBaseError, GeneralServerError
import traceback
from datetime import datetime, timezone


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


async def store_user_oauth_credentials(supabase: AsyncClient, user_id: UUID, channel_type: str, oauth_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Store or update OAuth credentials for a user and channel type.
    If credentials already exist, they will be updated.
    """
    print("store_user_oauth_credentials service function runs")
    try:
        # Check if credentials already exist
        user_existing_credentials = await get_user_oauth_credentials_by_channel_type(supabase, user_id, channel_type)

        if user_existing_credentials:
            # Update existing credentials
            result = (
                await supabase.table("user_oauth_credentials")
                .update({"oauth_data": oauth_data, "updated_at": datetime.now(timezone.utc).isoformat()})
                .eq("id", user_existing_credentials["id"])
                .execute()
            )
        else:
            # Create new credentials
            user_new_credentials = {"user_id": str(user_id), "channel_type": channel_type, "oauth_data": oauth_data}
            result = await supabase.table("user_oauth_credentials").insert(user_new_credentials).execute()

        if not result.data:
            raise DataBaseError(error_detail_message="Failed to store OAuth credentials")

        return result.data[0]

    except DataBaseError:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to store OAuth credentials")
