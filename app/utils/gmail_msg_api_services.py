import httpx
import traceback
from typing import Dict, Any, List, Optional
from app.custom_error import GeneralServerError
from app.utils.gmail_oauth_helpers import check_and_refresh_access_token
from datetime import datetime, timedelta, timezone
import base64
from uuid import UUID
import json
import uuid
import asyncio
from typing import Dict, List, Any
import httpx
import email.parser


# Google issues an access token that is specifically tied to that user's choosen account to be in pillar.
# This will later store in the channel table in the auth_data column, specific to project and which is specific to the target user.
# Here, we follow common practice to store each user's access token in a user-specific record such "channel".
# Each user's data remains isolated and secure.
# API requests are made on behalf of the correct user by using their specific access token (which is channel -> project -> user specific).


async def get_raw_messages_api(
    auth_data: Dict[str, Any],
    httpx_client: httpx.AsyncClient,
    query: str = None,
    max_total_results: int = 1000,  # default limit for total
    page_size: int = 50,  # default for page size (max allowed is 500) will be later used to set the maxResults query param per API call
) -> List[Dict[str, Any]]:
    """
    List of Gmail messages that match a query with pagination support.

    Args:
        auth_data: The auth data for the Gmail channel
        httpx_client: HTTPX client for API requests
        query: Gmail search query (e.g., "after:2025-04-01")
        max_total_results: Maximum total number of results to return
        page_size: Number of results per page (max 100 for Gmail API)

    Returns:
        List of message metadata from Gmail API
    """
    print("get_raw_messages_api function runs")

    try:
        # Check and refresh token if needed
        channel_auth_data = await check_and_refresh_access_token(auth_data, httpx_client)
        access_token = channel_auth_data["tokens"]["access_token"]

        all_fetched_raw_messages = []
        page_token = None

        # Paginate through results until we reach max_total_results or no more pages
        while len(all_fetched_raw_messages) < max_total_results:
            # maxResults query param, which dictates the maximum number of messages returned PER API call.
            params = {"maxResults": min(page_size, max_total_results - len(all_fetched_raw_messages))}
            if query:
                params["q"] = query
            if page_token:
                params["pageToken"] = page_token

            # Make API request to Gmail
            # GET https://www.googleapis.com/gmail/v1/users/me/messages?q=in:sent after:2014/01/01 before:2014/02/01
            # Gmail determines which is the user based on the OAuth 2.0 access token included in your API request's Authorization header.
            # When use "me" in the API request, Gmail uses the access token to identify the user and access their mailbox accordingly (very important).
            headers = {"Authorization": f"Bearer {access_token}"}
            response = await httpx_client.get("https://www.googleapis.com/gmail/v1/users/me/messages", headers=headers, params=params)

            response_data = response.json()

            # Extract messages
            raw_messages = response_data.get("messages", [])
            if not raw_messages:
                break  # No more messages to fetch

            all_fetched_raw_messages.extend(raw_messages)

            # Get next page token
            page_token = response_data.get("nextPageToken")
            if not page_token:
                break  # No more pages

            print(f"Fetched {len(raw_messages)} messages, total so far: {len(all_fetched_raw_messages)}")

        print(f"Total messages fetched: {len(all_fetched_raw_messages)}")
        return all_fetched_raw_messages

    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to list Gmail messages")


# ---------------------------------------------------------------------------------------------------------------------------------------------


