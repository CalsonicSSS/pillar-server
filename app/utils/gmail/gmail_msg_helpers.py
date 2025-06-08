from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, timedelta
import base64
import traceback
from app.custom_error import UserOauthError, GeneralServerError
from app.utils.gmail.gmail_api_service import create_gmail_service
from supabase._async.client import AsyncClient
from app.utils.gmail.gmail_attachment_helpers import process_gmail_attachments_with_storage


# this function is to leverage gmail message list API to essentially get the list of message ids between the user and target contact
def fetch_gmail_msg_ids_for_contact_in_date_range(
    oauth_data: Dict[str, Any], start_date: str, end_date: datetime, contact_email: str, max_results: int = 1000
) -> List[Dict[str, Any]]:
    """
    Fetch Gmail messages for a specific contact within a date range.

    CAPTURES BOTH DIRECTIONS:
    - Messages FROM contact TO user (received messages)
    - Messages FROM user TO contact (sent messages)

    This gives complete conversation history for each tracked contact.
    """
    print("fetch_gmail_msg_ids_for_contact_in_date_range runs...")
    try:
        gmail_service = create_gmail_service(oauth_data)

        # we do next 2 days range to account for the edge case of when user fetch this near the end of "today"
        next_two_day = (end_date + timedelta(days=2)).strftime("%Y/%m/%d")
        print(f"Start date: {start_date}, End date: {next_two_day}")

        # Build search query - CAPTURES BOTH SENT AND RECEIVED
        # from:{contact_email} = Messages FROM contact TO user (RECEIVED)
        # to:{contact_email} = Messages FROM user TO contact (SENT)
        query = f"(from:{contact_email} OR to:{contact_email}) after:{start_date} before:{next_two_day}"
        print(f"Query (both directions): {query}")

        initial_msg_id_list_response = gmail_service.users().messages().list(userId="me", q=query, maxResults=min(max_results, 100)).execute()
        print(f"First msg ids fetch response: {initial_msg_id_list_response}")

        fetched_raw_messages = initial_msg_id_list_response.get("messages", [])
        next_page_token = initial_msg_id_list_response.get("nextPageToken")

        while next_page_token and len(fetched_raw_messages) < max_results:
            page_response = (
                gmail_service.users()
                .messages()
                .list(userId="me", q=query, pageToken=next_page_token, maxResults=min(max_results - len(fetched_raw_messages), 100))
                .execute()
            )

            fetched_raw_messages.extend(page_response.get("messages", []))
            next_page_token = page_response.get("nextPageToken")

            if len(fetched_raw_messages) >= max_results:
                break

        print(f"Total messages fetched (both sent + received): {len(fetched_raw_messages)}")

        if not fetched_raw_messages:
            return []

        msg_ids = [msg["id"] for msg in fetched_raw_messages]
        return msg_ids

    except UserOauthError:
        raise

    except Exception as e:
        print(f"Failed to fetch Gmail message ids for:{contact_email}.\n {str(e)}")
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message=f"Failed to fetch Gmail message ids for contact {contact_email}")


# -------------------------------------------------------------------------------------------------------------------------------------


