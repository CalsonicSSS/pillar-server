from typing import Dict, Any
import traceback
import json
import base64
from uuid import UUID
from fastapi import Request
from supabase._async.client import AsyncClient
from app.utils.gmail.gmail_notification_helpers import get_gmail_history_delta_msg_ids, is_message_in_final_state
from app.utils.gmail.gmail_msg_helpers import transform_and_process_fetched_full_gmail_message_with_attachments, batch_get_gmail_full_messages
from app.services.user_oauth_credential_services import update_user_oauth_credentials_by_channel_type


# this is the process logic that will be only triggered by each of the Gmail Pub/Sub notification http request sent by Google
# particularly request is sent by the specific Subscriptions setup on GCP within the pub/sub system
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

            # Find the specific user (whom) by matching the email address in OAuth data for only the Gmail channel through rpc
            user_gmail_oauth_credentials_query_result = await supabase.rpc(
                "get_user_gmail_oauth_by_gmail_address", {"email_address": user_email_address}
            ).execute()

            if not user_gmail_oauth_credentials_query_result.data:
                print(f"No Gmail OAuth credentials found for email address {user_email_address}")
                return {"status": "error", "message": f"No gmail OAuth credentials found for {user_email_address}"}

            user_gmail_credentials = user_gmail_oauth_credentials_query_result.data[0]

            # get the user_id from the oauth credentials
            user_id = user_gmail_credentials["user_id"]

            # Current historyId from our stored credentials
            current_user_gmail_history_id = user_gmail_credentials["oauth_data"].get("user_info", {}).get("historyId")

            if not current_user_gmail_history_id:
                print("No historyId found in stored credentials")
                return {"status": "error", "message": "No historyId in credentials"}

            # If the new historyId is the same as our stored one, nothing to do
            if str(current_user_gmail_history_id) == str(notification_history_id):
                print(f"No new changes (historyId unchanged: {notification_history_id})")
                return {"status": "success", "message": "No new changes"}

            # All the Processing happens here:
            # 1. get the new history id with all the delta messages occurred
            # 2. filtering process to only user's gmail-type contacts under all active project
            # 3. fetch full messages
            # 4. filter which message should be saved in db for only the "contacts" from "gmail channel" under "active project" for this user
            # 5. transform and process the message with attachments

            print(f"Processing Gmail history changes for user: {user_id}, starting from history_id: {current_user_gmail_history_id}")

            # Get history changes
            # all msg id fetched from "get_gmail_history_delta_msg_ids" can potential from all possible contacts from user gmail channel
            # so later we will need to filter out which messages are relevant to the user based on the only the chosen existing contacts
            history_delta_result = await get_gmail_history_delta_msg_ids(
                user_gmail_credentials["oauth_data"], current_user_gmail_history_id, 1000, supabase, UUID(user_id)
            )
            new_history_id = history_delta_result["history_id"]
            delta_message_ids = history_delta_result["message_ids"]

            print(f"Found {len(delta_message_ids)} possible new messages with till new history_id: {new_history_id}")

            if not delta_message_ids:
                # No new messages to process
                # Still update the historyId
                user_gmail_credentials["oauth_data"]["user_info"]["historyId"] = new_history_id
                await update_user_oauth_credentials_by_channel_type(supabase, UUID(user_id), "gmail", user_gmail_credentials["oauth_data"])
                return {"status": "success", "message": "No new messages to process", "history_id": new_history_id, "new_msg_saved": 0}

            # filter 1: Get active projects and their channels for this user
            active_projects_result = await supabase.table("projects").select("id").eq("user_id", str(user_id)).eq("status", "active").execute()

            if not active_projects_result.data:
                print(f"No active projects found for user {user_id}, skipping message processing")
                # Still update the historyId even if no active projects
                user_gmail_credentials["oauth_data"]["user_info"]["historyId"] = new_history_id
                await update_user_oauth_credentials_by_channel_type(supabase, UUID(user_id), "gmail", user_gmail_credentials["oauth_data"])
                return {"status": "success", "message": "No active projects found", "history_id": new_history_id, "new_msg_saved": 0}

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
                user_gmail_credentials["oauth_data"]["user_info"]["historyId"] = new_history_id
                await update_user_oauth_credentials_by_channel_type(supabase, UUID(user_id), "gmail", user_gmail_credentials["oauth_data"])
                return {
                    "status": "success",
                    "message": "No Gmail channels found in active projects",
                    "history_id": new_history_id,
                    "new_msg_saved": 0,
                }

            # filter 3: Get all contacts from ALL Gmail channel type only for all ACTIVE projects from THIS USER (this is the final filter we are looking for)
            contacts_result = (
                await supabase.table("contacts")
                .select("id, channel_id, account_identifier")
                .in_("channel_id", [c["id"] for c in channels_result.data])
                .execute()
            )

            if not contacts_result.data:
                print(f"No contacts found for Gmail channels in active projects of user {user_id}")
                # Still update the historyId even if no contacts
                user_gmail_credentials["oauth_data"]["user_info"]["historyId"] = new_history_id
                await update_user_oauth_credentials_by_channel_type(supabase, UUID(user_id), "gmail", user_gmail_credentials["oauth_data"])
                return {"status": "success", "message": "No contacts found in Gmail channels", "history_id": new_history_id, "new_msg_saved": 0}

            # Organize contacts by channel
            contacts_by_channel = {}
            for contact in contacts_result.data:
                channel_id = contact["channel_id"]
                if channel_id not in contacts_by_channel:
                    contacts_by_channel[channel_id] = []
                contacts_by_channel[channel_id].append(contact)

            # Batch get all the full messages
            # need to use full message to compare if any of these messaage are from target contact(s) within all gmail channels under active project for this user
            full_messages = await batch_get_gmail_full_messages(user_gmail_credentials["oauth_data"], delta_message_ids, supabase, UUID(user_id))

            if not full_messages:
                print(f"No full messages retrieved for user {user_id}")
                # Still update the historyId even if no messages retrieved
                user_gmail_credentials["oauth_data"]["user_info"]["historyId"] = new_history_id
                await update_user_oauth_credentials_by_channel_type(supabase, UUID(user_id), "gmail", user_gmail_credentials["oauth_data"])
                return {"status": "success", "message": "No full messages retrieved", "history_id": new_history_id, "new_msg_saved": 0}

            # Process and store relevant messages
            messages_saved = 0

            # we need to analyze each full message to see if any of the contacts are involved
            # if then, we will process, transform, and save the message to the database with attachments
            for full_message in full_messages:
                # Check if message is in truly final state
                message_labels = full_message.get("labelIds", [])

                # Filter out messages that aren't in final state
                if not is_message_in_final_state(message_labels):
                    print(f"Skipping message {full_message['id']} - not in final state")
                    continue

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

                # UPDATED: Check if message is relevant for ANY tracked contact
                # This now handles BOTH directions clearly:
                # 1. RECEIVED: Contact sends TO user
                # 2. SENT: User sends TO contact
                for channel_id, contacts in contacts_by_channel.items():
                    contact_emails = [c["account_identifier"].lower() for c in contacts]

                    relevant_contact = None

                    # CASE 1: Message FROM tracked contact TO user (RECEIVED MESSAGE)
                    if from_email and from_email in contact_emails:
                        relevant_contact = next((c for c in contacts if c["account_identifier"].lower() == from_email), None)
                        print(f"Found RECEIVED message from contact: {from_email}")

                    # CASE 2: Message FROM user TO tracked contact (SENT MESSAGE)
                    elif user_email_address.lower() == from_email:
                        # User sent this message, check if any tracked contact is in TO field
                        for to_email in to_emails:
                            if to_email in contact_emails:
                                relevant_contact = next((c for c in contacts if c["account_identifier"].lower() == to_email), None)
                                print(f"Found SENT message to contact: {to_email}")
                                break

                    if relevant_contact:
                        # This message involves a tracked contact (either direction)
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

                        # Transform and store the message with attachments
                        transformed_message = await transform_and_process_fetched_full_gmail_message_with_attachments(
                            full_message, contact_id, user_email_address, user_gmail_credentials["oauth_data"], supabase, UUID(user_id)
                        )

                        # Insert the message
                        result = await supabase.table("messages").insert(transformed_message).execute()

                        if result.data:
                            messages_saved += 1
                            print(
                                f"Saved message {message_id} for contact {contact_id} in channel {channel_id} (Direction: {'RECEIVED' if from_email in contact_emails else 'SENT'})"
                            )

            # Update historyId after processing
            user_gmail_credentials["oauth_data"]["user_info"]["historyId"] = new_history_id
            await update_user_oauth_credentials_by_channel_type(supabase, UUID(user_id), "gmail", user_gmail_credentials["oauth_data"])

            return {
                "status": "success",
                "message": "Gmail pub/sub notification processed successfully",
                "history_id": new_history_id,
                "new_msg_saved": messages_saved,
            }

        # If we can't find the ["message"]["data"] at all within the notification request paylad, log an error
        print("Error: No message data found in notification payload")
        return {"status": "error", "message": "No message data found in notification payload"}

    except Exception as e:
        print(f"Error processing Gmail notification: {str(e)}")
        print(traceback.format_exc())
        # Still return a success response to acknowledge the message to prevent redelivery
        return {"status": "error", "message": f"Error processing notification: {str(e)}"}
