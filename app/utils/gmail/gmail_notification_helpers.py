from typing import Dict, Any, List, Set
import traceback
from app.custom_error import UserOauthError
from app.utils.gmail.gmail_msg_helpers import create_gmail_service
from app.services.user_oauth_credential_services import update_user_oauth_credentials_by_channel_type
from uuid import UUID
from supabase._async.client import AsyncClient
from app.custom_error import GeneralServerError
from app.utils.gmail.gmail_msg_helpers import transform_fetched_full_gmail_message, batch_get_gmail_full_messages


def get_gmail_history_delta_msg_ids(user_oauth_data: Dict[str, Any], current_user_gmail_history_id: str, max_results: int) -> Dict[str, Any]:
    """
    Get history of Gmail changes since the provided history ID.

    Args:
        user_oauth_data: User's Gmail OAuth credentials
        current_user_gmail_history_id: Starting history ID to get changes since

    Returns:
        Dictionary containing history response data with historyId and changes
    """
    print(f"get_gmail_history_delta_msg_ids runs (for starting history_id: {current_user_gmail_history_id})")
    try:
        # Create Gmail service
        gmail_service = create_gmail_service(user_oauth_data)

        # Request parameters
        history_params = {
            "startHistoryId": current_user_gmail_history_id,
            "historyTypes": ["messageAdded", "labelAdded"],  # Only care about new messages and label changes
        }

        # Get history: we call this to retrieve the list of changes (history records) that occurred since that startHistoryId.
        history_delta_response = gmail_service.users().history().list(userId="me", **history_params, maxResults=min(max_results, 100)).execute()
        print("history_delta_response:", history_delta_response)

        # Extract message IDs from history
        message_ids = extract_message_ids_from_history(history_delta_response)

        # Handle pagination if necessary
        while "nextPageToken" in history_delta_response and len(message_ids) < max_results:
            page_token = history_delta_response["nextPageToken"]
            history_params["pageToken"] = page_token

            # Get next page of history
            next_page_response = (
                gmail_service.users().history().list(userId="me", **history_params, maxResults=min(max_results - len(message_ids), 100)).execute()
            )

            # Extract more message IDs
            message_ids.update(extract_message_ids_from_history(next_page_response))

            # Update history response for next iteration
            history_delta_response.update(next_page_response)

            # Remove nextPageToken if it's the last page
            if "nextPageToken" not in next_page_response:
                history_delta_response.pop("nextPageToken", None)

        return {
            "history_id": history_delta_response.get("historyId"),
            "message_ids": list(message_ids),
        }

    except Exception as e:
        print(f"Error getting Gmail history: {str(e)}")
        print(traceback.format_exc())
        raise UserOauthError(error_detail_message=f"Failed to get Gmail history: {str(e)}")


# -----------------------------------------------------------------------------------------------------------------------


def extract_message_ids_from_history(history_response: Dict[str, Any]) -> Set[str]:
    """
    Extract unique message IDs from a Gmail history response.

    Args:
        history_response: Response from Gmail History API

    Returns:
        Set of unique message IDs
    """
    message_ids = set()

    # Process history records
    history_records = history_response.get("history", [])

    for record in history_records:
        # Extract from messageAdded
        for message_added in record.get("messagesAdded", []):
            message_id = message_added.get("message", {}).get("id")
            if message_id:
                message_ids.add(message_id)

        # Extract from labelsAdded - might include newly received messages
        for label_added in record.get("labelsAdded", []):
            message_id = label_added.get("message", {}).get("id")
            if message_id:
                message_ids.add(message_id)

    # the .add method of a set will not add duplicates, so the message_ids set will only contain unique message IDs
    return message_ids


# -----------------------------------------------------------------------------------------------------------------------


