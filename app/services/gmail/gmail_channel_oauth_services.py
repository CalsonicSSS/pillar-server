from uuid import UUID
from supabase._async.client import AsyncClient
import httpx
from app.custom_error import DataBaseError, GeneralServerError, UserAuthError, UserOauthError
import traceback
from app.utils.gmail.gmail_oauth_helpers import generate_gmail_oauth_url, exchange_auth_code_for_tokens, get_gmail_user_info
from app.services.user_oauth_credential_services import (
    get_user_oauth_credentials_by_channel_type,
    update_user_oauth_credentials_by_channel_type,
    create_user_oauth_credentials_by_channel_type,
)
from app.services.gmail.gmail_watch_services import start_gmail_user_watch
from app.models.channel_models import ChannelCreate
from app.models.oauth_process_models import GmailOAuthFlowResponse, GmailOAuthCallbackCompletionResponse
from app.services.channel_services import create_channel, update_channel
from app.models.channel_models import ChannelUpdate


# this is to create a new gmail channel within a specific project
# 1. Check if the project exists and belongs to the user
# 2. Check if a Gmail channel already exists for this project
# 3. If not: Create a new channel record for Gmail
# 4. Check if the user already has Gmail OAuth credentials
# 5. If yes: Update the channel as connected and return success message (no OAuth needed)
# 6. If no: Generate OAuth URL with channel_id as state parameter
async def initialize_gmail_channel_create_and_oauth(supabase: AsyncClient, project_id: str, user_id: UUID) -> GmailOAuthFlowResponse:
    """
    Initialize Gmail OAuth flow + creating gmail channel, either:
    1. Using existing OAuth credentials if available, or
    2. Generating an auth URL to start a new OAuth process

    Args:
        supabase: Supabase client
        project_id: ID of the project to add the channel to
        user_id: ID of the authenticated user

    Returns:
        Dictionary with either auth_url (if a new OAuth process needed) or success message (if using existing credentials)
    """
    print("initialize_gmail_channel_create_and_oauth function runs")
    try:
        # Verify if this project exist under the user
        project_result = await supabase.table("projects").select("id").eq("id", project_id).eq("user_id", str(user_id)).execute()

        if not project_result.data:
            raise UserAuthError(error_detail_message="Project not found or access denied")

        # Check if channel of this type (gmail) already exists for this project
        existing_gmail_channel_type = await supabase.table("channels").select("id").eq("project_id", project_id).eq("channel_type", "gmail").execute()

        if existing_gmail_channel_type.data:
            raise DataBaseError(error_detail_message="A Gmail channel already exists for this project")

        # Create a new channel record for Gmail if the channel does not exist yet under this project
        new_channel_data = ChannelCreate(
            **{
                "project_id": project_id,
                "channel_type": "gmail",
                "is_connected": False,  # Will be updated after full OAuth process or immediately if user oauth credentials already exist
            }
        )

        channel_result = await create_channel(supabase, new_channel_data, user_id)

        channel_id = channel_result.model_dump()["id"]

        # Check if user already has Gmail OAuth credentials TYPE exist (this is cross all project basis)
        user_gmail_credentials = await get_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail")

        # If user already has OAuth credentials FOR GMAIL TYPE, update channel as connected and return directly, we will not go through oauth process here
        if user_gmail_credentials:
            # Update channel as connected directly
            print("user already has initial gmail oauth credentials")
            await update_channel(supabase, channel_id, user_id, {"is_connected": True})

            return GmailOAuthFlowResponse(
                **{
                    "oauth_url": "",
                    "status_message": "Gmail channel connected with existing gmail oauth credentials",
                    "requires_oauth": False,
                }
            )

        # Otherwise, generate OAuth URL with channel_id as state parameter
        print("user dont have initial gmail oauth credentials, generate oauth url")
        oauth_url = generate_gmail_oauth_url(channel_id)

        return GmailOAuthFlowResponse(
            **{
                "oauth_url": oauth_url,
                "status_message": "initialize gmail channel oauth flow to obtain initial gmail oauth credentials",
                "requires_oauth": True,
            }
        )

    except (DataBaseError, UserAuthError):
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Something went wrong from our side. Please try again later.")


