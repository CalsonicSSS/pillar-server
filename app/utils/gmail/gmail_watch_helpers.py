from typing import Dict, Any, Optional
import traceback
from datetime import datetime, timezone, timedelta
from app.custom_error import UserOauthError, GeneralServerError
from app.utils.gmail.gmail_api_service import create_gmail_service
from supabase._async.client import AsyncClient
from uuid import UUID


async def start_gmail_watch(oauth_data: Dict[str, Any], topic_name: str, supabase: AsyncClient, user_id: UUID) -> Dict[str, Any]:
    """
    Start watching a specific user Gmail account for real-time changes using the Watch API.
    WATCHES BOTH INBOX AND SENT for complete conversation tracking.

    Args:
        oauth_data: User's Gmail OAuth credentials
        topic_name: The Pub/Sub topic name to send notifications to

    Returns:
        Dictionary containing watch response data including historyId and expiration
    """
    print("start_gmail_watch function runs...")
    try:
        # Create Gmail service
        gmail_service = await create_gmail_service(oauth_data, supabase, user_id)

        # UPDATED: Watch both INBOX (received) and SENT (user's sent messages)
        watch_request = {
            "topicName": topic_name,
            "labelIds": ["INBOX", "SENT"],  # UPDATED: Now includes SENT messages
            "labelFilterAction": "include",
        }

        # Start watching
        watch_response = gmail_service.users().watch(userId="me", body=watch_request).execute()

        print(f"Gmail watch started successfully for INBOX + SENT: {watch_response}")

        return {
            "history_id": watch_response.get("historyId"),
            "expiration": watch_response.get("expiration"),
            "topic_name": topic_name,
        }

    except Exception as e:
        print(f"Error starting Gmail watch: {str(e)}")
        print(traceback.format_exc())
        raise UserOauthError(error_detail_message=f"Failed to start Gmail watch: {str(e)}")


async def stop_gmail_watch(oauth_data: Dict[str, Any], supabase: AsyncClient, user_id: UUID) -> Dict[str, Any]:
    """
    Stop watching a Gmail account.

    Args:
        oauth_data: User's Gmail OAuth credentials

    Returns:
        Dictionary containing success status
    """
    print("stop_gmail_watch function runs...")
    try:
        # Create Gmail service
        gmail_service = await create_gmail_service(oauth_data, supabase, user_id)

        # Stop watching
        gmail_service.users().stop(userId="me").execute()

        print("Gmail watch stopped successfully")

        return {"status": "stopped"}

    except Exception as e:
        print(f"Error stopping Gmail watch: {str(e)}")
        print(traceback.format_exc())
        raise UserOauthError(error_detail_message=f"Failed to stop Gmail watch: {str(e)}")


def get_gmail_watch_expiration_datetime(expiration_timestamp: str) -> datetime:
    """
    Convert Gmail watch expiration timestamp to datetime object.

    Args:
        expiration_timestamp: The expiration timestamp from Gmail watch API (in milliseconds)

    Returns:
        Datetime object representing the expiration time
    """
    # Gmail returns expiration in milliseconds since epoch
    expiration_ms = int(expiration_timestamp)
    expiration_datetime = datetime.fromtimestamp(expiration_ms / 1000, tz=timezone.utc)

    return expiration_datetime


def is_gmail_watch_expired(expiration_timestamp: str, buffer_hours: int) -> bool:
    """
    Check if Gmail watch is expired or will expire soon.

    Args:
        expiration_timestamp: The expiration timestamp from Gmail API
        buffer_hours: Hours before expiration to consider as "expired" (for renewal)

    Returns:
        True if expired or will expire within buffer_hours
    """
    expiration_datetime = get_gmail_watch_expiration_datetime(expiration_timestamp)
    buffer_datetime = datetime.now(timezone.utc) + timedelta(hours=buffer_hours)

    return buffer_datetime >= expiration_datetime