# All the Processing happens here:
# 1. get the new history id with all the delta messages occurred
# 2. filtering process to only user's gmail-type contacts under all active project
# 3. fetch all full messages through batch
# 4. filter which message should be saved in db for only the "contacts" from "gmail channel" under "active project" for this user
async def process_gmail_history_changes(
    supabase: AsyncClient, user_id: UUID, user_email_address: str, current_user_gmail_history_id: str, user_oauth_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Process Gmail history changes and store new messages.

    Args:
        supabase: Supabase client
        user_id: User ID
        email_address: Gmail email address
        current_user_gmail_history_id: Starting history ID
        user_oauth_data: OAuth credentials

    Returns:
        Processing results
    """
    print(f"process_gmail_history_changes runs for user: {user_id}, starting from history_id: {current_user_gmail_history_id}")
    try:
        # Get history changes
        history_delta_result = get_gmail_history_delta_msg_ids(user_oauth_data, current_user_gmail_history_id)
        new_history_id = history_delta_result["history_id"]
        delta_message_ids = history_delta_result["message_ids"]

        print(f"Found {len(delta_message_ids)} possible new messages with till new history_id: {new_history_id}")

        if not delta_message_ids:
            # No new messages to process
            # Still update the historyId
            user_oauth_data["user_info"]["historyId"] = new_history_id
            await update_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail", user_oauth_data)
            return {"status": "success", "status_message": "No new messages to process", "history_id": new_history_id, "new_msg_saved": 0}

        # filter 1: Get active projects and their channels for this user
        active_projects_result = await supabase.table("projects").select("id").eq("user_id", str(user_id)).eq("status", "active").execute()

        if not active_projects_result.data:
            print(f"No active projects found for user {user_id}, skipping message processing")
            # Still update the historyId even if no active projects
            user_oauth_data["user_info"]["historyId"] = new_history_id
            await update_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail", user_oauth_data)
            return {"status": "success", "status_message": "No active projects found", "history_id": new_history_id, "new_msg_saved": 0}

        active_project_ids = [p["id"] for p in active_projects_result.data]

        # filter 2: Get all GMAIL TYPE channels for all ACTIVE projects from THIS USER
        channels_result = (
            await supabase.table("channels")
            .select("id, project_id")
            .in_("project_id", active_project_ids)
            .eq("channel_type", "gmail")
            .eq("is_connected", True)
            .execute()
        )

        if not channels_result.data:
            print(f"No Gmail channels found for active projects of user {user_id}")
            # Still update the historyId even if no Gmail channels
            user_oauth_data["user_info"]["historyId"] = new_history_id
            await update_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail", user_oauth_data)
            return {
                "status": "success",
                "status_message": "No Gmail channels found in active projects",
                "history_id": new_history_id,
                "new_msg_saved": 0,
            }

        # filter 3: Get all contacts from Gmail channels
        contacts_result = (
            await supabase.table("contacts")
            .select("id, channel_id, account_identifier")
            .in_("channel_id", [c["id"] for c in channels_result.data])
            .execute()
        )

        if not contacts_result.data:
            print(f"No contacts found for Gmail channels in active projects of user {user_id}")
            # Still update the historyId even if no contacts
            user_oauth_data["user_info"]["historyId"] = new_history_id
            await update_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail", user_oauth_data)
            return {"status": "success", "status_message": "No contacts found in Gmail channels", "history_id": new_history_id, "new_msg_saved": 0}

        # Organize contacts by channel
        contacts_by_channel = {}
        for contact in contacts_result.data:
            channel_id = contact["channel_id"]
            if channel_id not in contacts_by_channel:
                contacts_by_channel[channel_id] = []
            contacts_by_channel[channel_id].append(contact)

        # Batch get all the full messages
        # need to use full message to compare if any of these messaage are from target contact(s) within all gmail channels under active project for this user
        full_messages = batch_get_gmail_full_messages(user_oauth_data, delta_message_ids)

        if not full_messages:
            print(f"No full messages retrieved for user {user_id}")
            # Still update the historyId even if no messages retrieved
            user_oauth_data["user_info"]["historyId"] = new_history_id
            await update_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail", user_oauth_data)
            return {"status": "success", "status_message": "No full messages retrieved", "history_id": new_history_id, "new_msg_saved": 0}

        # Process and store relevant messages
        messages_saved = 0

        for full_message in full_messages:
            # Extract email addresses from the message
            headers = {}
            for header in full_message.get("payload", {}).get("headers", []):
                name = header.get("name", "").lower()
                value = header.get("value", "")
                headers[name] = value

            # Get From email
            from_email = None
            if "from" in headers:
                from_value = headers["from"]
                if "<" in from_value:
                    from_email = from_value.split("<")[1].strip(">").lower()
                else:
                    from_email = from_value.lower()

            # Get To emails
            to_emails = []
            if "to" in headers:
                to_value = headers["to"]
                recipients = to_value.split(",")
                for recipient in recipients:
                    recipient = recipient.strip()
                    if "<" in recipient:
                        email = recipient.split("<")[1].strip(">").lower()
                    else:
                        email = recipient.lower()
                    to_emails.append(email)

            # Check if message is relevant (involves any of our contacts)
            for channel_id, contacts in contacts_by_channel.items():
                contact_emails = [c["account_identifier"].lower() for c in contacts]

                # Check if any contact is involved (as sender or recipient)
                relevant_contact = None
                if from_email and from_email in contact_emails:
                    # Message FROM contact TO user
                    relevant_contact = next((c for c in contacts if c["account_identifier"].lower() == from_email), None)
                elif user_email_address.lower() == from_email and any(
                    email in contact_emails for email in to_emails
                ):  # Message FROM user TO contact (and possibly others)
                    for to_email in to_emails:
                        if to_email in contact_emails:
                            relevant_contact = next((c for c in contacts if c["account_identifier"].lower() == to_email), None)
                            break

                if relevant_contact:
                    # This message involves a contact we care about
                    contact_id = relevant_contact["id"]
                    message_id = full_message["id"]

                    # Check if message already exists in our database
                    existing_message = (
                        await supabase.table("messages")
                        .select("id")
                        .eq("platform_message_id", message_id)
                        .eq("contact_id", str(contact_id))
                        .execute()
                    )

                    if existing_message.data:
                        print(f"Message {message_id} already exists, skipping")
                        continue

                    # Transform and store the message
                    transformed_message = transform_fetched_full_gmail_message(full_message, contact_id, user_email_address)

                    # Insert the message
                    result = await supabase.table("messages").insert(transformed_message).execute()

                    if result.data:
                        messages_saved += 1
                        print(f"Saved message {message_id} for contact {contact_id} in channel {channel_id}")

        # Update historyId after processing
        user_oauth_data["user_info"]["historyId"] = new_history_id
        await update_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail", user_oauth_data)

        return {
            "status": "success",
            "status_message": f"Successfully processed Gmail history changes",
            "history_id": new_history_id,
            "new_msg_saved": messages_saved,
        }

    except Exception as e:
        print(f"Error processing Gmail history changes: {str(e)}")
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message=f"Failed to process Gmail history changes: {str(e)}")
