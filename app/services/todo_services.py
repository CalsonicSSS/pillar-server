from typing import List, Dict, Any, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone
import traceback
from supabase._async.client import AsyncClient
from app.custom_error import DataBaseError, GeneralServerError, UserAuthError
from app.models.todo_models import TodoGenerateRequest, TodoListResponse, TodoGenerateResponse, TodoListUpdateRequest, TodoItem
from app.utils.llm.todo_llm_helpers import generate_todo_summary_and_items
from app.services.user_oauth_credential_services import get_user_oauth_credentials_by_channel_type


async def generate_project_todo_list(
    supabase: AsyncClient, project_id: UUID, user_id: UUID, todo_request: TodoGenerateRequest
) -> TodoGenerateResponse:
    """
    Generate a new todo list for a project based on messages in the specified date range.
    Replaces any existing todo list for this project.
    """
    print("generate_project_todo_list service function runs")
    try:
        # Verify project belongs to user
        project_result = (
            await supabase.table("projects").select("id, project_context_detail").eq("id", str(project_id)).eq("user_id", str(user_id)).execute()
        )
        if not project_result.data:
            raise UserAuthError(error_detail_message="Project not found or access denied")

        project_context = project_result.data[0].get("project_context_detail", "")

        # Get user identities (similar to timeline recap)
        user_gmail_credentials = await get_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail")
        if user_gmail_credentials:
            user_gmail_address = user_gmail_credentials["oauth_data"]["user_info"]["emailAddress"]
            user_identities = f"gmail: {user_gmail_address}"
        else:
            user_identities = "No user identities found"

        # Fetch messages within the date range for this project
        messages_result = await supabase.rpc(
            "get_messages_with_filters",
            {
                "user_id_param": str(user_id),
                "project_id_param": str(project_id),
                "channel_id_param": None,
                "contact_id_param": None,
                "thread_id_param": None,
                "start_date_param": todo_request.start_date.isoformat(),
                "end_date_param": todo_request.end_date.isoformat(),
                "is_read_param": None,
                "is_from_contact_param": None,
                "limit_param": 200,
                "offset_param": 0,
            },
        ).execute()

        messages = messages_result.data

        # Generate date range description
        start_str = todo_request.start_date.strftime("%B %d, %Y")
        end_str = todo_request.end_date.strftime("%B %d, %Y")
        date_range_description = f"{start_str} - {end_str}"

        # Generate summary and todo items using LLM
        summary, llm_todo_items = await generate_todo_summary_and_items(
            messages=messages, user_identities=user_identities, date_range_description=date_range_description, project_context=project_context
        )

        print("summary:", summary)
        print("llm_todo_items:", llm_todo_items)

        # Format todo items for database storage
        formatted_todo_items = []
        for item in llm_todo_items:
            formatted_item = {
                "id": str(uuid4()),
                "description": item.get("description", ""),
                "is_completed": False,
                "completed_at": None,
                "display_order": item.get("priority"),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            formatted_todo_items.append(formatted_item)

        # Prepare todo list data
        todo_list_data = {
            "project_id": str(project_id),
            "start_date": todo_request.start_date.isoformat(),
            "end_date": todo_request.end_date.isoformat(),
            "summary": summary,
            "items": formatted_todo_items,
        }

        # Check if todo list already exists for this project
        existing_result = await supabase.table("todo_lists").select("id").eq("project_id", str(project_id)).execute()

        if existing_result.data:
            # Update existing todo list
            todo_list_data["updated_at"] = datetime.now(timezone.utc).isoformat()
            result = await supabase.table("todo_lists").update(todo_list_data).eq("project_id", str(project_id)).execute()
        else:
            # Create new todo list
            result = await supabase.table("todo_lists").insert(todo_list_data).execute()

        if not result.data:
            raise DataBaseError(error_detail_message="Failed to save todo list")

        return TodoGenerateResponse(status="success", status_message=f"Successfully generated todo list with {len(formatted_todo_items)} items")

    except (DataBaseError, UserAuthError):
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to generate todo list")


# ------------------------------------------------------------------------------------------------------------------------------------


async def get_project_todo_list(supabase: AsyncClient, project_id: UUID, user_id: UUID) -> Optional[TodoListResponse]:
    """
    Get the existing todo list for a project.
    """
    print("get_project_todo_list service function runs")
    try:
        # Verify project belongs to user
        project_result = await supabase.table("projects").select("id").eq("id", str(project_id)).eq("user_id", str(user_id)).execute()
        if not project_result.data:
            raise UserAuthError(error_detail_message="Project not found or access denied")

        # Get todo list
        result = await supabase.table("todo_lists").select("*").eq("project_id", str(project_id)).execute()

        if not result.data:
            return None

        todo_data = result.data[0]

        # Convert items to TodoItem objects
        todo_items = [TodoItem(**item) for item in todo_data.get("items", [])]

        # Create response with summary field
        response_data = {**todo_data, "items": todo_items}
        return TodoListResponse(**response_data)

    except UserAuthError:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to retrieve todo list")


# ------------------------------------------------------------------------------------------------------------------------------------


# The update_payload.items is the entire updated todo list each time. So even if the user just:
# Marks one item as completed ✓
# Edits one item's description ✓
# Reorders items ✓
# Adds/removes items ✓
# The frontend sends the complete updated items array back to the backend.
async def update_project_todo_list(supabase: AsyncClient, project_id: UUID, user_id: UUID, update_payload: TodoListUpdateRequest) -> TodoListResponse:
    """
    Update todo list items (for frontend editing of individual items).
    """
    print("update_project_todo_list service function runs")
    try:
        # Verify project belongs to user and todo list exists
        existing_todo = await get_project_todo_list(supabase, project_id, user_id)
        if not existing_todo:
            raise DataBaseError(error_detail_message="Todo list not found")

        # Update the items
        update_data = {"items": update_payload.items, "updated_at": datetime.now(timezone.utc).isoformat()}

        result = await supabase.table("todo_lists").update(update_data).eq("project_id", str(project_id)).execute()

        if not result.data:
            raise DataBaseError(error_detail_message="Failed to update todo list")

        # Return updated todo list
        return await get_project_todo_list(supabase, project_id, user_id)

    except (DataBaseError, UserAuthError):
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to update todo list")
