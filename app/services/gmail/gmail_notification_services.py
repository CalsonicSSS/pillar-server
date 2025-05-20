from typing import Dict, Any
import traceback
import json
import base64
from uuid import UUID
from fastapi import Request
from supabase._async.client import AsyncClient
from app.custom_error import GeneralServerError
from app.services.user_oauth_credential_services import get_user_oauth_credentials_by_channel_type, update_user_oauth_credentials_by_channel_type


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
        request_body_payload = await request.json()

        # Print for debugging
        print("Received Gmail notification payload:", request_body_payload)

        # The actual message data is base64 encoded
        if "message" in request_body_payload and "data" in request_body_payload["message"]:
            # Decode the base64 data
            message_data_decoded = base64.b64decode(request_body_payload["message"]["data"]).decode("utf-8")

            # Parse the decoded data as JSON
            notification_message_data = json.loads(message_data_decoded)

            print("notification_message_data:", notification_message_data)

            # Extract essential information from the notification
            email_address = notification_message_data.get("emailAddress")
            new_history_id = notification_message_data.get("historyId")

            if not email_address or not new_history_id:
                print("Missing email_address or history_id in notification")
                return {"status": "error", "message": "Missing required gmail notification data"}

            # Find the user by matching the email address in OAuth data for only the Gmail channel through rpc
            user_gmail_oauth_credentials_query_result = await supabase.rpc(
                "get_user_gmail_oauth_by_gmail_address", {"email_address": email_address}
            ).execute()

            if not user_gmail_oauth_credentials_query_result.data:
                print(f"No Gmail OAuth credentials found for email address {email_address}")
                return {"status": "error", "message": f"No gmail OAuth credentials found for {email_address}"}

            target_user_oauth_credentials = user_gmail_oauth_credentials_query_result.data[0]

            user_id = target_user_oauth_credentials["user_id"]

            # Current historyId from our stored credentials
            current_user_gmail_history_id = target_user_oauth_credentials["oauth_data"].get("user_info", {}).get("historyId")

            if not current_user_gmail_history_id:
                print("No historyId found in stored credentials")
                return {"status": "error", "message": "No historyId in credentials"}

            # If the new historyId is the same as our stored one, nothing to do
            if str(current_user_gmail_history_id) == str(new_history_id):
                print(f"No new changes (historyId unchanged: {new_history_id})")
                return {"status": "success", "message": "No new changes"}

            # Update the historyId in our database using the specific update function
            oauth_data = target_user_oauth_credentials["oauth_data"]
            oauth_data["user_info"]["historyId"] = new_history_id

            await update_user_oauth_credentials_by_channel_type(supabase, UUID(user_id), "gmail", oauth_data)

            print(f"Updated historyId from {current_user_gmail_history_id} to {new_history_id} for user {user_id}")

            # Process the history to find new messages
            # We'll implement this in the next step

            return {
                "status": "success",
                "message": "Notification processed and historyId updated",
                "user_id": user_id,
                "email_address": email_address,
                "old_history_id": current_user_gmail_history_id,
                "new_history_id": new_history_id,
            }

        # If we can't find the message data, log an error
        print("Error: No message data found in notification payload")
        return {"status": "error", "message": "No message data found in notification payload"}

    except Exception as e:
        print(f"Error processing Gmail notification: {str(e)}")
        print(traceback.format_exc())
        # Still return a success response to acknowledge the message to prevent redelivery
        return {"status": "error", "message": f"Error processing notification: {str(e)}"}
