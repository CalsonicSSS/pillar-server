from typing import Dict, Any
import traceback
from uuid import UUID
from supabase._async.client import AsyncClient
from app.custom_error import DataBaseError, GeneralServerError, UserOauthError
from app.services.user_oauth_credential_services import get_user_oauth_credentials_by_channel_type, update_user_oauth_credentials_by_channel_type
from app.utils.gmail.gmail_watch_helpers import start_gmail_watch, stop_gmail_watch, is_gmail_watch_expired
from app.utils.generals import logger


async def start_gmail_user_watch(supabase: AsyncClient, user_id: UUID) -> Dict[str, Any]:
    """
    Start Gmail watch for a specific user.

    Args:
        supabase: Supabase client
        user_id: ID of the user to start watching

    Returns:
        Dictionary with watch setup results
    """
    print("start_gmail_user_watch service function runs")
    try:
        # Get user's Gmail OAuth credentials
        user_gmail_credentials = await get_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail")

        if not user_gmail_credentials:
            raise UserOauthError(error_detail_message="No Gmail OAuth credentials found for user")

        user_gmail_oauth_data = user_gmail_credentials["oauth_data"]

        # Check if watch is already active and not expired
        existing_watch_expiration = user_gmail_oauth_data.get("watch_info", {}).get("expiration")
        if existing_watch_expiration and not is_gmail_watch_expired(existing_watch_expiration):
            print(f"Gmail watch already active for user {user_id}")
            return {"status": "already_active", "message": "Gmail watch is already active and not expired", "expiration": existing_watch_expiration}

        # Start Gmail watch
        watch_result = start_gmail_watch(user_gmail_oauth_data)

        # Update OAuth data with watch information
        user_gmail_oauth_data["watch_info"] = {
            "expiration": watch_result["expiration"],
            "topic_name": watch_result["topic_name"],
            "starting_history_id": watch_result["history_id"],
        }

        # Update OAuth data with new the historyId from watch response
        user_gmail_oauth_data["user_info"]["historyId"] = watch_result["history_id"]

        # Save updated user gmail OAuth data
        await update_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail", user_gmail_oauth_data)

        return {
            "status": "success",
            "message": "Gmail watch started successfully for the user",
            "history_id": watch_result["history_id"],
            "expiration": watch_result["expiration"],
            "user_id": str(user_id),
        }

    except (DataBaseError, UserOauthError):
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message=f"Failed to start Gmail watch: {str(e)}")


async def stop_gmail_user_watch(supabase: AsyncClient, user_id: UUID) -> Dict[str, Any]:
    """
    Stop Gmail watch for a specific user.

    Args:
        supabase: Supabase client
        user_id: ID of the user to stop watching

    Returns:
        Dictionary with stop results
    """
    print("stop_gmail_user_watch service function runs")
    try:
        # Get user's Gmail OAuth credentials
        user_gmail_credentials = await get_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail")

        if not user_gmail_credentials:
            raise UserOauthError(error_detail_message="No Gmail OAuth credentials found for user")

        user_gmail_oauth_data = user_gmail_credentials["oauth_data"]

        # Stop Gmail watch
        stop_gmail_watch(user_gmail_oauth_data)

        # Remove watch information from OAuth data
        if "watch_info" in user_gmail_oauth_data:
            del user_gmail_oauth_data["watch_info"]

        # Save updated OAuth data
        await update_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail", user_gmail_oauth_data)

        return {"status": "success", "message": "Gmail watch stopped successfully", "user_id": str(user_id)}

    except (DataBaseError, UserOauthError):
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message=f"Failed to stop Gmail watch: {str(e)}")


