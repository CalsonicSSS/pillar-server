from typing import Dict, Any
from uuid import UUID
from supabase._async.client import AsyncClient
import httpx
from app.custom_error import DataBaseError, GeneralServerError, UserAuthError
import traceback
from app.utils.gmail_oauth_helpers import generate_gmail_auth_url, exchange_auth_code_for_tokens, get_gmail_user_info


async def initialize_gmail_oauth(supabase: AsyncClient, project_id: str, user_id: UUID) -> str:
    """
    Initialize Gmail OAuth flow by creating / integrating a channel and generating an auth URL to kick off oauth process for google gmail.

    Args:
        supabase: Supabase client
        project_id: ID of the project to add the channel to
        user_id: ID of the authenticated user

    Returns:
        OAuth authorization URL to redirect the user to
    """
    print("initialize_gmail_oauth service function runs")
    try:
        # Verify project belongs to user
        project_result = await supabase.table("projects").select("id").eq("id", project_id).eq("user_id", str(user_id)).execute()

        # if no project found or not belongs to user, this will return empty list
        if not project_result.data:
            raise UserAuthError(error_detail_message="Project not found or access denied")

        # Create a new channel record for Gmail
        channel_data = {
            "project_id": project_id,
            "channel_type": "Gmail",
            "is_connected": False,  # Will be set to True after OAuth completion
            "auth_data": None,  # initially set to None, will be updated after OAuth completion
        }

        channel_result = await supabase.table("channels").insert(channel_data).execute()

        if not channel_result.data:
            raise DataBaseError(error_detail_message="Failed to create channel")

        channel_id = channel_result.data[0]["id"]

        # Generate OAuth URL with channel_id in the state parameter
        auth_url = generate_gmail_auth_url(channel_id)
        print("auth_url:", auth_url)

        return {"auth_url": auth_url}

    except (DataBaseError, UserAuthError):
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Something went wrong from our side. Please try again later.")


async def gmail_oauth_complete_callback(supabase: AsyncClient, httpx_client: httpx.AsyncClient, auth_code: str, state: str) -> Dict[str, Any]:
    """
    Complete the OAuth flow after the user has authorized the application by exchanging the authorization code for tokens (for initial connection).
    and updating the channel with the auth data.

    Args:
        supabase: Supabase client
        httpx_client: HTTPX client for API requests
        auth_code: Authorization code received from OAuth callback
        state: State parameter containing the channel ID

    Returns:
        Dictionary with success information
    """
    print("gmail_oauth_complete_callback service function runs")
    print("auth_code:", auth_code)
    print("state (channel id):", state)
    try:
        # The state parameter contains the channel_id
        channel_id = state

        # Verify channel exists
        channel_result = await supabase.table("channels").select("*").eq("id", channel_id).execute()

        if not channel_result.data:
            raise DataBaseError(error_detail_message="Channel not found")

        # Exchange auth code for tokens
        token_data = await exchange_auth_code_for_tokens(auth_code, httpx_client)

        # Get Gmail user info
        user_info = await get_gmail_user_info(token_data["access_token"], httpx_client)

        # Store token and user info in channel auth_data
        auth_data = {"tokens": token_data, "user_info": user_info}

        print("auth_data after oauth complete:", auth_data)

        # Update channel with auth data and mark as connected
        update_data = {"auth_data": auth_data, "is_connected": True}

        update_result = await supabase.table("channels").update(update_data).eq("id", channel_id).execute()

        if not update_result.data:
            raise DataBaseError(error_detail_message="Failed to update channel with OAuth data")

        return {"status": "success", "message": "Gmail connection completed."}

    except DataBaseError:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to complete Gmail authorization")
