from typing import List, Dict, Any
from datetime import datetime
import traceback
from app.utils.llm.claude_client import claude_message_api
from app.custom_error import GeneralServerError


def create_summarization_system_prompt() -> str:
    system_prompt = """You are a professional executive assistant for accounting professionals (the user). 
    Your role is to summarize communication messages between user ("accounting professionals") and their clients efficiently within a specific PROJECT SCOPE. 
    Focusing on what matters most to accounting work and based on all the messages provided.
    Provide only the summary in bullet point format in the end, with no additional text or commentary.
    """
    return system_prompt


def create_summarization_user_prompt(
    date_range_description: str,
    user_own_identities_context: str,
    project_context_content: str,
    summary_type: str,
) -> str:
    time_scope = "day" if summary_type == "daily" else "week"
    user_prompt = f"""Please summarize all the communication messages above from {date_range_description} date range into a concise summary within this project for me.

Additional important context for you to consider:
- {user_own_identities_context}
- {project_context_content}
    
Task Guidelines:
1. Carefully review all provided communication messages and summarize them in bullet points.
2. For each message, pay close attention to: "From (sender)", "To (recipients)", "Message subject (if available)", "Attachments (if available)", and "Message body".
3. Use the "Myself identifies" context to accurately distinguish which messages are sent **by me**, and which are sent **by my client contacts**. Prioritize the summary on key information from client messages and any significant responses or actions from me, to clearly map out the all the key stakeholders relationships and work-related exchanges within the project (VERY IMPORTANT AND MUST).
4. Focus your summary on key content, insights, attachments, and important action items. Exclude non-work-related or social messages unless they are directly relevant to project tasks.
5. If I have provided any non-empty "project context", use it as background to better interpret and prioritize the relevance of communication content.

Response Format:
1. Format your entire response with bullet points based output only (without any other generate content besides the generated bullet points), with each point on a new line starting with "•"
2. Make sure your overall summarization bullet points are concise and straight to the point.
3. Use professional, direct language.
4. If there are no communications message or entire provide communication messages are non-work related, your only bullet point should be "• No important summary during this {time_scope}."
"""

    return user_prompt


def format_all_project_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    # If no messages:
    if not messages:
        return "There were no messages in this time period."

    all_message_contents = ""
    all_message_contents += "Here are all communication messages to summarize (each message is separated by lines of '-'):\n\n"

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

        sender = msg.get("sender_account", "Unknown")
        recipients = ", ".join(msg.get("recipient_accounts", ["Unknown"]))
        subject = msg.get("subject", "No subject")
        attachments = ", ".join([attachment["filename"] for attachment in msg.get("attachments")])

        all_message_contents += f"From: {sender}\n"
        all_message_contents += f"To: {recipients}\n"
        all_message_contents += f"Subject: {subject}\n"

        # we will later need to find ways to dynamic find message's corresponding channel type
        # so far we only have gmail channel type enabled
        # all_message_contents += f"message channel type: gmail"

        all_message_contents += f"available attachments: {attachments}"

        # Use text body if available, otherwise HTML
        body = msg.get("body_text", msg.get("body_html", "No content"))

        # Truncate very long bodies
        if len(body) > 2500:
            body = body[:2500] + "... [truncated]"

        all_message_contents += f"Message body:\n{body}\n\n"
        all_message_contents += "-" * 40 + "\n\n\n\n"

    return all_message_contents


async def summarize_timeline_recap_element(
    messages: List[Dict[str, Any]],
    user_identifies: str,
    date_range_description: str,
    summary_type: str = "daily",
    project_context: str = "",
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
        project_context_content = f"Here is my additional 'project context' for you to know: {project_context}"

        user_own_identities_context = f"""
            'Myself identifies':
            
            These are my own identities across different channels within this project: {user_identifies}. 
            Please use this information to distinguish between me (myself) and my clients when generating summaries based on all messages from these channels in this single project."""

        # Create system prompt
        system_prompt = create_summarization_system_prompt()

        # Format messages for Claude
        full_project_message_contents = format_all_project_messages(messages)

        # Add the task instruction to the last message
        user_prompt = create_summarization_user_prompt(date_range_description, user_own_identities_context, project_context_content, summary_type)

        formatted_messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": full_project_message_contents},
                    {"type": "text", "text": user_prompt},
                ],
            },
        ]

        # Get response from Claude
        llm_response = await claude_message_api(
            system_prompt=system_prompt,
            messages=formatted_messages,
            temperature=0.3,  # Lower temperature for more consistent summaries
            max_tokens=1000,  # Limit response to avoid verbosity
        )

        # Extract the summary text
        summary = llm_response.content[0].text.strip()

        return summary

    except Exception as e:
        print(f"Error in summarize_messages_in_date_range: {str(e)}")
        print(traceback.format_exc())
        raise GeneralServerError("An error occurred while generating the summary.")


async def generate_daily_summary(start_date: datetime, user_identifies: str, messages: List[Dict[str, Any]], project_context: str = "") -> str:
    """
    Generate a daily summary for the given date range.
    """
    # Format date for description
    date_str = start_date.strftime("%B %d, %Y")

    return await summarize_timeline_recap_element(
        messages=messages, user_identifies=user_identifies, date_range_description=date_str, summary_type="daily", project_context=project_context
    )


async def generate_weekly_summary(
    start_date: datetime, user_identifies: str, end_date: datetime, messages: List[Dict[str, Any]], project_context: str = ""
) -> str:
    """
    Generate a weekly summary for the given date range.
    """
    # Format date range for description
    start_str = start_date.strftime("%B %d, %Y")
    end_str = end_date.strftime("%B %d, %Y")
    date_range = f"{start_str} - {end_str}"

    return await summarize_timeline_recap_element(
        messages=messages, user_identifies=user_identifies, date_range_description=date_range, summary_type="weekly", project_context=project_context
    )
