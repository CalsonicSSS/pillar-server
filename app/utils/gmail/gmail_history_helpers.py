from typing import Dict, Any, List, Set
import traceback
from app.custom_error import UserOauthError
from app.utils.gmail.gmail_msg_helpers import create_gmail_service


def get_gmail_history_delta_and_msg_ids(oauth_data: Dict[str, Any], start_history_id: str) -> Dict[str, Any]:
    """
    Get history of Gmail changes since the provided history ID.

    Args:
        oauth_data: User's Gmail OAuth credentials
        start_history_id: Starting history ID to get changes since

    Returns:
        Dictionary containing history response data with historyId and changes
    """
    print(f"get_gmail_history_delta_and_msg_ids runs (for starting history_id: {start_history_id})")
    try:
        # Create Gmail service
        gmail_service = create_gmail_service(oauth_data)

        # Request parameters
        history_params = {
            "startHistoryId": start_history_id,
            "historyTypes": ["messageAdded", "labelAdded"],  # Only care about new messages and label changes
            "maxResults": 100,  # Adjust as needed
        }

        # Get history: we call this to retrieve the list of changes (history records) that occurred since that startHistoryId.
        history_delta_response = gmail_service.users().history().list(userId="me", **history_params).execute()
        print("history_delta_response:", history_delta_response)

        # Extract message IDs from history
        message_ids = extract_message_ids_from_history(history_delta_response)

        # Handle pagination if necessary
        while "nextPageToken" in history_delta_response and len(message_ids) < 500:  # Limit to 500 messages per notification
            page_token = history_delta_response["nextPageToken"]
            history_params["pageToken"] = page_token

            # Get next page of history
            next_page_response = gmail_service.users().history().list(userId="me", **history_params).execute()

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


def batch_get_gmail_messages(oauth_data: Dict[str, Any], message_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Fetch full Gmail messages in batches using the Gmail API.

    Args:
        oauth_data: User's Gmail OAuth credentials
        message_ids: List of message IDs to fetch

    Returns:
        List of full message objects
    """
    print(f"batch_get_gmail_messages runs for {len(message_ids)} messages")
    try:
        if not message_ids:
            return []

        # Create Gmail service
        gmail_service = create_gmail_service(oauth_data)

        full_messages = []
        batch_size = 50  # Process messages in batches of 50

        # Process messages in batches
        for i in range(0, len(message_ids), batch_size):
            batch_ids = message_ids[i : i + batch_size]
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
            for msg_id in batch_ids:
                batch.add(gmail_service.users().messages().get(userId="me", id=msg_id, format="full"), callback=callback_factory(msg_id))

            # Execute the batch request
            batch.execute()

            # Add results to full_messages
            for msg_id in batch_ids:
                if msg_id in batch_results:
                    full_messages.append(batch_results[msg_id])

            print(f"Processed batch {i//batch_size + 1}, fetched {len(batch_results)} messages")

        return full_messages

    except Exception as e:
        print(f"Error batch getting Gmail messages: {str(e)}")
        print(traceback.format_exc())
        raise UserOauthError(error_detail_message=f"Failed to batch get Gmail messages: {str(e)}")