# this is the functions used in both initial gmail message fetch and pub/sub message fetch through batch for a full message.
# format is set to format="full", so it will return the full message object with attachments
def batch_get_gmail_full_messages(user_oauth_data: Dict[str, Any], message_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Fetch full Gmail messages in batches using the Gmail API.

    Args:
        user_oauth_data: User's Gmail OAuth credentials
        message_ids: List of message IDs to fetch

    Returns:
        List of full message objects
    """
    print(f"batch_get_gmail_full_messages runs.... for {len(message_ids)} messages")
    try:
        if not message_ids:
            return []

        # Create Gmail service
        gmail_service = create_gmail_service(user_oauth_data)

        full_messages = []
        batch_size = 50  # Google recommends 50-100 requests per batch

        # Process messages in batches
        for i in range(0, len(message_ids), batch_size):
            current_batch_msg_ids = message_ids[i : i + batch_size]
            batch_results = {}

            # Create a batch request
            batch = gmail_service.new_batch_http_request()

            # Add callback function to process each response
            def callback_factory(msg_id):
                def callback(request_id, response, exception):
                    if exception:
                        print(f"Error fetching message {msg_id}: {exception}")
                    else:
                        batch_results[msg_id] = response

                return callback

            # Add each message to the batch
            for msg_id in current_batch_msg_ids:
                batch.add(gmail_service.users().messages().get(userId="me", id=msg_id, format="full"), callback=callback_factory(msg_id))

            # Execute the batch request
            batch.execute()

            # Add results to full_messages
            for msg_id in current_batch_msg_ids:
                if msg_id in batch_results:
                    full_messages.append(batch_results[msg_id])

            print(f"Processed batch {i//batch_size + 1}, fetched {len(batch_results)} messages")

        return full_messages

    except Exception as e:
        print(f"Error batch getting Gmail messages: {str(e)}")
        print(traceback.format_exc())
        raise UserOauthError(error_detail_message=f"Failed to batch get Gmail messages: {str(e)}")


# -------------------------------------------------------------------------------------------------------------------------------------


# to extract and process, clean the body of the email from the fetched full gmail message.
# only later used in the transform_and_process_fetched_full_gmail_message_with_attachments function
def extract_and_process_gmail_body(fetched_full_gmail_message, supabase_message_data):
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
                raise

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
                raise
    else:
        # Process multi-part messages recursively
        process_parts(payload.get("parts", []), supabase_message_data)

    # Clean the extracted content to remove quoted text
    if supabase_message_data["body_html"]:
        supabase_message_data["body_html"] = clean_email_content(supabase_message_data["body_html"], is_html=True)

    if supabase_message_data["body_text"]:
        supabase_message_data["body_text"] = clean_email_content(supabase_message_data["body_text"], is_html=False)


# -------------------------------------------------------------------------------------------------------------------------------------


# this function is also used in both initial gmail message fetch and pub/sub message fetch after batching
# the goal is to transform the fetched full gmail message into a format that can be stored in our database
# also automatically retrieve and store message attachments if there is any
async def transform_and_process_fetched_full_gmail_message_with_attachments(
    fetched_full_gmail_message: Dict[str, Any],
    contact_id: str,
    user_email: str,
    user_oauth_data: Dict[str, Any],  # NEW: Need OAuth data for attachment download
    supabase: AsyncClient,  # NEW: Need Supabase client for storage
) -> Dict[str, Any]:
    """
    Process a Gmail message into our application's format.
    Downloads and stores attachments automatically.

    Args:
        fetched_full_gmail_message: Gmail API message object
        contact_id: Contact ID
        user_email: User's email to determine message direction
        user_oauth_data: User's Gmail OAuth credentials for attachment download
        supabase: Supabase client for storage operations

    Returns:
        Processed message data for database storage
    """
    print("transform_fetched_full_gmail_message_with_attachments runs...")

    # Default message data
    supabase_message_data = {
        "platform_message_id": fetched_full_gmail_message["id"],
        "contact_id": contact_id,
        "thread_id": fetched_full_gmail_message.get("threadId"),
        "sender_account": "",
        "recipient_accounts": [],
        "cc_accounts": [],
        "subject": "",
        "body_text": "",
        "body_html": "",
        "registered_at": datetime.now().isoformat(),
        "is_read": False,
        "is_from_contact": False,
        "attachments": [],
    }

    # Process internal date for registered_at
    if "internalDate" in fetched_full_gmail_message:
        timestamp_ms = int(fetched_full_gmail_message["internalDate"])
        date_obj = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        supabase_message_data["registered_at"] = date_obj.isoformat()

    # set up headers for below extraction
    headers = {}
    for header in fetched_full_gmail_message.get("payload", {}).get("headers", []):
        name = header.get("name", "").lower()
        value = header.get("value", "")
        headers[name] = value

    # Extract sender
    if "from" in headers:
        from_value = headers["from"]
        if "<" in from_value:
            supabase_message_data["sender_account"] = from_value.split("<")[1].strip(">")
        else:
            supabase_message_data["sender_account"] = from_value

    supabase_message_data["is_from_contact"] = supabase_message_data["sender_account"].lower() != user_email.lower()

    # Extract TO headers for recipient_accounts
    if "to" in headers:
        to_value = headers["to"]
        recipients = to_value.split(",")
        for recipient in recipients:
            recipient = recipient.strip()
            if "<" in recipient:
                email = recipient.split("<")[1].strip(">")
            else:
                email = recipient
            supabase_message_data["recipient_accounts"].append(email)

    # Extract CC headers for cc_accounts
    if "cc" in headers:
        cc_value = headers["cc"]
        cc_recipients = cc_value.split(",")
        for cc_recipient in cc_recipients:
            cc_recipient = cc_recipient.strip()
            if "<" in cc_recipient:
                email = cc_recipient.split("<")[1].strip(">")
            else:
                email = cc_recipient
            supabase_message_data["cc_accounts"].append(email)

    supabase_message_data["subject"] = headers.get("subject", "")

    # Extract message body
    extract_and_process_gmail_body(fetched_full_gmail_message, supabase_message_data)

    # Extract attachments metadata and process download for storage for this specific message
    try:
        attachment_metadata = await process_gmail_attachments_with_storage(fetched_full_gmail_message, contact_id, user_oauth_data, supabase)
        supabase_message_data["attachments"] = attachment_metadata

    except Exception as e:
        print(f"Error processing attachments: {str(e)}")
        # Don't fail the entire message processing if attachments fail
        supabase_message_data["attachments"] = []

    return supabase_message_data
