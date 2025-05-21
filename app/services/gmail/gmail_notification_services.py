from typing import Dict, Any
import traceback
import json
import base64
from uuid import UUID
from fastapi import Request
from supabase._async.client import AsyncClient
from app.utils.gmail.gmail_notification_helpers import process_gmail_history_changes


# this is the process logic that will be only triggered by each of the Gmail Pub/Sub notification http request sent by Google
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

            # All the Processing happens here:
            # 1. get the new history id with all the delta messages occurred
            # 2. filtering process to only user's gmail-type contacts under all active project
            # 3. fetch full messages
            # 4. filter which message should be saved in db for only the "contacts" from "gmail channel" under "active project" for this user
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
