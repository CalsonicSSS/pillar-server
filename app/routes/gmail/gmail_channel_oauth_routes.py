from fastapi import APIRouter, Depends, Query, Path, Response
from app.utils.app_states import get_async_supabase_client, get_async_httpx_client
from app.utils.user_auth import verify_jwt_and_get_user_id
from app.services.gmail.gmail_channel_oauth_services import (
    initialize_gmail_channel_create_and_oauth,
    gmail_channel_oauth_complete_callback,
    gmail_channel_reoauth_process,
    gmail_channel_oauth_process,
)
from uuid import UUID
from supabase._async.client import AsyncClient
from httpx import AsyncClient
from app.models.oauth_process_models import GmailOAuthResponse, GmailOAuthCallbackCompletionResponse
from app.models.channel_models import ChannelResponse


gmail_channel_oauth_router = APIRouter(prefix="/gmail/channel", tags=["oauth"])


# this is to essentially create a new gmail channel and see if we need a whole gmail oauth flow for this user or not
@gmail_channel_oauth_router.post("/initialize/{project_id}", response_model=ChannelResponse)
async def initialize_gmail_channel_create_and_oauth_handler(
    project_id: str = Path(...),  # "..." means this is a required path parameter
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/gmail/channel/initialize POST route reached")
    return await initialize_gmail_channel_create_and_oauth(supabase, project_id, user_id)


# this is to create a oauth url to send to client side that navigate user to the google gmail flow
@gmail_channel_oauth_router.post("/oauth/{channel_id}", response_model=GmailOAuthResponse)
async def gmail_channel_oauth_process_handler(
    channel_id: str = Path(...),  # "..." means this is a required path parameter
):
    print("/gmail/channel/oauth POST route reached")
    return gmail_channel_oauth_process(channel_id)


@gmail_channel_oauth_router.post("/reoauth", response_model=GmailOAuthResponse)
async def gmail_channel_reoauth_process_handler(
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/gmail/channel/reoauth POST route reached")
    return await gmail_channel_reoauth_process(supabase, user_id)


# This is the browser side automatically redirect GET request once a gmail oauth flow and consent is done by user
# we then extract code and state query param here for processing
@gmail_channel_oauth_router.get("/callback", response_model=GmailOAuthCallbackCompletionResponse)
async def gmail_channel_oauth_complete_callback_handler(
    code: str = Query(...),  # google will attach this "code" query param in redirect url here
    state: str = Query(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    httpx_client: AsyncClient = Depends(get_async_httpx_client),
):
    print("/gmail/channel/callback GET route reached")
    return await gmail_channel_oauth_complete_callback(supabase, httpx_client, code, state)
