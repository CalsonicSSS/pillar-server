from fastapi import APIRouter, Depends, Query, Path, Response
from app.utils.app_states import get_async_supabase_client, get_async_httpx_client
from app.utils.user_auth import verify_jwt_and_get_user_id
from app.services.gmail.gmail_oauth_channel_services import (
    initialize_gmail_channel_create_and_oauth,
    gmail_oauth_complete_callback,
    gmail_reoauth_process,
)
from uuid import UUID
from supabase._async.client import AsyncClient
from httpx import AsyncClient


oauth_router = APIRouter(prefix="/oauth/gmail", tags=["oauth"])


# so far the flow of gmail oauth process is conducted within a specific project upon a gmail channel creation action triggered by the user
@oauth_router.post("/initialize/{project_id}")
async def initialize_gmail_channel_create_and_oauth_handler(
    project_id: str = Path(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/oauth/gmail/initialize POST route reached")
    return await initialize_gmail_channel_create_and_oauth(supabase, project_id, user_id)


@oauth_router.post("/refresh")
async def refresh_gmail_oauth_handler(
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    """
    Generate a new OAuth URL when any credentials and refresh token are invalidated.
    Clears existing invalid credentials.
    """
    print("/oauth/gmail/refresh POST route reached")
    return await gmail_reoauth_process(supabase, user_id)


@oauth_router.get("/callback")
async def gmail_oauth_complete_callback_handler(
    code: str = Query(...),
    state: str = Query(...),  # state parameter contains channel_id
    supabase: AsyncClient = Depends(get_async_supabase_client),
    httpx_client: AsyncClient = Depends(get_async_httpx_client),
):
    print("/oauth/gmail/callback GET route reached")
    await gmail_oauth_complete_callback(supabase, httpx_client, code, state)

    # Return a basic success HTML page
    # In production, this would redirect to a success page in your frontend
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Gmail Integration Successful</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                text-align: center;
                padding: 50px;
            }
            .success {
                color: #4CAF50;
                font-size: 24px;
                margin-bottom: 20px;
            }
            .message {
                margin-bottom: 30px;
            }
            .close-button {
                background-color: #4CAF50;
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 16px;
            }
        </style>
    </head>
    <body>
        <div class="success">✓ Gmail Connected Successfully</div>
        <div class="message">You can now close this window and return to the application.</div>
        <button class="close-button" onclick="window.close()">Close Window</button>
    </body>
    </html>
    """
    return Response(content=html_content, media_type="text/html")
