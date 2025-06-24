from app.models.project_models import ProjectCreate, ProjectUpdate, ProjectResponse
from typing import List, Optional
from uuid import UUID
from supabase._async.client import AsyncClient
from app.custom_error import DataBaseError, GeneralServerError
import traceback
from app.utils.generals import getProjectAvatarLetter
from datetime import datetime, timezone


async def get_user_projects(supabase: AsyncClient, user_id: UUID, status: Optional[str] = None) -> List[ProjectResponse]:
    print("get_projects service function runs")

    query = supabase.table("projects").select("*").eq("user_id", str(user_id)).order("created_at", desc=True)

    if status:
        query = query.eq("status", status)

    try:
        result = await query.execute()

        return [ProjectResponse(**project) for project in result.data]

    except Exception as e:
        print(traceback.format_exc())
        print("GeneralServerError occurred:", str(e))
        raise GeneralServerError(error_detail_message="Something went wrong when fetching your projects. Please try again later.")


# -----------------------------------------------------------------------------------------------------------------------------


async def create_new_project(supabase: AsyncClient, new_project_payload: ProjectCreate, user_id: UUID) -> ProjectResponse:
    print("create_new_project service function runs")
    try:
        new_project_data = new_project_payload.model_dump()

        # adding additional fields for creation
        new_project_data["user_id"] = str(user_id)  # we need to convert UUID to str for json serialization
        new_project_data["status"] = "active"  # "active" for new projects
        new_project_data["start_date"] = new_project_data[
            "start_date"
        ].isoformat()  # we need to convert datetime to iso str format for json serialization (this should be utc time zone already from the frontend)
        new_project_data["avatar_letter"] = getProjectAvatarLetter(new_project_data["name"])

        # .execute() is the method where we actually send the request to Supabase as I/O operation
        result = await supabase.table("projects").insert(new_project_data).execute()

        # the .data is the list of records (dict) returned from the database
        if not result.data:
            raise DataBaseError(error_detail_message="Failed to create project")

        return ProjectResponse(**result.data[0])

    except DataBaseError:
        print(traceback.format_exc())
        print("DataBaseError occurred")
        raise

    except Exception as e:
        print(traceback.format_exc())
        print("GeneralServerError occurred:", str(e))
        raise GeneralServerError(error_detail_message="Something went wrong when creating new project. Please try again later.")


# -----------------------------------------------------------------------------------------------------------------------------


async def get_project_by_id(supabase: AsyncClient, project_id: UUID, user_id: UUID) -> ProjectResponse:
    print("get_project_by_id service function runs")

    try:
        result = await supabase.table("projects").select("*").eq("id", str(project_id)).eq("user_id", str(user_id)).execute()

        if not result.data:
            raise DataBaseError(error_detail_message="Project not found")

        return ProjectResponse(**result.data[0])

    except DataBaseError:
        raise

    except Exception as e:
        print(traceback.format_exc())
        print("GeneralServerError occurred:", str(e))
        raise GeneralServerError(error_detail_message="Something went wrong from our side. Please try again later.")


# -----------------------------------------------------------------------------------------------------------------------------


async def update_project(supabase: AsyncClient, project_id: UUID, user_id: UUID, project_update_payload: ProjectUpdate) -> ProjectResponse:
    print("update_project service function runs")

    try:
        # Get only non-None values to update
        project_update_data = {k: v for k, v in project_update_payload.model_dump().items() if v is not None}

        # when there is no data to update with empty project_update_data dict
        if not project_update_data:
            # If nothing to update, just return the current project
            return await get_project_by_id(supabase, project_id, user_id)

        if project_update_data["name"]:
            project_update_data["avatar_letter"] = getProjectAvatarLetter(project_update_data["name"])

        project_update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        result = await supabase.table("projects").update(project_update_data).eq("id", str(project_id)).execute()

        if not result.data:
            raise DataBaseError(error_detail_message="Project update failed")

        return ProjectResponse(**result.data[0])

    except DataBaseError:
        raise
    except Exception as e:
        print(traceback.format_exc())
        print("GeneralServerError occurred:", str(e))
        raise GeneralServerError(error_detail_message="Something went wrong from our side. Please try again later.")
