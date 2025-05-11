from app.core.config import app_config_settings
from typing import Dict, Any, Optional
import traceback
from app.custom_error import GeneralServerError
from urllib.parse import urlencode
import time
import httpx
from fastapi import Depends
from app.utils.app_states import get_async_httpx_client
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from app.custom_error import UserOauthError
from google.auth.transport.requests import Request


def create_gmail_service(oauth_data: Dict[str, Any]):
    """Create a Gmail API service instance from stored OAuth data."""
    print("create_gmail_service runs...")

    tokens = oauth_data.get("tokens", {})

    credentials = Credentials(
        token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=app_config_settings.GOOGLE_CLIENT_ID,
        client_secret=app_config_settings.GOOGLE_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send"],
    )

    try:
        # Attempt to refresh the token to validate it
        credentials.refresh(Request())
    except Exception as e:
        print(f"Error creating Gmail service: {str(e)}")
        print(traceback.format_exc())
        raise UserOauthError(error_detail_message="Error initializing gmail service with oauth crendential")

    service = build("gmail", "v1", credentials=credentials)
    return service


# This function creates the URL that the frontend will navigate to google account directly for authentication
def generate_gmail_oauth_url(state: str) -> str:
    """
    Generate a Google OAuth authorization URL for Gmail integration.

    Args:
        state: additional state used in state parameter (e.g can be channel_id)

    Returns:
        The authorization URL to redirect the user to
    """
    # Define OAuth parameters
    params = {
        "client_id": app_config_settings.GOOGLE_CLIENT_ID,
        "redirect_uri": app_config_settings.GOOGLE_REDIRECT_URI,  # this is specify which redirect URI to use after user consent for this client ID setup on GCP
        "response_type": "code",  # tells Google we want an authorization code
        "scope": app_config_settings.GOOGLE_SCOPES,
        "access_type": "offline",  # It requests a refresh token in addition to the access token
        "prompt": "consent",  # Force consent screen to ensure refresh token is always provided
        "state": state,
    }

    # Create authorization URL
    auth_url = f"https://accounts.google.com/o/oauth2/auth?{urlencode(params)}"
    return auth_url


# ------------------------------------------------------------------------------------------------------------------------


async def exchange_auth_code_for_tokens(auth_code: str, httpx_client: httpx.AsyncClient = Depends(get_async_httpx_client)) -> Dict[str, Any]:
    """
    Exchange an authorization code for access and refresh tokens from Google.
    The response is the google oauth standard response data structure.

    Args:
        code: The authorization code received from the OAuth redirect

    Returns:
        A dictionary containing token information (access_token, refresh_token, etc.)
    """
    try:
        # this is a standard Google OAuth endpoint that won't change
        access_token_exchange_url = "https://oauth2.googleapis.com/token"
        payload = {
            "client_id": app_config_settings.GOOGLE_CLIENT_ID,
            "client_secret": app_config_settings.GOOGLE_CLIENT_SECRET,  # It's sent server-to-server (never exposed to frontend) over HTTPS, which is secure
            "code": auth_code,  # the authorization code received from Google after user consent
            "redirect_uri": app_config_settings.GOOGLE_REDIRECT_URI,  # this must be used again here for security reasons so attackers can't use the code
            "grant_type": "authorization_code",
        }

        response = await httpx_client.post(access_token_exchange_url, data=payload)

        exchanged_token_data = response.json()
        print("exchanged_token_data:", exchanged_token_data)

        # Google returns "expires_in" which is seconds until access token expiration (typically 3600 for 1 hour).
        # We convert this to an absolute timestamp by adding current epoch second time, making it easier to check if the token is expired later
        if "expires_in" in exchanged_token_data:
            # converts it to an integer of current time in seconds since the epoch + the expires_in value
            exchanged_token_data["expiry_timestamp"] = int(time.time()) + exchanged_token_data["expires_in"]

        return exchanged_token_data

    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to exchange tokens")


# ------------------------------------------------------------------------------------------------------------------------


