from google.auth.transport.requests import Request
from app.core.config import app_config_settings
from google.oauth2.credentials import Credentials
import traceback
from googleapiclient.discovery import build
from typing import Dict, Any
from app.custom_error import UserOauthError

# Every Gmail related API calls all uses this service, which interally uses the user's access token.
# In "fetch_gmail_msg_ids_for_contact_in_date_range() / batching"
# In "retrieve_gmail_attachment_body()"
# In "start_gmail_watch() / stop()"
# In "get_gmail_history_delta_msg_ids()"


def create_gmail_service(user_gmail_oauth_data: Dict[str, Any]):
    """Create a Gmail API service instance from stored OAuth data."""
    print("create_gmail_service runs...")

    try:
        tokens = user_gmail_oauth_data.get("tokens", {})

        credentials = Credentials(
            token=tokens.get("access_token"),  # ← This is what authorizes API calls
            refresh_token=tokens.get("refresh_token"),  # ← This renews expired access tokens
            token_uri="https://oauth2.googleapis.com/token",
            client_id=app_config_settings.GOOGLE_CLIENT_ID,
            client_secret=app_config_settings.GOOGLE_CLIENT_SECRET,
            scopes=app_config_settings.GOOGLE_SCOPES.split(),
        )

        # This line automatically refreshes if access_token is expired
        # 1. Checks if access_token is expired
        # 2. If expired, uses refresh_token to get a new access_token
        # 3. Updates the credentials object with the new token
        credentials.refresh(Request())  # ← Uses refresh_token to get new access_token ().

        # But it's only stored in memory, not in your Supabase oauth_data!
        # This means every time create_gmail_service runs with an expired access_token, it will refresh and get a new token
        # But NOT update your database
        # Next call will still see the old expired token in DB and refresh again

        service = build("gmail", "v1", credentials=credentials)
        return service

    except Exception as e:
        print(f"Error creating Gmail service: {str(e)}")
        print(traceback.format_exc())
        raise UserOauthError(
            error_detail_message="Error initializing service with your current oauth credentials. Please reconnect your Gmail account"
        )
