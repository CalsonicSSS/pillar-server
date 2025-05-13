from typing import List, Dict, Any
from datetime import datetime
import traceback
from app.utils.llm.claude_client import claude_message_api
from app.custom_error import GeneralServerError


def create_summarization_system_prompt() -> str:
    system_prompt = """You are a professional executive assistant for accounting professionals (the user). 
    Your role is to summarize user ("accounting professionals") client communications efficiently, focusing on what matters most to accounting work and based on all the messages provided.
    Provide only the summary in bullet point format, with no additional text or commentary."""
    return system_prompt


def create_summarization_user_prompt(date_range_description: str, summary_type: str = "daily") -> str:
    time_scope = "day" if summary_type == "daily" else "week"
    user_prompt = f"""Please summarize the communications from {date_range_description} into a concise summary.

Task Guidelines:
1. Carefully go through all the provided communication messages, and summarize them in bullet points. 
2. Focus your summary on key information, insights, and possible actions items to be highlighted in your response based on all provided communication messages.
3. There could be messages between my clients and I that are unrelated to accounting work and not important to summarize, Use your judgement to focus on the messages that are relevant to work only.
4. pay attention if I have provided a non-empty "project context" for this project as additional context. Use them accordingly in your response. 

Response Format:
1. Format your entire response as bullet points only, with each point on a new line starting with "•"
2. Make sure each bullet point is concise and to the point.
3. Use professional, direct language
4. If there are no communications message or entire provide communication messages are non-work related, your only bullet point should be "• No significant summary during this {time_scope}."
"""

    return user_prompt


def format_all_message_contents(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    # If no messages:
    if not messages:
        return {"type": "text", "text": "There were no messages in this time period."}

    all_message_contents = ""
    all_message_contents += "Here are all the communication messages to summarize:\n\n"

    # Format each message
    for msg in messages:
        # Common fields
        date = msg.get("registered_at", "Unknown date")

        # Try to get a human-readable date
        if isinstance(date, str):
            try:
                date_obj = datetime.fromisoformat(date.replace("Z", "+00:00"))
                date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass  # Keep as is if parsing fails

        all_message_contents += f"Date: {date}\n"

        channel_type = msg.get("channel_type", "Unknown message type")
        all_message_contents += f"Message Channel type: {channel_type}\n"

        sender = msg.get("sender_account", "Unknown")
        recipients = ", ".join(msg.get("recipient_accounts", ["Unknown"]))
        subject = msg.get("subject", "No subject")

        all_message_contents += f"From: {sender}\n"
        all_message_contents += f"To: {recipients}\n"
        all_message_contents += f"Subject: {subject}\n"

        # Use text body if available, otherwise HTML
        body = msg.get("body_text", msg.get("body_html", "No content"))

        # Truncate very long bodies
        if len(body) > 2000:
            body = body[:2000] + "... [truncated]"

        all_message_contents += f"Message:\n{body}\n\n"
        all_message_contents += "-" * 40 + "\n\n"

    return {"type": "text", "text": all_message_contents}


async def summarize_timeline_recap_element(
    messages: List[Dict[str, Any]], date_range_description: str, summary_type: str = "daily", project_context: str = ""
) -> str:
    """
    Summarize messages in a given date range using Claude.

    Args:
        messages: List of messages to summarize
        date_range_description: Description of the date range (e.g., "May 10-11, 2025")
        summary_type: Either "daily" or "weekly"
        project_context: Optional context about the project

    Returns:
        Summary string in bullet point format
    """
    try:
        if project_context:
            project_context_content = f"Given project Context:\n\n {project_context}"

        # Create system prompt
        system_prompt = create_summarization_system_prompt(summary_type)

        # Format messages for Claude
        full_message_content = format_all_message_contents(messages)

        # Add the task instruction to the last message
        user_prompt = create_summarization_user_prompt(date_range_description, summary_type)

        formatted_messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": project_context_content},
                    {"type": "text", "text": "below is all the communication messages to summarize:"},
                    full_message_content,
                    {"type": "text", "text": user_prompt},
                ],
            },
        ]

        # Get response from Claude
        llm_response = await claude_message_api(
            system_prompt=system_prompt,
            messages=formatted_messages,
            temperature=0.3,  # Lower temperature for more consistent summaries
            max_tokens=1500,  # Limit response to avoid verbosity
        )

        # Extract the summary text
        summary = llm_response.content[0].text.strip()

        return summary

    except Exception as e:
        print(f"Error in summarize_messages_in_date_range: {str(e)}")
        print(traceback.format_exc())
        raise GeneralServerError("An error occurred while generating the summary.")


async def generate_daily_summary(start_date: datetime, messages: List[Dict[str, Any]], project_context: str = "") -> str:
    """
    Generate a daily summary for the given date range.
    """
    # Format date for description
    date_str = start_date.strftime("%B %d, %Y")

    return await summarize_timeline_recap_element(
        messages=messages, date_range_description=date_str, summary_type="daily", project_context=project_context
    )


async def generate_weekly_summary(start_date: datetime, end_date: datetime, messages: List[Dict[str, Any]], project_context: str = "") -> str:
    """
    Generate a weekly summary for the given date range.
    """
    # Format date range for description
    start_str = start_date.strftime("%B %d, %Y")
    end_str = end_date.strftime("%B %d, %Y")
    date_range = f"{start_str} - {end_str}"

    return await summarize_timeline_recap_element(
        messages=messages, date_range_description=date_range, summary_type="weekly", project_context=project_context
    )
