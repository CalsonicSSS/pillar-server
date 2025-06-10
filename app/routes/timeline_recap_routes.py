from fastapi import APIRouter, Depends, Path, Query
from app.services.timeline_recap_services import (
    get_project_timeline_recap,
    initialize_project_timeline_recap_data_structure,
    generate_to_be_summarized_timeline_recap_summaries,
)
from app.models.timeline_recap_models import TimelineRecapResponse
from app.utils.app_states import get_async_supabase_client
from typing import Optional
from uuid import UUID
from supabase._async.client import AsyncClient
from app.utils.user_auth import verify_jwt_and_get_user_id

timeline_recap_router = APIRouter(prefix="/timeline-recap", tags=["timeline-recap"])


@timeline_recap_router.get("/project/{project_id}", response_model=TimelineRecapResponse)
async def get_project_timeline_recap_handler(
    project_id: UUID = Path(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/timeline-recap/project/{project_id} GET route reached")
    return await get_project_timeline_recap(supabase, project_id, user_id)


@timeline_recap_router.post("/project/{project_id}/initialize", response_model=TimelineRecapResponse)
async def initialize_project_timeline_recap_data_structure_handler(
    project_id: UUID = Path(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/timeline-recap/project/{project_id}/initialize POST route reached")
    return await initialize_project_timeline_recap_data_structure(supabase, project_id, user_id)


@timeline_recap_router.post("/project/{project_id}/generate-summaries", response_model=TimelineRecapResponse)
async def generate_to_be_summarized_timeline_recap_summaries_handler(
    project_id: UUID = Path(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/timeline-recap/project/{project_id}/generate-summaries POST route reached")
    return await generate_to_be_summarized_timeline_recap_summaries(supabase, project_id, user_id)
