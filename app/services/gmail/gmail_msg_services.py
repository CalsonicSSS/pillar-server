from typing import Dict, List, Any, Optional
from uuid import UUID
from datetime import datetime
import asyncio
import traceback
from supabase._async.client import AsyncClient
from app.custom_error import DataBaseError, GeneralServerError, UserAuthError, UserOauthError
from app.utils.gmail.gmail_msg_helpers import (
    fetch_gmail_msg_ids_for_contact_in_date_range,
    transform_fetched_full_gmail_message,
    batch_get_gmail_full_messages,
)
from app.services.user_oauth_credential_services import get_user_oauth_credentials_by_channel_type


# this function will be run whenever a new contact is added by user in the frontend
# this works either for initial project creation or dynamically when a new contact(s) is added
# front end will only send the newly added contact(s) id to this function EACH TIME (no previous added contact ids)
async def fetch_and_store_gmail_messages_from_all_contacts(
    supabase: AsyncClient, channel_id: UUID, contact_ids: List[UUID], start_date: datetime, user_id: UUID
) -> Dict[str, Any]:
    """
    Fetch and store initial messages for a channel's contacts from start_date to now.
    """
    print("fetch_and_store_gmail_messages_from_all_contacts function runs")
    try:
        # Verify channel belongs to user's project
        channel_verification_result = await supabase.rpc(
            "get_channel_with_user_verification", {"channel_id_param": str(channel_id), "user_id_param": str(user_id)}
        ).execute()

        if not channel_verification_result.data:
            raise UserAuthError(error_detail_message="Channel not found or access denied")

        # Get channel data to check if it's connected
        channel_data = channel_verification_result.data[0]
        if not channel_data.get("is_connected", False):
            raise UserAuthError(error_detail_message="Channel not connected")

        # Get gmail OAuth credentials from user level
        user_gmail_credentials = await get_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail")
        if not user_gmail_credentials or not user_gmail_credentials.get("oauth_data"):
            raise UserAuthError(error_detail_message="User Gmail OAuth credentials not found")

        user_gmail_oauth_data = user_gmail_credentials["oauth_data"]
        print("user_gmail_oauth_data:", user_gmail_oauth_data)

        # Get the user's email address from oauth_data
        user_gmail = user_gmail_oauth_data.get("user_info", {}).get("emailAddress", "")
        if not user_gmail:
            raise DataBaseError(error_detail_message="User email not found in OAuth data")

        for contact_id in contact_ids:
            # Get contact details
            contact_result = await supabase.table("contacts").select("*").eq("id", str(contact_id)).execute()

            if not contact_result.data:
                print(f"Contact {contact_id} not found, skipping")
                continue

            contact = contact_result.data[0]
            contact_identifier = contact.get("account_identifier")

            if not contact_identifier:
                print(f"Contact {contact_id} has no identifier, skipping")
                continue

            # Format dates for Gmail API (YYYY/MM/DD format)
            start_date_str = start_date.strftime("%Y/%m/%d")
            end_date_str = datetime.now()

            # Fetch all message ids for this contact within the date range
            print(f"Fetching messages for contact: {contact_identifier}")
            contact_msg_ids = fetch_gmail_msg_ids_for_contact_in_date_range(
                oauth_data=user_gmail_oauth_data,
                start_date=start_date_str,
                end_date=end_date_str,
                contact_email=contact_identifier,
                max_results=1000,
            )

            # batch get full messages for this contact
            contact_full_msgs = batch_get_gmail_full_messages(oauth_data=user_gmail_oauth_data, message_ids=contact_msg_ids)

            print(f"Found {len(contact_full_msgs)} full messages for contact: {contact_identifier}")

            # Process and store each message
            total_messages_saved_count = 0
            saved_count = 0

            for contact_full_msg in contact_full_msgs:
                try:
                    # Check if message already exists
                    existing_message = (
                        await supabase.table("messages")
                        .select("id")
                        .eq("platform_message_id", contact_full_msg["id"])
                        .eq("contact_id", str(contact_id))
                        .execute()
                    )

                    if existing_message.data:
                        print(f"Message {contact_full_msg['id']} already exists, skipping")
                        continue

                    # Process Gmail message
                    transformed_message = transform_fetched_full_gmail_message(contact_full_msg, str(contact_id), user_gmail)

                    # Store message in database
                    result = await supabase.table("messages").insert(transformed_message).execute()

                    if result.data:
                        saved_count += 1

                except Exception as e:
                    # Log error but continue processing other messages
                    print(f"Error processing message {contact_full_msg.get('id')}: {str(e)}")
                    print(traceback.format_exc())

            total_messages_saved_count += saved_count
            print(f"Saved {saved_count} messages for contact {contact_identifier}")

            # Small delay between contacts to avoid rate limiting
            if contact_id != contact_ids[-1]:
                await asyncio.sleep(0.5)

        return {
            "status": "success",
            "total_messages_fetched_count": len(contact_full_msgs),
            "total_messages_saved_count": total_messages_saved_count,
        }

    except (DataBaseError, UserAuthError, UserOauthError):
        raise

    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to fetch and store gmail messages")
