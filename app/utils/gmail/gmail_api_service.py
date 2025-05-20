from google.auth.transport.requests import Request
from app.core.config import app_config_settings
from google.oauth2.credentials import Credentials
import traceback
from googleapiclient.discovery import build
from typing import Dict, Any
from app.custom_error import UserOauthError


def create_gmail_service(user_gmail_oauth_data: Dict[str, Any]):
    """Create a Gmail API service instance from stored OAuth data."""
    print("create_gmail_service runs...")

    tokens = user_gmail_oauth_data.get("tokens", {})

    credentials = Credentials(
        token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=app_config_settings.GOOGLE_CLIENT_ID,
        client_secret=app_config_settings.GOOGLE_CLIENT_SECRET,
        scopes=app_config_settings.GOOGLE_SCOPES.split(),
    )

    try:
        # Attempt to refresh the token to validate it
        credentials.refresh(Request())
    except Exception as e:
        print(f"Error creating Gmail service: {str(e)}")
        print(traceback.format_exc())
        raise UserOauthError(error_detail_message="Error initializing gmail service with current user oauth crendential")

    service = build("gmail", "v1", credentials=credentials)
    return service
