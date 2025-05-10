from fastapi import APIRouter, Depends, Body
from app.models.project_models import ProjectCreate, ProjectResponse, ProjectUpdate
from app.services.project_services import create_new_project, get_user_projects, get_project_by_id, update_project, archive_project, unarchive_project
from app.utils.app_states import get_async_supabase_client
from typing import List
from uuid import UUID
from supabase._async.client import AsyncClient
from app.utils.user_auth import verify_jwt_and_get_user_id

project_router = APIRouter(prefix="/projects", tags=["projects"])


@project_router.post("/", response_model=ProjectResponse)
async def create_new_project_handler(
    new_project_payload: ProjectCreate = Body(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/projects route reached")
    return await create_new_project(supabase, new_project_payload, user_id)


@project_router.get("/", response_model=List[ProjectResponse])
async def get_user_projects_handler(
    status: str = None,
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/projects route reached")
    return await get_user_projects(supabase, user_id, status)


@project_router.get("/{project_id}", response_model=ProjectResponse)
async def get_project_by_id_handler(
    project_id: UUID,
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/projects/project_id route reached")
    return await get_project_by_id(supabase, project_id, user_id)


@project_router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project_handler(
    project_id: UUID,
    project_update_payload: ProjectUpdate = Body(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/projects/project_id route reached")
    return await update_project(supabase, project_id, user_id, project_update_payload)


@project_router.patch("/{project_id}/archive", response_model=ProjectResponse)
async def archive_project_handler(
    project_id: UUID,
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/projects/project_id/archive route reached")
    return await archive_project(supabase, project_id, user_id)


@project_router.patch("/{project_id}/unarchive", response_model=ProjectResponse)
async def unarchive_project_handler(
    project_id: UUID,
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    print("/projects/project_id/unarchive route reached")
    return await unarchive_project(supabase, project_id, user_id)
