from typing import Dict, List, Any, Optional
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timezone, timedelta
import base64
import traceback
from app.core.config import app_config_settings


def create_gmail_service(oauth_data: Dict[str, Any]):
    """Create a Gmail API service instance from stored OAuth data."""
    print("create_gmail_service runs...")
    try:
        tokens = oauth_data.get("tokens", {})

        credentials = Credentials(
            token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=app_config_settings.GOOGLE_CLIENT_ID,
            client_secret=app_config_settings.GOOGLE_CLIENT_SECRET,
            scopes=["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send"],
        )
        service = build("gmail", "v1", credentials=credentials)
        return service
    except Exception as e:
        print(f"Error creating Gmail service: {str(e)}")
        print(traceback.format_exc())
        return None


async def fetch_full_gmail_messages_for_contact_in_date_range(
    oauth_data: Dict[str, Any], start_date: str, end_date: datetime, contact_email: str, max_results: int = 1000
) -> List[Dict[str, Any]]:
    """
    Fetch Gmail messages for a specific contact within a date range using batch requests.
    """
    print("fetch_full_gmail_messages_for_contact_in_date_range runs...")
    try:
        # Create Gmail service
        service = create_gmail_service(oauth_data)
        if not service:
            return []

        next_day = (end_date + timedelta(days=1)).strftime("%Y/%m/%d")
        print(f"Start date: {start_date}, End date: {next_day}")

        # Build search query
        # as tested, after is inclusive and before is exclusive, so we have to do next day +1
        query = f"(from:{contact_email} OR to:{contact_email}) after:{start_date} before:{next_day}"
        print(f"Query: {query}")

        # Get message IDs
        response = service.users().messages().list(userId="me", q=query, maxResults=min(max_results, 100)).execute()
        print(f"First raw fetch Response: {response}")

        fetched_raw_messages = response.get("messages", [])
        next_page_token = response.get("nextPageToken")

        # Handle pagination if needed
        while next_page_token and len(fetched_raw_messages) < max_results:
            page_response = (
                service.users()
                .messages()
                .list(userId="me", q=query, pageToken=next_page_token, maxResults=min(max_results - len(fetched_raw_messages), 100))
                .execute()
            )

            fetched_raw_messages.extend(page_response.get("messages", []))
            next_page_token = page_response.get("nextPageToken")

            if len(fetched_raw_messages) >= max_results:
                break

        print(f"Total raw message fetched: {len(fetched_raw_messages)}")

        if not fetched_raw_messages:
            return []

        # Fetch full messages using batch requests
        full_messages = []
        batch_size = 50  # Google recommends 50-100 requests per batch

        # Process messages in batches
        for i in range(0, len(fetched_raw_messages), batch_size):
            raw_messages_in_current_batch = fetched_raw_messages[i : i + batch_size]
            batch_results = {}

            # Create a batch request
            batch = service.new_batch_http_request()

            # Add callback function to process each response
            def callback_factory(message_id):
                def callback(request_id, response, exception):
                    if exception:
                        print(f"Error fetching message {message_id}: {exception}")
                    else:
                        batch_results[message_id] = response

                return callback

            # Add each message to the batch
            for msg in raw_messages_in_current_batch:
                msg_id = msg["id"]
                batch.add(service.users().messages().get(userId="me", id=msg_id, format="full"), callback=callback_factory(msg_id))

            # Execute the batch request for all raw messages within the current batch
            batch.execute()

            # Add results to full_messages
            for msg in raw_messages_in_current_batch:
                msg_id = msg["id"]
                if msg_id in batch_results:
                    full_messages.append(batch_results[msg_id])

            print(f"Processed batch: {i//batch_size + 1}, messages: {len(batch_results)}")

        print(f"Total full messages fetched: {len(full_messages)}")
        print("full_messages: ", full_messages)
        return full_messages

    except Exception as e:
        print(f"Error fetching messages: {str(e)}")
        print(traceback.format_exc())
        return []


# -------------------------------------------------------------------------------------------------------------------------------------


