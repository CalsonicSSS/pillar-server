from fastapi import APIRouter, Depends, Body, Path
from app.models.contact_models import ContactCreate, ContactResponse, ContactUpdate, ContactDeletionResponse
from app.services.contact_services import create_contact, get_channel_contacts, get_contact_by_id, update_contact, delete_contact
from app.utils.app_states import get_async_supabase_client
from typing import List
from uuid import UUID
from supabase._async.client import AsyncClient
from app.utils.user_auth import verify_jwt_and_get_user_id

contact_router = APIRouter(prefix="/contacts", tags=["contacts"])


@contact_router.post("/", response_model=ContactResponse)
async def create_contact_handler(
    contact_create: ContactCreate = Body(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/contacts POST route reached")
    return await create_contact(supabase, contact_create, user_id)


@contact_router.get("/channel/{channel_id}", response_model=List[ContactResponse])
async def get_channel_contacts_handler(
    channel_id: UUID = Path(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/contacts/channel/{channel_id} GET route reached")
    return await get_channel_contacts(supabase, channel_id, user_id)


@contact_router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact_by_id_handler(
    contact_id: UUID = Path(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/contacts/{contact_id} GET route reached")
    return await get_contact_by_id(supabase, contact_id, user_id)


@contact_router.patch("/{contact_id}", response_model=ContactResponse)
async def update_contact_handler(
    contact_id: UUID = Path(...),
    contact_update_payload: ContactUpdate = Body(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/contacts/{contact_id} PATCH route reached")
    return await update_contact(supabase, contact_id, user_id, contact_update_payload)


@contact_router.delete("/{contact_id}", response_model=ContactDeletionResponse)
async def delete_contact_handler(
    contact_id: UUID = Path(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/contacts/{contact_id} DELETE route reached")
    return await delete_contact(supabase, contact_id, user_id)
