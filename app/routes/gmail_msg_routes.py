from fastapi import APIRouter, Depends, Body, Path, Query
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime
from app.services.gmail_msg_services import (
    initial_fetch_and_store_messages_from_all_contacts,
    get_messages_with_filters,
    get_message_by_id,
    mark_message_as_read,
)
from app.utils.app_states import get_async_supabase_client, get_async_httpx_client
from supabase._async.client import AsyncClient
from httpx import AsyncClient
from app.utils.user_auth import verify_jwt_and_get_user_id

message_router = APIRouter(prefix="/messages", tags=["messages"])


@message_router.post("/gmail/fetch", response_model=Dict[str, Any])
async def fetch_initial_messages_handler(
    channel_id: UUID = Body(...),
    contact_ids: List[UUID] = Body(...),
    start_date: datetime = Body(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    httpx_client: AsyncClient = Depends(get_async_httpx_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/gmail/messages/fetch POST route reached")
    return await initial_fetch_and_store_messages_from_all_contacts(supabase, httpx_client, channel_id, contact_ids, start_date, user_id)


@message_router.get("/gmail/", response_model=List[Dict[str, Any]])
async def get_messages_handler(
    channel_id: Optional[UUID] = Query(None),
    contact_id: Optional[UUID] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    is_read: Optional[bool] = Query(None),
    is_from_contact: Optional[bool] = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/gmail/messages GET route reached")
    filter_params = {
        "channel_id": channel_id,
        "contact_id": contact_id,
        "start_date": start_date,
        "end_date": end_date,
        "is_read": is_read,
        "is_from_contact": is_from_contact,
        "limit": limit,
        "offset": offset,
    }
    return await get_messages_with_filters(supabase, user_id, filter_params)


@message_router.get("/gmail/{message_id}", response_model=Dict[str, Any])
async def get_message_by_id_handler(
    message_id: UUID = Path(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/messages/{message_id} GET route reached")
    return await get_message_by_id(supabase, message_id, user_id)


@message_router.patch("/gmail/{message_id}/read", response_model=Dict[str, Any])
async def mark_message_as_read_handler(
    message_id: UUID = Path(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/messages/{message_id}/read PATCH route reached")
    return await mark_message_as_read(supabase, message_id, user_id)
