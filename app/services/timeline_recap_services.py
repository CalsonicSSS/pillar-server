from typing import Dict, List, Any, Optional
from uuid import UUID
from datetime import datetime, timedelta, timezone
import traceback
from supabase._async.client import AsyncClient
from app.custom_error import DataBaseError, GeneralServerError, UserAuthError
from app.models.timeline_recap_models import (
    RecapSummaryResponse,
    TimelineRecapResponse,
    TimelineRecapDataStructureCreateResponse,
    TimelineRecapSummaryGenResponse,
)
from app.utils.llm.timeline_recap_llm_helpers import generate_weekly_summary, generate_daily_summary
from app.utils.generals import logger
from app.services.user_oauth_credential_services import get_user_oauth_credentials_by_channel_type


async def get_project_timeline_recap(supabase: AsyncClient, project_id: UUID, user_id: UUID) -> TimelineRecapResponse:
    """
    Get the timeline recap for a specific project.
    Returns both recent activity (past 3 days) and past 4 weeks summaries.
    """
    print("get_project_timeline_recap service function runs")
    try:
        # First, verify the project belongs to the user
        project_result = await supabase.table("projects").select("id").eq("id", str(project_id)).eq("user_id", str(user_id)).execute()

        if not project_result.data:
            raise UserAuthError(error_detail_message="Project not found or access denied")

        # Get recent activity (daily summaries for past 3 days)
        recent_activity_result = (
            await supabase.table("communication_timeline_recap")
            .select("*")
            .eq("project_id", str(project_id))
            .eq("summary_type", "daily")
            .order("start_date", desc=True)
            .limit(3)
            .execute()
        )

        # Get past 4 weeks activity (weekly summaries)
        past_weeks_result = (
            await supabase.table("communication_timeline_recap")
            .select("*")
            .eq("project_id", str(project_id))
            .eq("summary_type", "weekly")
            .order("start_date", desc=True)
            .limit(2)
            .execute()
        )

        # Convert to response objects
        recent_activity = [RecapSummaryResponse(**summary) for summary in recent_activity_result.data]
        past_4_weeks = [RecapSummaryResponse(**summary) for summary in past_weeks_result.data]

        return TimelineRecapResponse(recent_activity=recent_activity, past_4_weeks=past_4_weeks)

    except UserAuthError:
        raise
    except Exception as e:
        print(traceback.format_exc())
        print("get_project_timeline_recap error occurred:", str(e))
        raise GeneralServerError(error_detail_message="Failed to retrieve timeline recap")


# ----------------------------------------------------------------------------------------------------------------------------------


