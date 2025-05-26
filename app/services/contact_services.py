from app.models.contact_models import ContactCreate, ContactUpdate, ContactResponse, ContactDeletionResponse
from typing import List
from uuid import UUID
from supabase._async.client import AsyncClient
from app.custom_error import DataBaseError, GeneralServerError, UserAuthError
import traceback
from datetime import datetime, timezone


async def create_contact(supabase: AsyncClient, new_contact_payload: ContactCreate, user_id: UUID) -> ContactResponse:
    """
    Create a new contact for a specific channel and project.
    Verifies that the channel belongs to a project owned by the user.
    """
    print("create_contact service function runs")
    try:
        # Verify channel belongs to user's project
        channel_verification_result = await supabase.rpc(
            "get_channel_with_user_verification", {"channel_id_param": str(new_contact_payload.channel_id), "user_id_param": str(user_id)}
        ).execute()

        if not channel_verification_result.data:
            raise UserAuthError(error_detail_message="Channel not found or access denied")

        # Create contact
        contact_data = new_contact_payload.model_dump()
        contact_data["channel_id"] = str(contact_data["channel_id"])
        result = await supabase.table("contacts").insert(contact_data).execute()

        if not result.data:
            raise DataBaseError(error_detail_message="Failed to create contact")

        return ContactResponse(**result.data[0])

    except (DataBaseError, UserAuthError):
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Something went wrong from our side. Please try again later.")


# ------------------------------------------------------------------------------------------------------------------------


async def get_channel_contacts(supabase: AsyncClient, channel_id: UUID, user_id: UUID) -> List[ContactResponse]:
    """
    Get all contacts for a specific channel.
    Verifies that the channel belongs to a project owned by the user.
    """
    print("get_channel_contacts service function runs")
    try:
        # Verify channel belongs to user's project
        channel_verification_result = await supabase.rpc(
            "get_channel_with_user_verification", {"channel_id_param": str(channel_id), "user_id_param": str(user_id)}
        ).execute()

        if not channel_verification_result.data:
            raise UserAuthError(error_detail_message="Channel not found or access denied")

        # Get contacts
        result = await supabase.table("contacts").select("*").eq("channel_id", str(channel_id)).execute()
        return [ContactResponse(**contact) for contact in result.data]

    except UserAuthError:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Something went wrong from our side. Please try again later.")


# ------------------------------------------------------------------------------------------------------------------------


async def get_contact_by_id(supabase: AsyncClient, contact_id: UUID, user_id: UUID) -> ContactResponse:
    """
    Get a specific contact by ID.
    Verifies that the contact belongs to a channel in a project owned by the user.
    """
    print("get_contact_by_id service function runs")
    try:
        # Verify contact belongs to user's project through channel
        contact_verification_result = await supabase.rpc(
            "get_contact_with_user_verification", {"contact_id_param": str(contact_id), "user_id_param": str(user_id)}
        ).execute()

        if not contact_verification_result.data:
            raise UserAuthError(error_detail_message="Contact not found or access denied")

        return ContactResponse(**contact_verification_result.data[0])

    except UserAuthError:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Something went wrong from our side. Please try again later.")


# ------------------------------------------------------------------------------------------------------------------------


async def update_contact(supabase: AsyncClient, contact_id: UUID, user_id: UUID, contact_update: ContactUpdate) -> ContactResponse:
    """
    Update a specific contact.
    Verifies that the contact belongs to a channel in a project owned by the user.
    """
    print("update_contact service function runs")
    try:
        # Get only non-None values to update
        update_data = {k: v for k, v in contact_update.model_dump().items() if v is not None}

        if not update_data:
            # If nothing to update, just return the current contact
            return await get_contact_by_id(supabase, contact_id, user_id)

        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        result = await supabase.table("contacts").update(update_data).eq("id", str(contact_id)).execute()

        if not result.data:
            raise DataBaseError(error_detail_message="Contact update failed")

        return ContactResponse(**result.data[0])

    except (DataBaseError, UserAuthError):
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Something went wrong from our side. Please try again later.")


# ------------------------------------------------------------------------------------------------------------------------


async def delete_contact(supabase: AsyncClient, contact_id: UUID, user_id: UUID) -> ContactDeletionResponse:
    """
    Delete a specific contact.
    Verifies that the contact belongs to a channel in a project owned by the user.
    """
    print("delete_contact service function runs")
    try:
        await get_contact_by_id(supabase, contact_id, user_id)

        # Delete contact
        result = await supabase.table("contacts").delete().eq("id", str(contact_id)).execute()

        if not result.data:
            raise DataBaseError(error_detail_message="Contact deletion failed")

        return ContactDeletionResponse(status="success", status_message="Contact deleted successfully")

    except (DataBaseError, UserAuthError):
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Something went wrong from our side. Please try again later.")