async def get_gmail_user_info(access_token: str, httpx_client: httpx.AsyncClient = Depends(get_async_httpx_client)) -> Dict[str, Any]:
    """
    Get Gmail user profile information using the access token.
    The response is the google standard response data structure for the user info of gmail.

    Args:
        access_token: The access token obtained from OAuth

    Returns:
        User profile information from Gmail
    """
    try:
        headers = {"Authorization": f"Bearer {access_token}"}

        # this is the standard Gmail API endpoint for getting the user's profile information
        response = await httpx_client.get("https://www.googleapis.com/gmail/v1/users/me/profile", headers=headers)

        if response.status_code != 200:
            print(f"Error getting Gmail profile: {response.text}")
            raise GeneralServerError(error_detail_message="Failed to get Gmail profile information")

        gmail_user_info = response.json()
        print("Gmail user info:", gmail_user_info)

        return gmail_user_info

    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to get Gmail user information")


# ------------------------------------------------------------------------------------------------------------------------


# # This is similar to exchange_code_for_tokens but uses the refresh token instead of the authorization code to get a new access token
# # access token (short-lived, ~1 hour) and refresh token (long-lived). When access token expires, we use refresh token to get a new access token
# async def refresh_access_token(refresh_token: str, httpx_client: httpx.AsyncClient = Depends(get_async_httpx_client)) -> Dict[str, Any]:
#     """
#     Get a new access token using a refresh token.

#     Args:
#         refresh_token: The refresh token stored from the original OAuth flow

#     Returns:
#         A dictionary containing the new access token and related information
#     """
#     try:
#         # this is a standard Google OAuth endpoint that won't change
#         access_token_exchange_url = "https://oauth2.googleapis.com/token"
#         payload = {
#             "client_id": app_config_settings.GOOGLE_CLIENT_ID,
#             "client_secret": app_config_settings.GOOGLE_CLIENT_SECRET,
#             "refresh_token": refresh_token,
#             "grant_type": "refresh_token",
#         }

#         response = await httpx_client.post(access_token_exchange_url, data=payload)

#         exchanged_token_data = response.json()
#         print("exchanged_token_data:", exchanged_token_data)

#         # Add expiration timestamp
#         if "expires_in" in exchanged_token_data:
#             exchanged_token_data["expiry_timestamp"] = int(time.time()) + exchanged_token_data["expires_in"]

#         # Keep the existing refresh token if the response doesn't include a new one
#         if "refresh_token" not in exchanged_token_data:
#             exchanged_token_data["refresh_token"] = refresh_token

#         return exchanged_token_data

#     except Exception as e:
#         print(traceback.format_exc())
#         raise GeneralServerError(error_detail_message="Failed to refresh access token")


# ------------------------------------------------------------------------------------------------------------------------


# # This function checks if an access token needs refreshing
# # get sec int of current time since epoch + buffer time (to avoid tokens expiring during API calls) and compares it to the expiry timestamp of the token
# # Returns a simple status object indicating if we need to refresh
# def get_current_token_status(auth_data: Dict[str, Any]) -> Dict[str, Any]:
#     """
#     Check if the current access token is valid or needs refreshing.

#     Args:
#         auth_data: The authentication data stored for the channel

#     Returns:
#         Updated auth_data if refreshed, or original if still valid
#     """

#     current_time = int(time.time())
#     buffer_time = 300  # 5 minutes buffer

#     if "expiry_timestamp" not in auth_data or current_time + buffer_time >= auth_data["expiry_timestamp"]:
#         return {"needs_refresh": True}

#     return {"needs_refresh": False}


# ------------------------------------------------------------------------------------------------------------------------


# async def check_and_refresh_access_token(auth_data: Dict[str, Any], httpx_client: httpx.AsyncClient) -> Dict[str, Any]:
#     """
#     Check if the access token needs to be refreshed and refresh it if necessary.

#     Args:
#         auth_data: The current auth data for the channel
#         httpx_client: HTTPX client for API requests

#     Returns:
#         Updated auth data with refreshed token if needed
#     """
#     token_status = get_current_token_status(auth_data["tokens"])

#     if token_status["needs_refresh"]:
#         # Refresh the token
#         refresh_token = auth_data["tokens"]["refresh_token"]
#         new_tokens = await refresh_access_token(refresh_token, httpx_client)

#         # Update the auth data with new tokens (update is way more efficient than reassigning)
#         auth_data["tokens"].update(new_tokens)

#     return auth_data
