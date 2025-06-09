from typing import Dict, Any, List, Set
import traceback
from app.custom_error import UserOauthError
from app.utils.gmail.gmail_api_service import create_gmail_service
from supabase._async.client import AsyncClient
from uuid import UUID


# this is to get the delta of msg ids from the specified current hist_id as starting point to the time point when history list api is called
async def get_gmail_history_delta_msg_ids(
    user_oauth_data: Dict[str, Any], current_user_gmail_history_id: str, max_results: int, supabase: AsyncClient, user_id: UUID
) -> Dict[str, Any]:
    """
    Get history of Gmail changes since the provided history ID.

    Args:
        user_oauth_data: User's Gmail OAuth credentials
        current_user_gmail_history_id: Starting history ID to get changes since
        max_results: Maximum number of messages to process

    Returns:
        Dictionary containing history response data with historyId and changes
    """
    print(f"get_gmail_history_delta_msg_ids runs (for starting history_id: {current_user_gmail_history_id})")
    try:
        # Create Gmail service
        gmail_service = await create_gmail_service(user_oauth_data, supabase, user_id)

        # Request parameters
        history_params = {
            "startHistoryId": current_user_gmail_history_id,
            # "historyTypes": ["messageAdded"],  # messageAdded alone Captures Both Directions INBOX / SENT (matching watch api config)
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
