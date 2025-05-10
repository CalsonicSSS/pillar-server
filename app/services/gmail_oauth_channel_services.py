from typing import Dict, Any
from uuid import UUID
from supabase._async.client import AsyncClient
import httpx
from app.custom_error import DataBaseError, GeneralServerError, UserAuthError
import traceback
from app.utils.gmail_oauth_helpers import generate_gmail_oauth_url, exchange_auth_code_for_tokens, get_gmail_user_info
from app.services.oauth_credential_services import get_user_oauth_credentials, store_user_oauth_credentials


async def initialize_gmail_channel_create_and_oauth(supabase: AsyncClient, project_id: str, user_id: UUID) -> Dict[str, Any]:
    """
    Initialize Gmail OAuth flow by creating a channel and either:
    1. Using existing OAuth credentials if available, or
    2. Generating an auth URL to start a new OAuth process

    Args:
        supabase: Supabase client
        project_id: ID of the project to add the channel to
        user_id: ID of the authenticated user

    Returns:
        Dictionary with either auth_url (if OAuth needed) or success message (if using existing credentials)
    """
    print("initialize_gmail_channel_create_and_oauth function runs")
    try:
        # Verify if this project exist under the user
        project_result = await supabase.table("projects").select("id").eq("id", project_id).eq("user_id", str(user_id)).execute()

        if not project_result.data:
            raise UserAuthError(error_detail_message="Project not found or access denied")

        # Check if channel of this type already exists for this project
        existing_channel = await supabase.table("channels").select("id").eq("project_id", project_id).eq("channel_type", "Gmail").execute()

        if existing_channel.data:
            raise DataBaseError(error_detail_message="A Gmail channel already exists for this project")

        # Create a new channel record for Gmail if the channel does not exist under this project
        new_channel_data = {
            "project_id": project_id,
            "channel_type": "Gmail",
            "is_connected": False,  # Will be updated after full OAuth process or immediately if user oauth credentials already exist
        }

        channel_result = await supabase.table("channels").insert(new_channel_data).execute()

        if not channel_result.data:
            raise DataBaseError(error_detail_message="Failed to create channel")

        channel_id = channel_result.data[0]["id"]

        # Check if user already has Gmail OAuth credentials
        user_existing_credentials = await get_user_oauth_credentials(supabase, user_id, "Gmail")

        # If user already has OAuth credentials, update channel as connected and return directly
        if user_existing_credentials:
            # Update channel as connected
            await supabase.table("channels").update({"is_connected": True}).eq("id", channel_id).execute()

            return {
                "status": "success",
                "message": "Gmail channel connected with existing oauth credentials",
                "channel_id": channel_id,
                "requires_oauth": False,
            }

        # Otherwise, generate OAuth URL with channel_id in the state parameter
        oauth_url = generate_gmail_oauth_url(channel_id)
        print("oauth_url:", oauth_url)

        return {"oauth_url": oauth_url, "channel_id": channel_id, "requires_oauth": True}

    except (DataBaseError, UserAuthError):
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Something went wrong from our side. Please try again later.")


async def gmail_oauth_complete_callback(supabase: AsyncClient, httpx_client: httpx.AsyncClient, auth_code: str, state: str) -> Dict[str, Any]:
    """
    Complete the OAuth flow after user authorization by:
    1. Exchanging the authorization code for tokens
    2. Storing tokens at the user level
    3. Updating the channel as connected

    Args:
        supabase: Supabase client
        httpx_client: HTTPX client for API requests
        auth_code: Authorization code received from OAuth callback
        state: State parameter containing the channel ID

    Returns:
        Dictionary with success information
    """
    print("gmail_oauth_complete_callback function runs")
    print("auth_code:", auth_code)
    print("state (channel id):", state)
    try:
        # The state parameter contains the channel_id
        channel_id = state

        # Verify channel exists
        channel_result = await supabase.table("channels").select("*").eq("id", channel_id).execute()

        if not channel_result.data:
            raise DataBaseError(error_detail_message="Channel not found")

        # Get project and user information from the channel
        channel = channel_result.data[0]
        project_id = channel["project_id"]

        # Get user_id from project
        project_result = await supabase.table("projects").select("user_id").eq("id", project_id).execute()
        if not project_result.data:
            raise DataBaseError(error_detail_message="Project not found")

        user_id = project_result.data[0]["user_id"]

        # Exchange auth code for tokens
        token_data = await exchange_auth_code_for_tokens(auth_code, httpx_client)

        # Get Gmail user info
        user_info = await get_gmail_user_info(token_data["access_token"], httpx_client)

        # Store token and user info in oauth_data format
        oauth_data = {"tokens": token_data, "user_info": user_info}

        print("oauth_data after oauth complete:", oauth_data)

        # Store OAuth credentials at user level
        await store_user_oauth_credentials(supabase, UUID(user_id), "Gmail", oauth_data)

        # Update channel as connected
        update_result = await supabase.table("channels").update({"is_connected": True}).eq("id", channel_id).execute()

        if not update_result.data:
            raise DataBaseError(error_detail_message="Failed to update channel connection status")

        return {"status": "success", "message": "Gmail connection completed."}

    except DataBaseError:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to complete Gmail authorization")
