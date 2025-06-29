from fastapi import APIRouter, Depends, Body, Path, Query
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime
from app.services.message_services import get_messages_with_filters, get_message_by_id, mark_message_as_read
from app.utils.app_states import get_async_supabase_client
from supabase._async.client import AsyncClient
from app.utils.user_auth import verify_jwt_and_get_user_id
from app.models.message_models import MessageResponse, MessageFilter, MessageUpdate

general_message_router = APIRouter(prefix="/messages", tags=["messages"])


@general_message_router.get("/", response_model=List[MessageResponse])
async def get_messages_with_filters_handler(
    project_id: Optional[UUID] = Query(None),
    channel_id: Optional[UUID] = Query(None),
    contact_id: Optional[UUID] = Query(None),
    thread_id: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    is_read: Optional[bool] = Query(None),
    is_from_contact: Optional[bool] = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
    supabase: AsyncClient = Depends(get_async_supabase_client),
):
    print("/messages GET route reached")

    return await get_messages_with_filters(
        supabase,
        user_id,
        MessageFilter(
            project_id=project_id,
            channel_id=channel_id,
            contact_id=contact_id,
            thread_id=thread_id,
            start_date=start_date,
            end_date=end_date,
            is_read=is_read,
            is_from_contact=is_from_contact,
            limit=limit,
            offset=offset,
        ),
    )


@general_message_router.get("/{message_id}", response_model=MessageResponse)
async def get_message_by_id_handler(
    message_id: UUID = Path(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/messages/{message_id} GET route reached")
    return await get_message_by_id(supabase, message_id, user_id)


@general_message_router.patch("/{message_id}/read", response_model=MessageResponse)
async def mark_message_as_read_handler(
    message_id: UUID = Path(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
    message_update_payload: MessageUpdate = Body(...),
):
    print("/messages/{message_id}/read PATCH route reached")
    return await mark_message_as_read(supabase, message_id, user_id, message_update_payload)
