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

message_router = APIRouter(prefix="/gmail", tags=["messages"])


@message_router.post("/fetch", response_model=Dict[str, Any])
async def fetch_and_store_gmail_messages_from_all_contacts_handler(
    channel_id: UUID = Body(...),
    contact_ids: List[UUID] = Body(...),
    start_date: datetime = Body(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/gmai/fetch POST route reached")
    return await fetch_and_store_gmail_messages_from_all_contacts(supabase, channel_id, contact_ids, start_date, user_id)
