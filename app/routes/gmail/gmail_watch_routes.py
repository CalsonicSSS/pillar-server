from fastapi import APIRouter, Depends, Path
from app.services.gmail.gmail_watch_services import start_gmail_user_watch, stop_gmail_user_watch, check_and_renew_gmail_user_watch
from app.utils.app_states import get_async_supabase_client
from typing import Dict, Any
from uuid import UUID
from supabase._async.client import AsyncClient
from app.utils.user_auth import verify_jwt_and_get_user_id

gmail_watch_router = APIRouter(prefix="/gmail/watch", tags=["gmail-watch"])


# this is the manual request based gmail watch api trigger. Frontend side typically wont need to trigger this
@gmail_watch_router.post("/start")
async def start_gmail_user_watch_handler(
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
) -> Dict[str, Any]:
    """
    Start Gmail watch for the authenticated user.
    This begins monitoring the user's Gmail for changes.
    """
    print("/gmail/watch/start POST route reached")
    return await start_gmail_user_watch(supabase, user_id)


@gmail_watch_router.post("/stop")
async def stop_gmail_user_watch_handler(
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
) -> Dict[str, Any]:
    """
    Stop Gmail watch for the authenticated user.
    This stops monitoring the user's Gmail for changes.
    """
    print("/gmail/watch/stop POST route reached")
    return await stop_gmail_user_watch(supabase, user_id)


@gmail_watch_router.post("/renew")
async def check_and_renew_gmail_user_watch_handler(
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
) -> Dict[str, Any]:
    """
    Check if Gmail watch is expired and renew if necessary.
    This ensures continuous monitoring of the user's Gmail.
    """
    print("/gmail/watch/renew POST route reached")
    return await check_and_renew_gmail_user_watch(supabase, user_id)
