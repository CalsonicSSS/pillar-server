import httpx
import traceback
from typing import Dict, Any, List, Optional
from app.custom_error import GeneralServerError
from app.utils.gmail_oauth_helpers import check_and_refresh_access_token


async def get_list_messages(
    auth_data: Dict[str, Any], httpx_client: httpx.AsyncClient, query: str = None, max_results: int = 100
) -> List[Dict[str, Any]]:
    """
    List Gmail messages that match a query.

    Args:
        auth_data: The auth data for the Gmail channel
        httpx_client: HTTPX client for API requests
        query: Gmail search query (e.g., "after:2025-04-01")
        max_results: Maximum number of results to return

    Returns:
        List of message metadata from Gmail API
    """

    print("get_list_messages function runs")

    try:
        # Check and refresh token if needed
        channel_auth_data = await check_and_refresh_access_token(auth_data, httpx_client)
        access_token = channel_auth_data["tokens"]["access_token"]

        # Set up request parameters
        params = {"maxResults": max_results}
        if query:
            params["q"] = query

        # Make API request to Gmail
        headers = {"Authorization": f"Bearer {access_token}"}
        response = await httpx_client.get("https://www.googleapis.com/gmail/v1/users/me/messages", headers=headers, params=params)

        response_data = response.json()

        print("Gmail API for list of message:", response_data)

        # Return messages or empty list if none found
        return response_data.get("messages", [])

    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to list Gmail messages")


# ---------------------------------------------------------------------------------------------------------------------------------------------


async def get_message(auth_data: Dict[str, Any], httpx_client: httpx.AsyncClient, message_id: str, format: str = "full") -> Dict[str, Any]:
    """
    Get details of a specific Gmail message.

    Args:
        auth_data: The auth data for the Gmail channel
        httpx_client: HTTPX client for API requests
        message_id: The ID of the message to fetch
        format: Message format (full, minimal, raw, metadata)

    Returns:
        Message details from Gmail API
    """
    try:
        # Check and refresh token if needed
        channel_auth_data = await check_and_refresh_access_token(auth_data, httpx_client)
        access_token = channel_auth_data["tokens"]["access_token"]

        # Make API request to Gmail
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"format": format}

        response = await httpx_client.get(f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}", headers=headers, params=params)

        message = response.json()
        print("Gmail API for message:", message)

        return message

    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to get Gmail message")


# ---------------------------------------------------------------------------------------------------------------------------------------------


async def fetch_contacts_messages_in_date_range(
    auth_data: Dict[str, Any],
    httpx_client: httpx.AsyncClient,
    start_date: str,
    end_date: str,
    contact_emails: List[str] = None,
    max_results: int = 100,
) -> List[Dict[str, Any]]:
    """
    Fetch Gmail messages within a specific date range and optionally from specific contacts.

    Args:
        auth_data: The auth data for the Gmail channel
        httpx_client: HTTPX client for API requests
        start_date: Start date in format YYYY/MM/DD
        end_date: End date in format YYYY/MM/DD
        contact_emails: Optional list of contact email addresses to filter by
        max_results: Maximum number of results to return

    Returns:
        List of messages from Gmail API
    """
    print("fetch_messages_in_date_range function runs")
    try:
        # Build the Gmail search query
        query_parts = [f"after:{start_date}", f"before:{end_date}"]

        # Add contact email filters if provided
        if contact_emails:
            email_filters = []
            for email in contact_emails:
                email_filters.append(f"from:{email}")
                email_filters.append(f"to:{email}")

            # Combine with OR operator
            email_query = " OR ".join(email_filters)
            query_parts.append(f"({email_query})")

        query = " ".join(query_parts)

        # Fetch messages matching the query
        messages = await get_list_messages(auth_data, httpx_client, query, max_results)

        # For each message ID, fetch the full message details
        full_messages = []
        for msg in messages:
            message_detail = await get_message(auth_data, httpx_client, msg["id"])
            full_messages.append(message_detail)

        return full_messages

    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to fetch Gmail messages in date range")
