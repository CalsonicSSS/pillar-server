from app.core.config import app_config_settings
from anthropic import AsyncAnthropic
from typing import Dict, List, Any

# Create a global client
claude_client = AsyncAnthropic(api_key=app_config_settings.ANTHROPIC_API_KEY)


async def claude_message_api(
    system_prompt: str,
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int,
    model: str = app_config_settings.CLAUDE_MODEL_SONNET_4,
):
    """
    Send a message to Claude and get a response.

    Args:
        system_prompt: Instructions for Claude
        messages: List of message objects with role and content
        model: Claude model to use
        temperature: Controls randomness (0-1)
        max_tokens: Maximum tokens in response

    Returns:
        Claude's response
    """
    response = await claude_client.messages.create(
        model=model,
        system=system_prompt,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    return response
