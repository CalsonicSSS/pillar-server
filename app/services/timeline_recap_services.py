from typing import Dict, List, Any, Optional
from uuid import UUID
from datetime import datetime, timedelta, timezone
import traceback
from supabase._async.client import AsyncClient
from app.custom_error import DataBaseError, GeneralServerError, UserAuthError
from app.models.timeline_recap_models import RecapSummaryCreate, RecapSummaryResponse, TimelineRecapResponse


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
            await supabase.table("communication_summaries")
            .select("*")
            .eq("project_id", str(project_id))
            .eq("summary_type", "daily")
            .order("start_date", options={"ascending": False})
            .limit(3)
            .execute()
        )

        # Get past 4 weeks activity (weekly summaries)
        past_weeks_result = (
            await supabase.table("communication_summaries")
            .select("*")
            .eq("project_id", str(project_id))
            .eq("summary_type", "weekly")
            .order("start_date", options={"ascending": False})
            .limit(4)
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


async def initialize_project_timeline_recap(supabase: AsyncClient, project_id: UUID, user_id: UUID) -> Dict[str, Any]:
    """
    Generate initial timeline recap for a project with 8:00am UTC as the daily boundary.
    """
    try:
        # Verify project and get start date
        project_result = await supabase.table("projects").select("id, start_date").eq("id", str(project_id)).eq("user_id", str(user_id)).execute()

        if not project_result.data:
            raise UserAuthError(error_detail_message="Project not found or access denied")

        project_start_date = datetime.fromisoformat(project_result.data[0]["start_date"])

        # Check if recap already exists
        existing_project_timeline_recap = (
            await supabase.table("communication_summaries").select("id").eq("project_id", str(project_id)).limit(1).execute()
        )

        if existing_project_timeline_recap.data:
            return {"status": "exists", "message": "Timeline recap already exists for this project"}

        # Current time in UTC
        now = datetime.now(timezone.utc)

        # Get the reference 8:00am boundary
        today_8am_utc = now.replace(hour=8, minute=0, second=0, microsecond=0)

        # Determine the starting reference point based on 8:00am UTC boundary
        if now < today_8am_utc:
            # Before 8am UTC, use yesterday's 8am as the reference for FIRST day boundary
            reference_day_boundary = today_8am_utc - timedelta(days=1)
        else:
            # After 8am UTC, use today's 8am as the reference day boundary
            reference_day_boundary = today_8am_utc

        # Generate daily summaries
        daily_summaries = []

        # First day (most recent period)
        daily_summaries.append(
            {
                "project_id": str(project_id),
                "summary_type": "daily",
                "start_date": reference_day_boundary.isoformat(),
                "end_date": now.isoformat(),
                "content": "No message summary" if reference_day_boundary >= project_start_date else "Unavailable",
            }
        )

        # Previous two days (full 24-hour periods)
        for day_offset in range(1, 3):
            day_end = reference_day_boundary - timedelta(days=day_offset - 1)
            day_start = day_end - timedelta(days=1)

            daily_summaries.append(
                {
                    "project_id": str(project_id),
                    "summary_type": "daily",
                    "start_date": day_start.isoformat(),
                    "end_date": day_end.isoformat(),
                    "content": "No message summary" if day_start >= project_start_date else "Unavailable",
                }
            )

        # Generate weekly summaries based on the same reference day
        weekly_summaries = []

        # First week (may be partial)
        week_end = now
        week_start = reference_day_boundary - timedelta(days=6)

        weekly_summaries.append(
            {
                "project_id": str(project_id),
                "summary_type": "weekly",
                "start_date": week_start.isoformat(),
                "end_date": week_end.isoformat(),
                "content": get_content_status(week_start, week_end, project_start_date),
            }
        )

        # Previous three weeks (full 7-day periods)
        for week_offset in range(1, 4):
            week_end = reference_day_boundary - timedelta(days=(week_offset - 1) * 7)
            week_start = week_end - timedelta(days=7)

            weekly_summaries.append(
                {
                    "project_id": str(project_id),
                    "summary_type": "weekly",
                    "start_date": week_start.isoformat(),
                    "end_date": week_end.isoformat(),
                    "content": get_content_status(week_start, week_end, project_start_date),
                }
            )

        # Insert all summaries
        all_summaries = daily_summaries + weekly_summaries
        result = await supabase.table("communication_summaries").insert(all_summaries).execute()

        if not result.data:
            raise DataBaseError(error_detail_message="Failed to create timeline recap")

        return {
            "status": "success",
            "message": "Timeline recap initialized successfully",
            "daily_count": len(daily_summaries),
            "weekly_count": len(weekly_summaries),
        }

    except (DataBaseError, UserAuthError):
        raise
    except Exception as e:
        print(traceback.format_exc())
        print("something went wrong when initialize_project_timeline_recap")
        raise GeneralServerError(error_detail_message="Failed to initialize timeline recap")


def get_content_status(start_date, end_date, project_start_date):
    """Helper function to determine the appropriate content status"""
    if start_date >= project_start_date:
        return "No message summary"
    elif end_date > project_start_date:
        return "Partial data available (project started during this period)"
    else:
        return "Unavailable"
