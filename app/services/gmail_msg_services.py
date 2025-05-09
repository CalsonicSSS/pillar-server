from typing import Dict, List, Any, Optional
from uuid import UUID
from datetime import datetime
import asyncio
import traceback
from supabase._async.client import AsyncClient
from app.custom_error import DataBaseError, GeneralServerError, UserAuthError
from app.utils.gmail_msg_api_services import fetch_full_gmail_messages_for_contact_in_date_range, transform_fetched_full_gmail_message
from app.services.oauth_credential_services import get_user_oauth_credentials


async def initial_fetch_and_store_messages_from_all_contacts(
    supabase: AsyncClient, channel_id: UUID, contact_ids: List[UUID], start_date: datetime, user_id: UUID
) -> Dict[str, Any]:
    """
    Fetch and store initial messages for a channel's contacts from start_date to now.
    """
    print("initial_fetch_and_store_messages_from_all_contacts function runs")
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

        # Get OAuth credentials from user level
        user_oauth_credentials = await get_user_oauth_credentials(supabase, user_id, "Gmail")
        if not user_oauth_credentials or not user_oauth_credentials.get("oauth_data"):
            raise UserAuthError(error_detail_message="User Gmail OAuth credentials not found")

        oauth_data = user_oauth_credentials["oauth_data"]

        # Get the user's email address from oauth_data
        user_email = oauth_data.get("user_info", {}).get("emailAddress", "")
        if not user_email:
            raise DataBaseError(error_detail_message="User email not found in OAuth data")

        # For each contact, fetch and store messages
        total_messages_fetched_count = 0
        total_messages_saved_count = 0

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

            # Fetch messages for this contact
            print(f"Fetching messages for contact: {contact_identifier}")
            contact_full_gmail_messages_fetched = await fetch_full_gmail_messages_for_contact_in_date_range(
                oauth_data=oauth_data,
                start_date=start_date_str,
                end_date=end_date_str,
                contact_email=contact_identifier,
                max_results=1000,
            )

            total_messages_fetched_count += len(contact_full_gmail_messages_fetched)
            print(f"Found {len(contact_full_gmail_messages_fetched)} messages for contact: {contact_identifier}")

            # Process and store each message
            saved_count = 0
            for full_gmail_message in contact_full_gmail_messages_fetched:
                try:
                    # Process Gmail message
                    transformed_message_data = transform_fetched_full_gmail_message(full_gmail_message, str(channel_id), str(contact_id), user_email)

                    # Check if message already exists
                    existing_stored_message = (
                        await supabase.table("messages")
                        .select("id")
                        .eq("platform_message_id", transformed_message_data["platform_message_id"])
                        .eq("channel_id", str(channel_id))
                        .execute()
                    )

                    if existing_stored_message.data:
                        # Skip existing messages
                        continue

                    # Store message in database
                    result = await supabase.table("messages").insert(transformed_message_data).execute()

                    if result.data:
                        saved_count += 1

                except Exception as e:
                    # Log error but continue processing other messages
                    print(f"Error processing message {full_gmail_message.get('id')}: {str(e)}")
                    print(traceback.format_exc())

            total_messages_saved_count += saved_count
            print(f"Saved {saved_count} messages for contact {contact_identifier}")

            # Small delay between contacts to avoid rate limiting
            if contact_id != contact_ids[-1]:
                await asyncio.sleep(1)

        return {
            "status": "success",
            "total_messages_fetched_count": total_messages_fetched_count,
            "total_messages_saved_count": total_messages_saved_count,
        }

    except (DataBaseError, UserAuthError):
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to fetch and store messages")


async def get_messages_with_filters(supabase: AsyncClient, user_id: UUID, filter_params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Get messages with filtering options using the RPC function.
    """
    print("get_messages_with_filters service function runs")
    try:
        # Call the RPC function with user_id and filter parameters
        result = await supabase.rpc(
            "get_messages_with_filters",
            {
                "user_id_param": str(user_id),
                "channel_id_param": str(filter_params.get("channel_id")) if filter_params.get("channel_id") else None,
                "contact_id_param": str(filter_params.get("contact_id")) if filter_params.get("contact_id") else None,
                "start_date_param": filter_params.get("start_date"),
                "end_date_param": filter_params.get("end_date"),
                "is_read_param": filter_params.get("is_read"),
                "is_from_contact_param": filter_params.get("is_from_contact"),
                "limit_param": filter_params.get("limit", 50),
                "offset_param": filter_params.get("offset", 0),
            },
        ).execute()

        return result.data

    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to retrieve messages")


async def get_message_by_id(supabase: AsyncClient, message_id: UUID, user_id: UUID) -> Dict[str, Any]:
    """
    Get a specific message by ID with user verification.
    """
    print("get_message_by_id service function runs")
    try:
        # Verify message belongs to user's project through channel
        message_verification_result = await supabase.rpc(
            "get_message_with_user_verification", {"message_id_param": str(message_id), "user_id_param": str(user_id)}
        ).execute()

        if not message_verification_result.data:
            raise UserAuthError(error_detail_message="Message not found or access denied")

        return message_verification_result.data[0]

    except UserAuthError:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to retrieve message")


async def mark_message_as_read(supabase: AsyncClient, message_id: UUID, user_id: UUID) -> Dict[str, Any]:
    """
    Mark a message as read with user verification.
    """
    print("mark_message_as_read service function runs")
    try:
        # Verify message belongs to user's project
        await get_message_by_id(supabase, message_id, user_id)

        # Update message read status
        result = await supabase.table("messages").update({"is_read": True}).eq("id", str(message_id)).execute()

        if not result.data:
            raise DataBaseError(error_detail_message="Failed to mark message as read")

        return result.data[0]

    except (DataBaseError, UserAuthError):
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to mark message as read")
