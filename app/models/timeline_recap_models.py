from pydantic import BaseModel
from typing import Optional, Dict, List, Literal
from datetime import datetime, date
from uuid import UUID


class RecapSummaryBase(BaseModel):
    project_id: UUID
    summary_type: Literal["daily", "weekly"]
    start_date: datetime
    end_date: datetime
    content: str  # Summary text


class RecapSummaryCreate(RecapSummaryBase):
    pass


class RecapSummaryResponse(RecapSummaryBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class TimelineRecapResponse(BaseModel):
    recent_activity: List[RecapSummaryResponse]  # Past 3 days
    past_2_weeks: List[RecapSummaryResponse]  # Past 2 weeks