# -----------------------------------------------------------------------------------------------------------------------


async def gmail_channel_reoauth_process(supabase: AsyncClient, user_id: UUID):
    print("gmail_reoauth_process function runs")
    # find existing user's invalided credentials for Gmail type
    user_gmail_credentials = await get_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail")
    if user_gmail_credentials:
        # Generate a refresh state with special format
        refresh_state = f"refresh_{str(user_id)}"

        # Generate new OAuth URL
        oauth_url = generate_gmail_oauth_url(refresh_state)

        return GmailOAuthFlowResponse(
            **{
                "oauth_url": oauth_url,
                "status_message": "Gmail OAuth credentials invalidated, re-oauth process required",
                "requires_oauth": True,
            }
        )

    else:
        # If no existing credentials, return an error message
        raise UserOauthError(error_detail_message="No existing Gmail OAuth credentials found for this user")


# -----------------------------------------------------------------------------------------------------------------------


# this is only called when
# 1. user has existing gmail oauth credentials and they are invalidated
# 2. user has no existing gmail oauth credentials yet and this must means a new gmail channel created
async def gmail_channel_oauth_complete_callback(
    supabase: AsyncClient, httpx_client: httpx.AsyncClient, auth_code: str, state: str
) -> GmailOAuthCallbackCompletionResponse:
    """
    This is the post-completion the OAuth flow after user authorization
    1. Exchanging the authorization code for all gmail related tokens (this is also user specific)
    2. Storing tokens at the per user level for WHOLE gmail channel type
    3. starting the gmail watch process for this specific user

    Complete the OAuth flow after user authorization process.
    Handles both new channel creation and credential refreshing.

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
    print("state:", state)
    try:
        # Check if this is the case for token invalidation re-oauth process with existing credentials
        if state.startswith("refresh_"):
            print("gmail oauth process callback for token invalidation case")
            # Extract user_id from refresh state
            user_id = UUID(state.replace("refresh_", ""))

            # Exchange auth code for tokens
            token_data = await exchange_auth_code_for_tokens(auth_code, httpx_client)

            # Get Gmail user info
            user_info = await get_gmail_user_info(token_data["access_token"], httpx_client)

            # Store token and user info in oauth_data format (now this new oauth_data will not have watch_info)
            user_oauth_data = {"tokens": token_data, "user_info": user_info}
            await update_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail", user_oauth_data)

            # at this point, we will start the gmail channel watch for this user
            watch_result = await start_gmail_user_watch(supabase, UUID(user_id))
            print(f"Gmail watch started automatically here after re-oauth progress completed: {watch_result}")

            return GmailOAuthCallbackCompletionResponse(**{"status": "success", "status_message": "Gmail credentials refreshed successfully."})

        # this is the initial oauth process for a new gmail channel creation
        print("gmail oauth process callback for initial establishment")
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

        # Exchange auth code for tokens (google standard ds)
        token_data = await exchange_auth_code_for_tokens(auth_code, httpx_client)

        # Get Gmail user info (google standard ds)
        user_info = await get_gmail_user_info(token_data["access_token"], httpx_client)

        # Construct and Store our custom "oauth_data" DS token using user info in oauth_data format
        user_oauth_data = {"tokens": token_data, "user_info": user_info}

        # Store gmail channel OAuth credentials for this specific user for the first time (now this oauth_data will not have "watch_info")
        await create_user_oauth_credentials_by_channel_type(supabase, UUID(user_id), "gmail", user_oauth_data)

        print("gmail initial oauth_data exchanged and stored complete:", user_oauth_data)

        # Update target channel as "connected"
        update_channel_data = ChannelUpdate(is_connected=True)
        await update_channel(supabase, channel_id, user_id, update_channel_data)

        # start watching for the gmail channel for this user
        watch_result = await start_gmail_user_watch(supabase, UUID(user_id))
        print(f"Gmail watch started automatically here after oauth progress completed: {watch_result}")

        return GmailOAuthCallbackCompletionResponse(
            **{
                "status": "success",
                "status_message": "Gmail channel connected and OAuth process completed successfully.",
            }
        )

    except DataBaseError:
        raise

    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to complete Gmail authorization")