# This function is to create 5 definite entries (3 daily + 2 weekly) as placeholder data structure in the database
# this function should be fully AUTOMATICALLY called when a new project is created by user without user intervention
# this sets up the initial data structure for the timeline recap for later "first-time" initialization and sheduled daily / weekly generation
async def initialize_project_timeline_recap_data_structure(
    supabase: AsyncClient, project_id: UUID, user_id: UUID
) -> TimelineRecapDataStructureCreateResponse:
    """
    Generate initial timeline recap data_structure for a project with 8:00am UTC as the daily boundary for the very first time only.
    """
    print("initialize_project_timeline_recap_data_structure service function runs")
    try:
        # Verify project and get start date
        project_result = await supabase.table("projects").select("id, start_date").eq("id", str(project_id)).eq("user_id", str(user_id)).execute()

        if not project_result.data:
            raise UserAuthError(error_detail_message="Project not found or access denied")

        project_start_date = datetime.fromisoformat(project_result.data[0]["start_date"])
        print("Project start date:", project_start_date)

        # Check if recap already exists
        existing_project_timeline_recap = (
            await supabase.table("communication_timeline_recap").select("id").eq("project_id", str(project_id)).limit(1).execute()
        )

        if existing_project_timeline_recap.data:
            return TimelineRecapDataStructureCreateResponse(
                status="error",
                status_message="Timeline recap data structure already exists for this project",
            )

        now_utc = datetime.now(timezone.utc)
        today_8am_utc = now_utc.replace(hour=8, minute=0, second=0, microsecond=0)

        if now_utc >= today_8am_utc:
            end_of_first_date = today_8am_utc + timedelta(days=1)
        else:
            end_of_first_date = today_8am_utc

        start_of_first_date = end_of_first_date - timedelta(days=1)

        # Generate daily summaries
        daily_summaries = []

        # First day (most recent period)
        daily_summaries.append(
            {
                "project_id": str(project_id),
                "summary_type": "daily",
                "start_date": start_of_first_date.isoformat(),
                "end_date": end_of_first_date.isoformat(),
                "content": "To be summarized" if end_of_first_date >= project_start_date else "Unavailable",
            }
        )

        # Previous 2 days (full 24-hour per period)
        for day_offset in range(1, 3):
            day_end = start_of_first_date - timedelta(days=day_offset - 1)
            day_start = day_end - timedelta(days=1)

            daily_summaries.append(
                {
                    "project_id": str(project_id),
                    "summary_type": "daily",
                    "start_date": day_start.isoformat(),
                    "end_date": day_end.isoformat(),
                    "content": "To be summarized" if day_end >= project_start_date else "Unavailable",
                }
            )

        # Generate weekly summaries based on the same reference day
        weekly_summaries = []

        monday_this_week_8am_utc = (now_utc - timedelta(days=now_utc.weekday())).replace(hour=8, minute=0, second=0, microsecond=0)

        if now_utc < monday_this_week_8am_utc:
            start_of_first_week = monday_this_week_8am_utc - timedelta(days=7)
        else:
            start_of_first_week = monday_this_week_8am_utc

        end_of_first_week = start_of_first_week + timedelta(days=7)

        weekly_summaries.append(
            {
                "project_id": str(project_id),
                "summary_type": "weekly",
                "start_date": start_of_first_week.isoformat(),
                "end_date": end_of_first_week.isoformat(),
                "content": "To be summarized" if end_of_first_week >= project_start_date else "Unavailable",
            }
        )

        # Previous 1 week (full 7-day per period)
        for week_offset in range(1, 2):
            week_end = start_of_first_week - timedelta(days=(week_offset - 1) * 7)
            week_start = week_end - timedelta(days=7)

            weekly_summaries.append(
                {
                    "project_id": str(project_id),
                    "summary_type": "weekly",
                    "start_date": week_start.isoformat(),
                    "end_date": week_end.isoformat(),
                    "content": "To be summarized" if week_end >= project_start_date else "Unavailable",
                }
            )

        # Insert all summaries
        all_summaries = daily_summaries + weekly_summaries
        result = await supabase.table("communication_timeline_recap").insert(all_summaries).execute()

        if not result.data:
            raise DataBaseError(error_detail_message="Failed to create timeline recap")

        return TimelineRecapDataStructureCreateResponse(
            status="success",
            status_message="Timeline recap element structure initialized successfully",
        )

    except (DataBaseError, UserAuthError):
        raise
    except Exception as e:
        print(traceback.format_exc())
        print("something went wrong when initialize_project_timeline_recap")
        raise GeneralServerError(error_detail_message="Failed to initialize timeline recap")


# ------------------------------------------------------------------------------------------------------------------------------------------


