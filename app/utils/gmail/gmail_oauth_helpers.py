from app.core.config import app_config_settings
from typing import Dict, Any, Optional
import traceback
from app.custom_error import GeneralServerError
from urllib.parse import urlencode
import time
import httpx
from fastapi import Depends
from app.utils.app_states import get_async_httpx_client


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
        "scope": app_config_settings.GOOGLE_SCOPES,  # Google expects the scope parameter in the authorization URL to be a space-separated string of scopes
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
        print("exchanged_gmail_oauth_token_data:", exchanged_token_data)

        # Google returns "expires_in" which is seconds until access token expiration (typically 3600 for 1 hour).
        # We convert this to an absolute timestamp by adding current epoch second time, making it easier to check if the token is expired later
        if "expires_in" in exchanged_token_data:
            # converts it to an integer of current time in seconds since the epoch + the expires_in value
            exchanged_token_data["expiry_timestamp"] = int(time.time()) + exchanged_token_data["expires_in"]

        return exchanged_token_data

    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to exchange gmail oauth tokens")


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

        gmail_user_info = response.json()
        print("Gmail user info:", gmail_user_info)

        return gmail_user_info

    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to get Gmail user information")