async def get_full_messages_through_batch_api(
    auth_data: Dict[str, Any],
    httpx_client: httpx.AsyncClient,
    all_message_ids: List[str],
    format: str = "full",
    batch_size: int = 50,  # Gmail API recommends max 50 requests per batch
) -> List[Dict[str, Any]]:
    """
    Get full details of multiple Gmail messages using true Gmail API batch requests.

    This implements the multipart/mixed batch request mechanism as described in the
    Gmail API documentation, which allows multiple API calls in a single HTTP request.

    Args:
        auth_data: The auth data for the Gmail channel
        httpx_client: HTTPX client for API requests
        all_message_ids: List of message IDs to fetch
        format: Message format (full, minimal, raw, metadata)
        batch_size: Number of requests per batch (max 100, recommended 50 or less)

    Returns:
        List of full message details from Gmail API
    """
    print("get_full_messages_through_batch_api function runs")
    try:
        # Check and refresh token if needed
        channel_auth_data = await check_and_refresh_access_token(auth_data, httpx_client)
        access_token = channel_auth_data["tokens"]["access_token"]

        all_full_messages = []
        total_batches = (len(all_message_ids) + batch_size - 1) // batch_size  # Ceiling division

        # Process in batches of batch_size
        for batch_index in range(total_batches):
            start_idx = batch_index * batch_size
            end_idx = min(start_idx + batch_size, len(all_message_ids))
            batch_ids = all_message_ids[start_idx:end_idx]

            # Generate a unique boundary string
            boundary = f"batch_boundary_{uuid.uuid4().hex}"

            # Build multipart request body
            body_parts = []

            for i, msg_id in enumerate(batch_ids):
                # Add boundary
                body_parts.append(f"--{boundary}")

                # Add part headers
                body_parts.append("Content-Type: application/http")
                body_parts.append(f"Content-ID: <request-{i}>")
                body_parts.append("")  # Empty line after headers

                # Add the HTTP request line and headers
                body_parts.append(f"GET /gmail/v1/users/me/messages/{msg_id}?format={format} HTTP/1.1")
                body_parts.append("Accept: application/json")
                body_parts.append(f"Authorization: Bearer {access_token}")
                body_parts.append("")  # Empty line to separate headers from body
                body_parts.append("")  # Empty body for GET requests

            # Close the multipart body
            body_parts.append(f"--{boundary}--")

            # Join all parts with CRLF
            multipart_body = "\r\n".join(body_parts)

            # Set up headers for the batch request
            headers = {"Content-Type": f"multipart/mixed; boundary={boundary}", "Authorization": f"Bearer {access_token}"}

            # Make the batch request
            response = await httpx_client.post("https://www.googleapis.com/batch/gmail/v1", headers=headers, content=multipart_body.encode("utf-8"))

            if response.status_code != 200:
                print(f"Batch request failed: {response.status_code}")
                print(f"Response: {response.text[:500]}...")  # Log first 500 chars of error response
                continue

            # Parse the multipart response using email.parser
            # First, add a proper Content-Type header to help the parser
            msg_content = f"Content-Type: {response.headers['Content-Type']}\r\n\r\n{response.text}"

            # Parse the MIME message
            parser = email.parser.Parser()
            mime_message = parser.parsestr(msg_content)

            # Process each part of the multipart response
            for part in mime_message.get_payload():
                # Check if this is an HTTP response part
                if part.get_content_type() == "application/http":
                    # Get the payload which contains the HTTP response
                    http_response = part.get_payload()

                    # Check status code more explicitly
                    status_line = http_response.split("\n")[0]
                    if "HTTP/1.1 200" not in status_line:
                        if "HTTP/1.1 4" in status_line or "HTTP/1.1 5" in status_line:
                            print(f"Error in batch part: {status_line}")
                        continue

                    # More robust approach to find JSON body
                    parts = http_response.split("\r\n\r\n")
                    if len(parts) >= 2:
                        json_text = parts[-1]  # Last part after headers
                        try:
                            message = json.loads(json_text)
                            all_full_messages.append(message)
                        except json.JSONDecodeError as e:
                            print(f"Failed to parse JSON: {e}")

            print(f"Processed batch {batch_index + 1}/{total_batches}, retrieved {len(all_full_messages)} full messages so far in this batch")

            # Small delay between batches to avoid rate limiting
            if batch_index < total_batches - 1:
                await asyncio.sleep(0.3)

        print(f"Total full messages retrieved: {len(all_full_messages)}")
        return all_full_messages

    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to batch get Gmail messages")


# ---------------------------------------------------------------------------------------------------------------------------------------------


async def fetch_target_contact_email_messages_in_date_range(
    auth_data: Dict[str, Any],
    httpx_client: httpx.AsyncClient,
    start_date: str,
    end_date: str,
    contact_email: str,
    max_total_results: int = 1000,
) -> List[Dict[str, Any]]:
    """
    Fetch Gmail messages within a specific date range and from a specific contact.
    Handles pagination and batch processing for efficiency.

    Args:
        auth_data: The auth data for the Gmail channel
        httpx_client: HTTPX client for API requests
        start_date: Start date in format YYYY/MM/DD
        end_date: End date in format YYYY/MM/DD
        contact_email: Optional contact email address to filter by
        max_total_results: Maximum total number of results to return

    Returns:
        List of full messages from Gmail API
    """
    print("fetch_target_contact_email_messages_in_date_range function runs")
    try:
        # Build the Gmail search query
        query_parts = [f"after:{start_date}", f"before:{end_date}"]

        email_query = f"(from:{contact_email} OR to:{contact_email})"
        query_parts.append(email_query)

        query = " ".join(query_parts)
        print("Gmail API url query:", query)

        # Fetch message IDs with pagination
        all_raw_messages = await get_raw_messages_api(auth_data, httpx_client, query, max_total_results=max_total_results)

        if not all_raw_messages:
            print("No messages found matching the criteria")
            return []

        # Extract just the IDs for batch processing
        all_message_ids = [msg["id"] for msg in all_raw_messages]
        print(f"Found {len(all_message_ids)} messages, fetching full details")

        # Fetch full message details in batches
        all_full_messages = await get_full_messages_through_batch_api(auth_data, httpx_client, all_message_ids)
        print("all_full_messages:", all_full_messages)

        return all_full_messages

    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to fetch Gmail messages in date range")


