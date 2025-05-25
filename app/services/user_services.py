from app.models.user_models import UserResponse
from app.custom_error import DataBaseError, GeneralServerError
from uuid import UUID
import traceback
import json
from fastapi import Request
from supabase._async.client import AsyncClient


# this handles the user creation and deletion event from the Clerk webhook post request
async def manage_user_from_clerk(request: Request, supabase: AsyncClient) -> dict:
    print("manage_user_from_clerk service function runs")

    try:
        clerk_webhook_request_payload = await request.json()

        event_type = clerk_webhook_request_payload.get("type")
        clerk_user_data = clerk_webhook_request_payload.get("data", {})

        if event_type == "user.created":
            new_user_data = {
                "clerk_id": clerk_user_data.get("id"),
                "email": clerk_user_data.get("email_addresses", [{}])[0].get("email_address", ""),
                "first_name": clerk_user_data.get("first_name", ""),
                "last_name": clerk_user_data.get("last_name", ""),
            }

            result = await supabase.table("users").insert(new_user_data).execute()

            if not result.data:
                raise DataBaseError(error_detail_message="Failed to create user")

            return {"status": "success", "message": "User created"}

        elif event_type == "user.deleted":
            clerk_user_id = clerk_user_data.get("id")
            await supabase.table("users").delete().eq("clerk_id", clerk_user_id).execute()

            return {"status": "success", "message": "User deleted"}

        else:
            return {"status": "ignored", "message": "Event type not handled"}

    except DataBaseError:
        print(traceback.format_exc())
        raise

    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Something went wrong from our side. Please try again later.")


# ---------------------------------------------------------------------------------------------------------------------------


async def get_user_by_clerk_id(supabase: AsyncClient, clerk_id: str) -> UserResponse:
    print("get_user_by_clerk_id function runs")

    try:
        result = await supabase.table("users").select("*").eq("clerk_id", clerk_id).execute()

        if not result.data:
            raise DataBaseError(error_detail_message="User not found")

        return UserResponse(**result.data[0])

    except DataBaseError:
        print(traceback.format_exc())
        raise

    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Something went wrong from our side. Please try again later.")


# ---------------------------------------------------------------------------------------------------------------------------


async def get_user_by_id(supabase: AsyncClient, user_id: UUID) -> UserResponse:
    print("get_user_by_id service function runs")

    try:
        result = await supabase.table("users").select("*").eq("id", str(user_id)).execute()

        if not result.data:
            raise DataBaseError(error_detail_message="User not found")

        return UserResponse(**result.data[0])

    except DataBaseError:
        print(traceback.format_exc())
        raise

    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Something went wrong from our side. Please try again later.")
