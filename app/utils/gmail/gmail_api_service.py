from google.auth.transport.requests import Request
from app.core.config import app_config_settings
from google.oauth2.credentials import Credentials
import traceback
from googleapiclient.discovery import build
from typing import Dict, Any
from app.custom_error import UserOauthError
from supabase._async.client import AsyncClient
from uuid import UUID
import time
from app.services.user_oauth_credential_services import update_user_oauth_credentials_by_channel_type

# Every Gmail related API calls all uses this service, which interally uses the user's access token.
# In "fetch_gmail_msg_ids_for_contact_in_date_range() / batching"
# In "retrieve_gmail_attachment_body()"
# In "start_gmail_watch() / stop()"
# In "get_gmail_history_delta_msg_ids()"


async def create_gmail_service(
    user_gmail_oauth_data: Dict[str, Any],
    supabase: AsyncClient,
    user_id: UUID,
):
    """Create a Gmail API service instance from stored OAuth data."""
    print("create_gmail_service runs...")

    try:
        tokens = user_gmail_oauth_data.get("tokens", {})

        credentials = Credentials(
            token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=app_config_settings.GOOGLE_CLIENT_ID,
            client_secret=app_config_settings.GOOGLE_CLIENT_SECRET,
            scopes=app_config_settings.GOOGLE_SCOPES.split(),
        )

        # ONLY refresh if token is actually expired
        was_token_refreshed = False
        if credentials.expired:
            print("Token is expired, refreshing...")
            credentials.refresh(Request())
            was_token_refreshed = True
        else:
            print("Token is still valid, no refresh needed")

        print("was_token_refreshed:", was_token_refreshed)

        # Only update database if token was actually refreshed
        if was_token_refreshed:
            # Update the oauth_data with new access token
            user_gmail_oauth_data["tokens"]["access_token"] = credentials.token
            user_gmail_oauth_data["tokens"]["expiry_timestamp"] = int(time.time()) + 3599

            # Save to database
            await update_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail", user_gmail_oauth_data)
            print("Successfully saved refreshed access token to database")

        service = build("gmail", "v1", credentials=credentials)
        return service

    except Exception as e:
        print(f"Error creating Gmail service: {str(e)}")
        print(traceback.format_exc())
        raise UserOauthError(error_detail_message="Please reconnect your Gmail account")