# ---------------------------------------------------------------------------------------------------------------------------------------------


def transform_fetched_gmail_message(gmail_message: Dict[str, Any], channel_id: UUID, contact_id: UUID, user_email: str) -> Dict[str, Any]:
    """
    Process a Gmail message into our application's format.

    Args:
        gmail_message: Raw Gmail API message
        channel_id: Channel ID
        contact_id: Contact ID
        user_email: The user's email address to determine message direction

    Returns:
        Processed message data ready for database storage
    """
    # Default message data
    print("transform_fetched_gmail_message function runs")
    message_data = {
        "platform_message_id": gmail_message["id"],
        "channel_id": str(channel_id),
        "contact_id": str(contact_id),
        "thread_id": gmail_message.get("threadId"),
        "sender_email": "",
        "recipient_emails": [],
        "subject": "",
        "body_text": "",
        "body_html": "",
        "registered_at": datetime.now().isoformat(),  # Default
        "is_read": False,
        "is_from_contact": False,
    }

    # Use internalDate for registered_at (convert from milliseconds to datetime)
    if "internalDate" in gmail_message:
        try:
            # internalDate is in milliseconds since epoch
            timestamp_ms = int(gmail_message["internalDate"])
            date_obj = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            message_data["registered_at"] = date_obj.isoformat()
        except Exception:
            # If parsing fails, keep the default
            pass

    # Extract headers
    headers = {}
    for header in gmail_message.get("payload", {}).get("headers", []):
        headers[header.get("name", "").lower()] = header.get("value", "")

    # Get sender email
    if "from" in headers:
        # Extract email from "From" header (e.g., "John Doe <john@example.com>")
        from_parts = headers["from"].split("<")
        if len(from_parts) > 1:
            message_data["sender_email"] = from_parts[1].strip(">")
        else:
            message_data["sender_email"] = headers["from"]

    # Determine if message is from contact or from user
    message_data["is_from_contact"] = message_data["sender_email"] != user_email

    # Get recipient emails
    if "to" in headers:
        # Split multiple recipients and extract emails
        recipients = headers["to"].split(",")
        for recipient in recipients:
            recipient = recipient.strip()
            if "<" in recipient:
                email = recipient.split("<")[1].strip(">")
            else:
                email = recipient
            message_data["recipient_emails"].append(email)

    # Get subject
    if "subject" in headers:
        message_data["subject"] = headers["subject"]

    # Get message body
    parts = gmail_message.get("payload", {}).get("parts", [])
    if parts:
        for part in parts:
            mimeType = part.get("mimeType", "")
            if mimeType == "text/plain" and "body" in part and "data" in part["body"]:
                data = part["body"]["data"].replace("-", "+").replace("_", "/")
                message_data["body_text"] = base64.b64decode(data).decode("utf-8")
            elif mimeType == "text/html" and "body" in part and "data" in part["body"]:
                data = part["body"]["data"].replace("-", "+").replace("_", "/")
                message_data["body_html"] = base64.b64decode(data).decode("utf-8")

    # Handle case where payload doesn't have parts but has body directly (single-part messages)
    if not parts and "body" in gmail_message.get("payload", {}) and "data" in gmail_message["payload"]["body"]:
        data = gmail_message["payload"]["body"]["data"].replace("-", "+").replace("_", "/")

        # Determine the MIME type from the payload
        mimeType = gmail_message["payload"].get("mimeType", "text/plain")

        if "text/plain" in mimeType:
            message_data["body_text"] = base64.b64decode(data).decode("utf-8")
        elif "text/html" in mimeType:
            message_data["body_html"] = base64.b64decode(data).decode("utf-8")

    return message_data