async def check_and_renew_gmail_user_watch(supabase: AsyncClient, user_id: UUID) -> Dict[str, Any]:
    """
    Check if Gmail watch is expired or expiring soon, and renew if necessary.

    Args:
        supabase: Supabase client
        user_id: ID of the user to check

    Returns:
        Dictionary with renewal results
    """
    print("check_and_renew_gmail_user_watch service function runs")
    try:
        # Get user's Gmail OAuth credentials
        user_gmail_credentials = await get_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail")

        if not user_gmail_credentials:
            return {"status": "no_credentials", "message": "No Gmail credentials found"}

        user_gmail_oauth_data = user_gmail_credentials["oauth_data"]
        user_gmail_watch_info = user_gmail_oauth_data.get("watch_info", {})

        if not user_gmail_watch_info or "expiration" not in user_gmail_watch_info:
            # No watch set up, start one
            return await start_gmail_user_watch(supabase, user_id)

        # Check if watch is expired or expiring soon
        if is_gmail_watch_expired(user_gmail_watch_info["expiration"], buffer_hours=24):  # Renew 24 hours before expiration
            print(f"Gmail watch expiring soon for user {user_id}, renewing...")

            # Stop current watch first
            try:
                stop_gmail_watch(user_gmail_oauth_data)
            except Exception as e:
                print(f"Error stopping watch (continuing anyway): {str(e)}")

            # Start new watch
            watch_result = start_gmail_watch(user_gmail_oauth_data)

            # Update OAuth data with new watch information
            user_gmail_oauth_data["watch_info"] = {
                "expiration": watch_result["expiration"],
                "topic_name": watch_result["topic_name"],
                "starting_history_id": watch_result["history_id"],
            }

            user_gmail_oauth_data["user_info"]["historyId"] = watch_result["history_id"]

            # Save updated OAuth data
            await update_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail", user_gmail_oauth_data)

            return {
                "status": "renewed",
                "message": "Gmail watch renewed successfully",
                "expiration": watch_result["expiration"],
                "user_id": str(user_id),
            }

        return {
            "status": "active",
            "message": "Gmail watch is active and not expiring soon",
            "expiration": user_gmail_watch_info["expiration"],
            "user_id": str(user_id),
        }

    except DataBaseError:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message=f"Failed to check/renew Gmail watch: {str(e)}")


# ###################################################################################################################


async def schedule_gmail_watch_renewals(supabase: AsyncClient) -> None:
    """
    Scheduled job to check and renew expiring Gmail watches.
    This function should be run daily to ensure continuous monitoring.

    Args:
        supabase: Supabase client
    """

    logger.info("Running scheduled Gmail watch renewals check...")

    try:
        # Query all Gmail OAuth credentials
        oauth_credentials_result = await supabase.table("user_oauth_credentials").select("*").eq("channel_type", "gmail").execute()

        if not oauth_credentials_result.data:
            logger.info("No Gmail OAuth credentials found, nothing to renew")
            return

        renewal_count = 0
        error_count = 0

        # Check each credential for watch expiration
        for credential in oauth_credentials_result.data:
            try:
                user_id = credential.get("user_id")
                oauth_data = credential.get("oauth_data", {})
                watch_info = oauth_data.get("watch_info", {})

                # Skip if no watch is set up
                if not watch_info or "expiration" not in watch_info:
                    logger.info(f"No watch info for user {user_id}, skipping")
                    continue

                # Check if watch is expiring within 24 hours
                expiration = watch_info.get("expiration")
                if is_gmail_watch_expired(expiration, buffer_hours=24):
                    logger.info(f"Watch for user {user_id} expiring soon, renewing...")

                    # Renew the watch
                    renewal_result = await check_and_renew_gmail_user_watch(supabase, UUID(user_id))

                    if renewal_result.get("status") == "renewed":
                        renewal_count += 1
                        logger.info(f"Successfully renewed watch for user {user_id}")
                    else:
                        logger.info(f"Watch renewal skipped for user {user_id}: {renewal_result.get('message')}")

            except Exception as e:
                error_count += 1
                logger.error(f"Error checking/renewing watch for credential {credential.get('id')}: {str(e)}")
                logger.error(traceback.format_exc())
                continue

        logger.info(f"Gmail watch renewal completed. Renewed: {renewal_count}, Errors: {error_count}")

    except Exception as e:
        logger.error(f"Error in Gmail watch renewal scheduler: {str(e)}")
        logger.error(traceback.format_exc())