def get_email_body(fetched_full_gmail_message, supabase_message_data):
    """
    Extract email body from Gmail message with support for nested structures.
    Handles various MIME types and nested multipart messages.
    Strips out quoted previous messages for cleaner display.
    """

    # Helper function to clean content by removing quoted text
    def clean_email_content(content, is_html=False):
        if not content:
            return content

        if is_html:
            # Handle HTML content
            import re

            # Remove Gmail's quoted content (blockquotes)
            content = re.sub(r"<blockquote.*?>.*?</blockquote>", "", content, flags=re.DOTALL)

            # Remove Gmail quote containers
            content = re.sub(r'<div class=["\']gmail_quote["\'].*?>.*?</div>', "", content, flags=re.DOTALL)
            content = re.sub(r'<div class=["\']gmail_quote.*?>.*?</div>', "", content, flags=re.DOTALL)

            # Remove reply headers
            content = re.sub(r'<div class=["\']reply.*?>.*?</div>', "", content, flags=re.DOTALL)
            content = re.sub(r"On.*?wrote:", "", content, flags=re.DOTALL | re.IGNORECASE)

            # Clean up any empty divs or excessive spacing that might remain
            content = re.sub(r"<div>\s*</div>", "", content)
            content = re.sub(r"<br>\s*<br>\s*<br>", "<br><br>", content)

            return content.strip()
        else:
            # Handle plain text content
            import re

            # Remove lines after common reply markers
            markers = [
                r"On .* wrote:",
                r"-+\s*Original Message\s*-+",
                r"-+\s*Forwarded Message\s*-+",
                r"^From:.*$\n^Sent:.*$\n^To:",
                r"^>.*$",  # Basic quote markers (lines starting with >)
                r"^On.*at.*$",  # Common datetime format in replies
            ]

            for marker in markers:
                pattern = re.compile(marker, re.IGNORECASE | re.MULTILINE)
                match = pattern.search(content)
                if match:
                    content = content[: match.start()].strip()

            # Remove extra blank lines at the end
            content = re.sub(r"\n+$", "", content)
            return content.strip()

    # Initialize a function to recursively process message parts
    def process_parts(parts, message_data):
        if not parts:
            return

        for part in parts:
            mime_type = part.get("mimeType", "")

            # Handle nested multipart messages
            if mime_type.startswith("multipart/"):
                nested_parts = part.get("parts", [])
                process_parts(nested_parts, message_data)
                continue

            # Get part body data
            body_data = part.get("body", {}).get("data")
            if not body_data:
                continue

            try:
                # Decode the base64 data
                decoded_data = base64.urlsafe_b64decode(body_data.encode("UTF-8"))
                decoded_str = decoded_data.decode("utf-8")

                # Store based on MIME type
                if mime_type == "text/plain" and not message_data["body_text"]:
                    message_data["body_text"] = decoded_str
                elif mime_type == "text/html" and not message_data["body_html"]:
                    message_data["body_html"] = decoded_str
            except Exception as e:
                print(f"Error decoding part with MIME type {mime_type}: {str(e)}")

    # Handle single-part messages (no parts array)
    payload = fetched_full_gmail_message.get("payload", {})

    if "parts" not in payload:
        mime_type = payload.get("mimeType", "")
        body_data = payload.get("body", {}).get("data")

        if body_data:
            try:
                decoded_data = base64.urlsafe_b64decode(body_data.encode("UTF-8"))
                decoded_str = decoded_data.decode("utf-8")

                if "text/plain" in mime_type:
                    supabase_message_data["body_text"] = decoded_str
                elif "text/html" in mime_type:
                    supabase_message_data["body_html"] = decoded_str
                else:
                    # Default to text for unknown types
                    supabase_message_data["body_text"] = decoded_str
            except Exception as e:
                print(f"Error decoding single-part message: {str(e)}")
    else:
        # Process multi-part messages recursively
        process_parts(payload.get("parts", []), supabase_message_data)

    # Clean the extracted content to remove quoted text
    if supabase_message_data["body_html"]:
        supabase_message_data["body_html"] = clean_email_content(supabase_message_data["body_html"], is_html=True)

    if supabase_message_data["body_text"]:
        supabase_message_data["body_text"] = clean_email_content(supabase_message_data["body_text"], is_html=False)


# -------------------------------------------------------------------------------------------------------------------------------------


def transform_fetched_full_gmail_message(
    fetched_full_gmail_message: Dict[str, Any], channel_id: str, contact_id: str, user_email: str
) -> Dict[str, Any]:
    """
    Process a Gmail message into our application's format.

    Args:
        gmail_message: Gmail API message object
        channel_id: Channel ID
        contact_id: Contact ID
        user_email: User's email to determine message direction

    Returns:
        Processed message data for database storage
    """
    print("transform_fetched_full_gmail_message runs...")
    # Default message data
    supabase_message_data = {
        "platform_message_id": fetched_full_gmail_message["id"],
        "channel_id": channel_id,
        "contact_id": contact_id,
        "thread_id": fetched_full_gmail_message.get("threadId"),
        "sender_email": "",
        "recipient_emails": [],
        "subject": "",
        "body_text": "",
        "body_html": "",
        "registered_at": datetime.now().isoformat(),
        "is_read": False,
        "is_from_contact": False,
    }

    # Process internal date
    if "internalDate" in fetched_full_gmail_message:
        # internalDate is in milliseconds since epoch
        timestamp_ms = int(fetched_full_gmail_message["internalDate"])
        date_obj = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        supabase_message_data["registered_at"] = date_obj.isoformat()

    # Process headers
    headers = {}
    for header in fetched_full_gmail_message.get("payload", {}).get("headers", []):
        name = header.get("name", "").lower()
        value = header.get("value", "")
        headers[name] = value

    # Get sender
    if "from" in headers:
        from_value = headers["from"]
        if "<" in from_value:
            supabase_message_data["sender_email"] = from_value.split("<")[1].strip(">")
        else:
            supabase_message_data["sender_email"] = from_value

    # Determine if message is from contact
    supabase_message_data["is_from_contact"] = supabase_message_data["sender_email"].lower() != user_email.lower()

    # Get recipients
    if "to" in headers:
        to_value = headers["to"]
        recipients = to_value.split(",")
        for recipient in recipients:
            recipient = recipient.strip()
            if "<" in recipient:
                email = recipient.split("<")[1].strip(">")
            else:
                email = recipient
            supabase_message_data["recipient_emails"].append(email)

    # Get subject
    supabase_message_data["subject"] = headers.get("subject", "")

    # Start extraction with the message payload
    get_email_body(fetched_full_gmail_message, supabase_message_data)

    return supabase_message_data
