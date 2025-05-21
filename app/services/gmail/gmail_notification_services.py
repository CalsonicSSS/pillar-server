from typing import Dict, Any
import traceback
import json
import base64
from uuid import UUID
from fastapi import Request
from supabase._async.client import AsyncClient
from app.custom_error import GeneralServerError
from app.services.user_oauth_credential_services import get_user_oauth_credentials_by_channel_type, update_user_oauth_credentials_by_channel_type
from app.utils.gmail.gmail_notification_helpers import get_gmail_history_delta_and_msg_ids, batch_get_gmail_messages
from app.utils.gmail.gmail_msg_helpers import transform_fetched_full_gmail_message


# this is the process logic that will be only triggered by each of the Gmail Pub/Sub notification sent by Google
async def process_gmail_pub_sub_notifications(request: Request, supabase: AsyncClient) -> Dict[str, Any]:
    """
    Handle and process Gmail notifications sent by Google Pub/Sub.

    Args:
        request: FastAPI request object containing the Pub/Sub payload
        supabase: Supabase client

    Returns:
        Dictionary with processing results
    """
    print("process_gmail_pub_sub_notifications runs")
    try:
        # Get the raw request body
        pub_sub_notification_request_payload = await request.json()

        # Print for debugging
        print("Received Gmail notification payload:", pub_sub_notification_request_payload)

        # The actual message data is base64 encoded
        if "message" in pub_sub_notification_request_payload and "data" in pub_sub_notification_request_payload["message"]:
            # Decode the base64 data
            message_data_decoded = base64.b64decode(pub_sub_notification_request_payload["message"]["data"]).decode("utf-8")

            # Parse the decoded data as JSON
            pub_sub_notification_message_data = json.loads(message_data_decoded)

            print("gmail pub/sub notification_message_data:", pub_sub_notification_message_data)

            # Extract essential information from the notification
            user_email_address = pub_sub_notification_message_data.get("emailAddress")
            notification_history_id = pub_sub_notification_message_data.get("historyId")

            if not user_email_address or not notification_history_id:
                print("Missing email_address or history_id in notification")
                return {"status": "error", "message": "Missing required gmail notification data"}

            # Find the user by matching the email address in OAuth data for only the Gmail channel through rpc
            user_gmail_oauth_credentials_query_result = await supabase.rpc(
                "get_user_gmail_oauth_by_gmail_address", {"email_address": user_email_address}
            ).execute()

            if not user_gmail_oauth_credentials_query_result.data:
                print(f"No Gmail OAuth credentials found for email address {user_email_address}")
                return {"status": "error", "message": f"No gmail OAuth credentials found for {user_email_address}"}

            target_user_oauth_credentials = user_gmail_oauth_credentials_query_result.data[0]

            user_id = target_user_oauth_credentials["user_id"]

            # Current historyId from our stored credentials
            current_user_gmail_history_id = target_user_oauth_credentials["oauth_data"].get("user_info", {}).get("historyId")

            if not current_user_gmail_history_id:
                print("No historyId found in stored credentials")
                return {"status": "error", "message": "No historyId in credentials"}

            # If the new historyId is the same as our stored one, nothing to do
            if str(current_user_gmail_history_id) == str(notification_history_id):
                print(f"No new changes (historyId unchanged: {notification_history_id})")
                return {"status": "success", "message": "No new changes"}

            # Process the history to find new messages
            history_processing_result = await process_gmail_history_changes(
                supabase, UUID(user_id), user_email_address, current_user_gmail_history_id, target_user_oauth_credentials["oauth_data"]
            )

            return {
                "status": "success",
                "message": "new Gmail pub/sub notification processed successfully",
                "history_processing_result": history_processing_result,
            }

        # If we can't find the message data, log an error
        print("Error: No message data found in notification payload")
        return {"status": "error", "message": "No message data found in notification payload"}

    except Exception as e:
        print(f"Error processing Gmail notification: {str(e)}")
        print(traceback.format_exc())
        # Still return a success response to acknowledge the message to prevent redelivery
        return {"status": "error", "message": f"Error processing notification: {str(e)}"}


# --------------------------------------------------------------------------------------------------------------------------------


