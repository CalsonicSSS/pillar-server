from fastapi import APIRouter, Depends, Query, Path, Response
from app.utils.app_states import get_async_supabase_client, get_async_httpx_client
from app.utils.user_auth import verify_jwt_and_get_user_id
from app.services.gmail.gmail_channel_oauth_services import (
    initialize_gmail_channel_create_and_oauth,
    gmail_channel_oauth_complete_callback,
    gmail_channel_reoauth_process,
)
from uuid import UUID
from supabase._async.client import AsyncClient
from httpx import AsyncClient
from app.models.oauth_process_models import GmailOAuthFlowResponse, GmailOAuthCallbackCompletionResponse


gmail_channel_oauth_router = APIRouter(prefix="/gmail/channel", tags=["oauth"])


# this is to essentially create a new gmail channel and see if we need a whole gmail oauth flow for this user or not
@gmail_channel_oauth_router.post("/initialize/{project_id}", response_model=GmailOAuthFlowResponse)
async def initialize_gmail_channel_create_and_oauth_handler(
    project_id: str = Path(...),  # "..." means this is a required path parameter
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/gmail/oauth/initialize POST route reached")
    return await initialize_gmail_channel_create_and_oauth(supabase, project_id, user_id)


@gmail_channel_oauth_router.post("/refresh", response_model=GmailOAuthFlowResponse)
async def refresh_gmail_oauth_handler(
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    """
    Generate a new OAuth URL when any credentials and refresh token are invalidated.
    Clears existing invalid credentials.
    """
    print("/gmail/oauth/refresh POST route reached")
    return await gmail_channel_reoauth_process(supabase, user_id)


# this endpoint is reached from the client-side browser redirect request automatically with state / code query parameter attached
# this is only GET method since its client side browser request
# we will then extract and utilize the auth code
@gmail_channel_oauth_router.get("/callback", response_model=GmailOAuthCallbackCompletionResponse)
async def gmail_channel_oauth_complete_callback_handler(
    code: str = Query(...),  # google will attach this "code" query param in redirect url here
    state: str = Query(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    httpx_client: AsyncClient = Depends(get_async_httpx_client),
):
    print("/gmail/oauth/callback GET route reached")
    return await gmail_channel_oauth_complete_callback(supabase, httpx_client, code, state)
