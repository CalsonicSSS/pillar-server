from fastapi import APIRouter, Depends, Body, Path
from app.models.channel_models import ChannelResponse, ChannelDeletionResponse, ChannelMetricsResponse
from app.services.channel_services import get_project_channels, get_channel_by_id, update_channel, delete_channel, get_channel_metrics
from app.utils.app_states import get_async_supabase_client
from typing import List
from uuid import UUID
from supabase._async.client import AsyncClient
from app.utils.user_auth import verify_jwt_and_get_user_id

channel_router = APIRouter(prefix="/channels", tags=["channels"])


@channel_router.get("/project/{project_id}", response_model=List[ChannelResponse])
async def get_project_channels_handler(
    project_id: UUID = Path(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/channels/project/{project_id} GET route reached")
    return await get_project_channels(supabase, project_id, user_id)


@channel_router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel_by_id_handler(
    channel_id: UUID = Path(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/channels/{channel_id} GET route reached")
    return await get_channel_by_id(supabase, channel_id, user_id)


@channel_router.delete("/{channel_id}", response_model=ChannelDeletionResponse)
async def delete_channel_handler(
    channel_id: UUID = Path(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/channels/{channel_id} DELETE route reached")
    return await delete_channel(supabase, channel_id, user_id)


###########################################################################################################

# Add this route handler to your existing app/routes/channel_routes.py file


@channel_router.get("/{channel_id}/metrics", response_model=ChannelMetricsResponse)
async def get_channel_metrics_handler(
    channel_id: UUID,
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print(f"/channels/{channel_id}/metrics route reached")
    return await get_channel_metrics(supabase, channel_id, user_id)