async def process_gmail_history_changes(
    supabase: AsyncClient, user_id: UUID, user_email_address: str, start_history_id: str, oauth_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Process Gmail history changes and store new messages.

    Args:
        supabase: Supabase client
        user_id: User ID
        email_address: Gmail email address
        start_history_id: Starting history ID
        oauth_data: OAuth credentials

    Returns:
        Processing results
    """
    print(f"process_gmail_history_changes runs for user: {user_id}, starting from history_id: {start_history_id}")
    try:
        # Get history changes
        history_delta_result = get_gmail_history_delta_and_msg_ids(oauth_data, start_history_id)
        new_history_id = history_delta_result["history_id"]
        message_ids = history_delta_result["message_ids"]

        print(f"Found {len(message_ids)} possible new messages with till new history_id: {new_history_id}")

        if not message_ids:
            # No new messages to process
            # Still update the historyId
            oauth_data["user_info"]["historyId"] = new_history_id
            await update_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail", oauth_data)
            return {"status": "success", "message": "No new messages to process", "history_id": new_history_id, "new_msg_processed_count": 0}

        # Get active projects and their channels for this user
        active_projects_result = await supabase.table("projects").select("id").eq("user_id", str(user_id)).eq("status", "active").execute()

        if not active_projects_result.data:
            print(f"No active projects found for user {user_id}, skipping message processing")
            # Still update the historyId even if no active projects
            oauth_data["user_info"]["historyId"] = new_history_id
            await update_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail", oauth_data)
            return {"status": "success", "message": "No active projects found", "history_id": new_history_id, "new_msg_processed_count": 0}

        active_project_ids = [p["id"] for p in active_projects_result.data]

        # Get all Gmail channels for active projects
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
            oauth_data["user_info"]["historyId"] = new_history_id
            await update_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail", oauth_data)
            return {
                "status": "success",
                "message": "No Gmail channels found in active projects",
                "history_id": new_history_id,
                "new_msg_processed_count": 0,
            }

        # Get all contacts from Gmail channels in active projects
        contacts_result = (
            await supabase.table("contacts")
            .select("id, channel_id, account_identifier")
            .in_("channel_id", [c["id"] for c in channels_result.data])
            .execute()
        )

        if not contacts_result.data:
            print(f"No contacts found for Gmail channels in active projects of user {user_id}")
            # Still update the historyId even if no contacts
            oauth_data["user_info"]["historyId"] = new_history_id
            await update_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail", oauth_data)
            return {"status": "success", "message": "No contacts found in Gmail channels", "history_id": new_history_id, "new_msg_processed_count": 0}

        # Organize contacts by channel
        contacts_by_channel = {}
        for contact in contacts_result.data:
            channel_id = contact["channel_id"]
            if channel_id not in contacts_by_channel:
                contacts_by_channel[channel_id] = []
            contacts_by_channel[channel_id].append(contact)

        # Batch get all the messages
        full_messages = batch_get_gmail_messages(oauth_data, message_ids)

        if not full_messages:
            print(f"No full messages retrieved for user {user_id}")
            # Still update the historyId even if no messages retrieved
            oauth_data["user_info"]["historyId"] = new_history_id
            await update_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail", oauth_data)
            return {"status": "success", "message": "No messages retrieved", "history_id": new_history_id, "new_msg_processed_count": 0}

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
                        await supabase.table("messages").select("id").eq("platform_message_id", message_id).eq("channel_id", channel_id).execute()
                    )

                    if existing_message.data:
                        print(f"Message {message_id} already exists, skipping")
                        continue

                    # Transform and store the message
                    transformed_message = transform_fetched_full_gmail_message(full_message, channel_id, contact_id, user_email_address)

                    # Insert the message
                    message_result = await supabase.table("messages").insert(transformed_message).execute()

                    if message_result.data:
                        messages_saved += 1
                        print(f"Saved message {message_id} for contact {contact_id} in channel {channel_id}")

        # Update historyId after processing
        oauth_data["user_info"]["historyId"] = new_history_id
        await update_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail", oauth_data)

        return {
            "status": "success",
            "message": f"Successfully processed Gmail history changes",
            "history_id": new_history_id,
            "new_msg_processed_count": messages_saved,
            "total_messages_found": len(full_messages),
        }

    except Exception as e:
        print(f"Error processing Gmail history changes: {str(e)}")
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message=f"Failed to process Gmail history changes: {str(e)}")
