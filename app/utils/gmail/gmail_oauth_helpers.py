from app.core.config import app_config_settings
from typing import Dict, Any, Optional
import traceback
from app.custom_error import GeneralServerError
from urllib.parse import urlencode
import time
import httpx
from fastapi import Depends
from app.utils.app_states import get_async_httpx_client


# this function: Generating the OAuth Consent Screen URL (pointing to Google's OAuth 2.0 authorization endpoint)
# 1. used for user to nav to oauth consent flow page
# 2. they are presented with Google's OAuth consent screen. Here, they can review the permissions your application is requesting.
# 3. After the user grants consent by clicking "Continue" or "Allow," the browser sends a request to Google's authorization server.
#    (This request includes the parameters initially specified here, such as client_id, redirect_uri, response_type=code, scope, and state)
# 4. Then, authorization server processes this request, generates an authorization code -> responds to the browser with an HTTP 302 redirect response.
# 5. The browser then follows this redirect, sending a GET request to redirect_uri.


# This redirection is a client-side browser operation only. The GET REQUEST with redirect_uri
def generate_gmail_oauth_url(state: str) -> str:
    """
    Generate a Google OAuth authorization URL for Gmail integration.

    Args:
        state: additional state used in state parameter (e.g can be channel_id)

    Returns:
        The authorization URL to redirect the user to
    """

    # These parameters configure the consent screen and define the permissions your application is requesting.
    params = {
        "client_id": app_config_settings.GOOGLE_CLIENT_ID,
        "redirect_uri": app_config_settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",  # tells Google we want an authorization code
        "scope": app_config_settings.GOOGLE_SCOPES,
        "access_type": "offline",  # It requests a refresh token in addition to the access token
        "prompt": "consent",  # Force consent screen to ensure refresh token is always provided
        "state": state,
    }

    oauth_url = f"https://accounts.google.com/o/oauth2/auth?{urlencode(params)}"
    return oauth_url


# ------------------------------------------------------------------------------------------------------------------------


# exchange an authorization code for both access token and refresh token.
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
            "client_secret": app_config_settings.GOOGLE_CLIENT_SECRET,
            "code": auth_code,
            "redirect_uri": app_config_settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",  # authorization_code will always exchange both tokens (very important)
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
