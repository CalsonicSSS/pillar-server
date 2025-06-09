from typing import List, Dict, Any, Tuple
from datetime import datetime
import json
import traceback
from app.utils.llm.claude_client import claude_message_api
from app.custom_error import GeneralServerError


def create_todo_system_prompt() -> str:
    return """You are a professional executive assistant for accounting professionals. 
    Your role is to analyze all communication messages within a given date time range and generate:
    1. A concise summary of what happened in the given time period
    2. A prioritized list of actionable to-do items based on the communications
    
    Focus on accounting work, client needs, possible deadlines, follow-up, and other relevant important actions.
    Provide your response in the exact JSON format specified."""


def create_todo_user_prompt(
    date_range_description: str,
    user_identities: str,
    project_context: str,
) -> str:
    return f"""Please analyze all the communication messages from {date_range_description} within this project and generate:

1. A brief key insight summary of what happened during this period
2. A prioritized list of actionable to-do items

Additional important context for you to consider:
- additional 'project context' for you to know: {project_context}
- Myself identifies: {user_identities} (Please use this information to distinguish between me (myself) and my clients when generating)

Guidelines:
- Focus on actionable items that require follow-up
- Prioritize by urgency and importance
- Extract specific deadlines, client requests, pending tasks, and other relevant possible important content as you see fit
- Ignore social/non-work communications unless directly relevant
- If I have provided any non-empty "project context", use it as background to better interpret and prioritize the relevance of communication content.
- Use the "Myself identifies" context to accurately distinguish which messages are sent **by me**, and which are sent **by my client contacts**. To clearly map out the all the key stakeholders relationships and work-related exchanges within the project (VERY IMPORTANT AND MUST).



Response Format:
{{
  "summary": "Brief summary of communications during this period...",
  "todo_items": [
    {{
      "description": "Specific actionable task description",
      "priority": 1
    }},
    {{
      "description": "Another task description", 
      "priority": 2
    }}
  ]
}}

Respond with only the JSON format response shown above, strictly no additional and context text such as "json" etc AT ALL."""


def format_messages_for_todo_analysis(messages: List[Dict[str, Any]]) -> str:
    if not messages:
        return "No messages found in this time period."

    content = "All communication messages to analyze (each message is separated by lines of '-'):\n\n"

    for msg in messages:
        date = msg.get("registered_at", "Unknown date")
        if isinstance(date, str):
            try:
                date_obj = datetime.fromisoformat(date.replace("Z", "+00:00"))
                date = date_obj.strftime("%Y-%m-%d %H:%M")
            except:
                pass

        attachments = ", ".join([attachment["filename"] for attachment in msg.get("attachments")])

        sender = msg.get("sender_account", "Unknown")
        subject = msg.get("subject", "No subject")
        body = msg.get("body_text", msg.get("body_html", "No content"))

        # Truncate long messages
        if len(body) > 2500:
            body = body[:2500] + "... [truncated]"

        content += f"Date: {date}\n"
        content += f"From: {sender}\n"
        content += f"Subject: {subject}\n"
        content += f"available attachments: {attachments}"
        content += f"Content: {body}\n"
        content += "-" * 40 + "\n\n"

    return content


async def generate_todo_summary_and_items(
    messages: List[Dict[str, Any]],
    user_identities: str,
    date_range_description: str,
    project_context: str = "",
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Generate summary and todo items from messages using Claude.

    Returns:
        Tuple of (summary_text, list_of_todo_items)
    """
    try:
        print("generate_todo_summary_and_items runs...")
        system_prompt = create_todo_system_prompt()

        # Format messages for analysis
        message_content = format_messages_for_todo_analysis(messages)

        # Create user prompt
        user_prompt = create_todo_user_prompt(date_range_description, user_identities, project_context)

        # Prepare messages for Claude
        formatted_messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": message_content},
                    {"type": "text", "text": user_prompt},
                ],
            },
        ]

        # Get response from Claude
        llm_response = await claude_message_api(
            system_prompt=system_prompt,
            messages=formatted_messages,
            temperature=0.3,
            max_tokens=1500,
        )

        # Parse JSON response
        response_text = llm_response.content[0].text.strip()
        print("response_text:", response_text)

        parsed_response = json.loads(response_text)
        summary = parsed_response.get("summary", "No summary generated")
        todo_items = parsed_response.get("todo_items", [])

        return summary, todo_items

    except Exception as e:
        print(f"Error generating todo summary and items: {str(e)}")
        print(traceback.format_exc())
        raise GeneralServerError("Failed to generate todo analysis")
