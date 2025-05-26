from fastapi import APIRouter, Depends, Body, Path, Query
from typing import List, Dict, Any
from uuid import UUID
from datetime import datetime
from app.services.gmail.gmail_msg_services import (
    fetch_and_store_gmail_messages_from_all_contacts,
)
from app.utils.app_states import get_async_supabase_client
from supabase._async.client import AsyncClient
from app.utils.user_auth import verify_jwt_and_get_user_id
from app.models.oauth_process_models import GmailContactsInitialMessagesFetchRequest, GmailContactsInitialMessagesFetchResponse

gmail_message_router = APIRouter(prefix="/gmail/message", tags=["messages"])


@gmail_message_router.post("/fetch", response_model=GmailContactsInitialMessagesFetchResponse)
async def fetch_and_store_gmail_messages_from_all_contacts_handler(
    gmail_message_fetch_info: GmailContactsInitialMessagesFetchRequest = Body(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/gmail/message/fetch POST route reached")
    return await fetch_and_store_gmail_messages_from_all_contacts(supabase, gmail_message_fetch_info, user_id)