# this is the function that actually does the LLM summarization for EACH OF ALL fetched recap elements WITHIN A SPECIFIC PROJECT for only the "To be summarized" ones
# Only after initialization, can "generate_to_be_summarized_timeline_recap_summaries" be meaningfully called afterwards (This sequence is critical)
async def generate_to_be_summarized_timeline_recap_summaries(
    supabase: AsyncClient, project_id: UUID, user_id: UUID
) -> TimelineRecapSummaryGenResponse:
    print("generate_to_be_summarized_timeline_recap_summaries service runs")
    try:
        # First, verify the project belongs to the user
        project_result = (
            await supabase.table("projects")
            .select("id, start_date, project_context_detail")
            .eq("id", str(project_id))
            .eq("user_id", str(user_id))
            .execute()
        )

        # so far we will only get the user's own gmail channel identify only
        # we will later make this dynamic to include all possible user identifies from all different channels
        target_user_gmail_oauth_credentials = await get_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail")
        target_user_gmail_address = target_user_gmail_oauth_credentials["oauth_data"]["user_info"]["emailAddress"]
        user_identifies = f"gmail: {target_user_gmail_address}"

        if not project_result.data:
            raise UserAuthError(error_detail_message="Project not found or access denied")

        project_context = project_result.data[0].get("project_context_detail", "")

        generated_count = 0

        # find all timeline recap element(s) data placeholder to be summarized within the whole project scope for only the "To be summarized" ones
        project_all_timeline_recap_elements = (
            await supabase.table("communication_timeline_recap")
            .select("*")
            .eq("project_id", str(project_id))
            .eq("content", "To be summarized")
            .execute()
        )
        if not project_all_timeline_recap_elements.data:
            return TimelineRecapSummaryGenResponse(
                status="error",
                status_message="No timeline recap elements to summarize found for this project",
            )

        # Process each timeline recap element summary content
        for recap_element in project_all_timeline_recap_elements.data:
            recap_element_id = recap_element["id"]
            recap_element_type = recap_element["summary_type"]
            recap_element_start_date = datetime.fromisoformat(recap_element["start_date"])
            recap_element_end_date = datetime.fromisoformat(recap_element["end_date"])

            # filter messages within this date time range of this summary-recap-element within this specific project
            recap_element_time_range_filtered_msgs = await supabase.rpc(
                "get_messages_with_filters",
                {
                    "user_id_param": str(user_id),
                    "project_id_param": str(project_id),
                    "channel_id_param": None,  # All channels
                    "contact_id_param": None,  # All contacts
                    "thread_id_param": None,  # All possible threads
                    "start_date_param": recap_element_start_date.isoformat(),
                    "end_date_param": recap_element_end_date.isoformat(),
                    "is_read_param": None,  # Both read and unread
                    "is_from_contact_param": None,  # Both from user and contacts
                    "limit_param": 200,  # Reasonable limit for summarization
                    "offset_param": 0,
                },
            ).execute()

            # Generate summary based on type for this specific recap element
            if recap_element_type == "daily":
                recap_element_summary_content = await generate_daily_summary(
                    start_date=recap_element_start_date,
                    messages=recap_element_time_range_filtered_msgs.data,  # can be empty list
                    project_context=project_context,
                    user_identifies=user_identifies,
                )
            else:  # weekly
                recap_element_summary_content = await generate_weekly_summary(
                    start_date=recap_element_start_date,
                    end_date=recap_element_end_date,
                    messages=recap_element_time_range_filtered_msgs.data,  # can be empty list
                    project_context=project_context,
                    user_identifies=user_identifies,
                )

            # Update the target timeline recap element with summarized content in the database
            await supabase.table("communication_timeline_recap").update(
                {
                    "content": recap_element_summary_content,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", recap_element_id).execute()

            generated_count += 1

        return TimelineRecapSummaryGenResponse(
            status="success",
            status_message=f"Successfully generated {generated_count} summaries for project {project_id}",
        )

    except UserAuthError:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise GeneralServerError(error_detail_message="Failed to generate timeline recap summaries")


# ######################################################################################################################################################
# scheduler service functions


# this is on the whole app's projects level from all users
async def schedule_daily_recaps_update(supabase: AsyncClient) -> None:
    """
    Daily update for all projects' timeline recaps.
    This function runs at 8:00am UTC daily and updates the most recent daily summary for each project.
    """
    logger.info("Running scheduled daily recaps update...")

    try:
        # Get all projects cross the app
        active_projects_result = await supabase.table("projects").select("id, user_id, project_context_detail").eq("status", "active").execute()

        if not active_projects_result.data:
            logger.info("No active projects found for daily recap update")
            return

        # Get current time (8:00am UTC of the current day)
        now_utc = datetime.now(timezone.utc)
        today_8am_utc = now_utc.replace(hour=8, minute=0, second=0, microsecond=0)

        # Calculate date range for yesterday
        end_date = today_8am_utc
        start_date = end_date - timedelta(days=1)

        # Update count
        updated_count = 0

        # Process each project
        for active_project in active_projects_result.data:
            project_id = active_project["id"]
            user_id = active_project["user_id"]
            project_context = active_project.get("project_context_detail", "")

            # so far we will only get the user's own gmail channel identify only
            # we will later make this dynamic to include all possible user identifies from all different channels
            target_user_gmail_oauth_credentials = await get_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail")
            target_user_gmail_address = target_user_gmail_oauth_credentials["oauth_data"]["user_info"]["emailAddress"]
            user_identifies = f"gmail: {target_user_gmail_address}"

            try:
                # Get existing timeline recap structure
                project_existing_daily_recaps = (
                    await supabase.table("communication_timeline_recap")
                    .select("*")
                    .eq("project_id", project_id)
                    .eq("summary_type", "daily")
                    .order("start_date", desc=True)
                    .execute()
                )

                if not project_existing_daily_recaps.data:
                    logger.warning(f"Incomplete daily recap structure for project {project_id}, skipping")
                    continue

                # Get the oldest daily recap to update it to latest (this is important as this simulates the rolling window)
                oldest_recap = min(project_existing_daily_recaps.data, key=lambda x: datetime.fromisoformat(x["start_date"]))
                oldest_recap_id = oldest_recap["id"]

                # Get messages from the date range
                new_day_range_filtered_messages = await supabase.rpc(
                    "get_messages_with_filters",
                    {
                        "user_id_param": user_id,
                        "project_id_param": project_id,
                        "channel_id_param": None,  # All channels
                        "contact_id_param": None,  # All contacts
                        "thread_id_param": None,  # All threads
                        "start_date_param": start_date.isoformat(),
                        "end_date_param": end_date.isoformat(),
                        "is_read_param": None,  # Both read and unread
                        "is_from_contact_param": None,  # Both from user and contacts
                        "limit_param": 200,  # Reasonable limit for summarization
                        "offset_param": 0,
                    },
                ).execute()

                # Generate summary
                if new_day_range_filtered_messages.data:
                    summary = await generate_daily_summary(
                        start_date=start_date,
                        messages=new_day_range_filtered_messages.data,
                        project_context=project_context,
                        user_identifies=user_identifies,
                    )
                else:
                    summary = "• No important summary during this day."

                # Create updated daily recap content
                updated_recap = {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "content": summary,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }

                # Update the recap with the summary
                await supabase.table("communication_timeline_recap").update(updated_recap).eq("id", oldest_recap_id).execute()

                updated_count += 1

            except Exception as e:
                logger.error(f"Error updating daily recap for project {project_id}: {str(e)}")
                logger.error(traceback.format_exc())
                continue

        logger.info(f"Daily recap update completed. Updated {updated_count} projects.")

    except Exception as e:
        logger.error(f"Error in daily recap scheduler: {str(e)}")
        logger.error(traceback.format_exc())


# ------------------------------------------------------------------------------------------------------------------------


async def schedule_weekly_recaps_update(supabase: AsyncClient) -> None:
    """
    Weekly update for all projects' timeline recaps.
    This function runs at 8:00am UTC every Monday and updates the most recent weekly summary for each project.
    """
    logger.info("Running scheduled weekly recaps update...")

    try:
        # Get all projects cross the app
        active_projects_result = await supabase.table("projects").select("id, user_id, project_context_detail").eq("status", "active").execute()

        if not active_projects_result.data:
            logger.info("No projects found for weekly recap update")
            return

        # Get current time (8:00am UTC of the current Monday)
        now_utc = datetime.now(timezone.utc)
        today_8am_utc = now_utc.replace(hour=8, minute=0, second=0, microsecond=0)

        # Calculate date range for the past week
        end_date = today_8am_utc
        start_date = end_date - timedelta(days=7)

        # Update count
        updated_count = 0

        # Process each project
        for active_project in active_projects_result.data:
            project_id = active_project["id"]
            user_id = active_project["user_id"]
            project_context = active_project.get("project_context_detail", "")

            # so far we will only get the user's own gmail channel identify only
            # we will later make this dynamic to include all possible user identifies from all different channels
            target_user_gmail_oauth_credentials = await get_user_oauth_credentials_by_channel_type(supabase, user_id, "gmail")
            target_user_gmail_address = target_user_gmail_oauth_credentials["oauth_data"]["user_info"]["emailAddress"]
            user_identifies = f"gmail: {target_user_gmail_address}"

            try:
                # Get existing timeline recap structure
                project_existing_weekly_recaps = (
                    await supabase.table("communication_timeline_recap")
                    .select("*")
                    .eq("project_id", project_id)
                    .eq("summary_type", "weekly")
                    .order("start_date", desc=True)
                    .execute()
                )

                if not project_existing_weekly_recaps.data:
                    logger.warning(f"Incomplete weekly recap structure for project {project_id}, skipping")
                    continue

                # Get the oldest weekly recap to update it to latest (this is important as this simulates the rolling window)
                oldest_recap = min(project_existing_weekly_recaps.data, key=lambda x: datetime.fromisoformat(x["start_date"]))
                oldest_recap_id = oldest_recap["id"]

                # Get messages from the date range
                messages = await supabase.rpc(
                    "get_messages_with_filters",
                    {
                        "user_id_param": user_id,
                        "project_id_param": project_id,
                        "channel_id_param": None,  # All channels
                        "contact_id_param": None,  # All contacts
                        "thread_id_param": None,  # All threads
                        "start_date_param": start_date.isoformat(),
                        "end_date_param": end_date.isoformat(),
                        "is_read_param": None,  # Both read and unread
                        "is_from_contact_param": None,  # Both from user and contacts
                        "limit_param": 200,
                        "offset_param": 0,
                    },
                ).execute()

                # Generate summary
                if messages.data:
                    summary = await generate_weekly_summary(
                        start_date=start_date,
                        end_date=end_date,
                        messages=messages.data,
                        project_context=project_context,
                        user_identifies=user_identifies,
                    )
                else:
                    summary = "• No important summary during this week."

                updated_recap = {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "content": summary,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }

                # Update the recap with the summary
                await supabase.table("communication_timeline_recap").update(updated_recap).eq("id", oldest_recap_id).execute()

                updated_count += 1

            except Exception as e:
                logger.error(f"Error updating weekly recap for project {project_id}: {str(e)}")
                logger.error(traceback.format_exc())
                continue

        logger.info(f"Weekly recap update completed. Updated {updated_count} projects.")

    except Exception as e:
        logger.error(f"Error in weekly recap scheduler: {str(e)}")
        logger.error(traceback.format_exc())
