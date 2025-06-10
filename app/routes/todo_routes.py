from fastapi import APIRouter, Depends, Body, Path
from typing import Optional
from uuid import UUID
from supabase._async.client import AsyncClient
from app.utils.app_states import get_async_supabase_client
from app.utils.user_auth import verify_jwt_and_get_user_id
from app.services.todo_services import generate_project_todo_list, get_project_todo_list, update_project_todo_list
from app.models.todo_models import TodoGenerateRequest, TodoListResponse, TodoListUpdateRequest

todo_router = APIRouter(prefix="/todo-lists", tags=["todo-lists"])


@todo_router.post("/project/{project_id}", response_model=TodoListResponse)
async def generate_project_todo_list_handler(
    project_id: UUID = Path(...),
    todo_request: TodoGenerateRequest = Body(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    """
    Generate a new todo list for a project based on messages in the specified date range.
    """
    print("/todo-lists/project/{project_id} POST route reached")
    return await generate_project_todo_list(supabase, project_id, user_id, todo_request)


# --------------------------------------------------------------------------------------------------------------------------------


# FastAPI already allows the response to be None by default — as long as the route actually returns None.
# in return None, then response body will simply have "null" as json (not wrapped in an object, array, or anything else. It's just the standalone)
# Optional[X] is equivalent to Union[X, None].
@todo_router.get("/project/{project_id}", response_model=Optional[TodoListResponse])
async def get_project_todo_list_handler(
    project_id: UUID = Path(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    """
    Get the existing todo list for a project. Returns null if no todo list exists.
    """
    print("/todo-lists/project/{project_id} GET route reached")
    todo_list = await get_project_todo_list(supabase, project_id, user_id)
    return todo_list  # Can be None, FastAPI handles this properly


# --------------------------------------------------------------------------------------------------------------------------------


@todo_router.patch("/project/{project_id}", response_model=TodoListResponse)
async def update_project_todo_list_handler(
    project_id: UUID = Path(...),
    update_payload: TodoListUpdateRequest = Body(...),
    supabase: AsyncClient = Depends(get_async_supabase_client),
    user_id: UUID = Depends(verify_jwt_and_get_user_id),
):
    """
    Update todo list items (for marking completed/incomplete, editing descriptions, etc.).
    """
    print("/todo-lists/project/{project_id} PATCH route reached")
    return await update_project_todo_list(supabase, project_id, user_id, update_payload)
