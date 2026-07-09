"""
Study progress API router.

Endpoints:
- POST /api/v1/study/progress — record a single study action result
- GET  /api/v1/study/progress — retrieve aggregated stats for a user
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from apps.api.services.database import get_session_context
from apps.api.models.study_progress import StudyProgress

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/study", tags=["study"])


# === REQUEST/RESPONSE MODELS ===


class ProgressRecordCreate(BaseModel):
    """Request body for recording a single study action."""

    hand: str = Field(..., description="Hand string (e.g., 'AA', 'AKs')", max_length=10)
    position: str = Field(..., description="Position (e.g., 'UTG', 'BTN')", max_length=10)
    stack_depth: int = Field(..., ge=0, le=10000, description="Stack depth in big blinds")
    action_chosen: str = Field(..., max_length=50, description="Action the user selected")
    action_gto: str = Field(..., max_length=50, description="GTO-recommended action")
    correct: bool = Field(..., description="Whether the user's action matches GTO")
    user_id: str = Field(
        "anonymous", description="User identifier from X-User-Id header or default"
    )


class PositionStats(BaseModel):
    """Accuracy stats broken down by position."""

    position: str
    total: int
    correct: int
    accuracy: float


class ActionTypeStats(BaseModel):
    """Accuracy stats broken down by action type."""

    action_type: str
    total: int
    correct: int
    accuracy: float


class RecentSession(BaseModel):
    """A single session summary (grouped by date)."""

    date: str
    total: int
    correct: int
    accuracy: float


class ProgressStatsResponse(BaseModel):
    """Aggregated progress statistics response."""

    user_id: str
    total_hands: int
    correct_hands: int
    overall_accuracy: float
    current_streak: int
    best_streak: int
    by_position: List[PositionStats]
    by_action: List[ActionTypeStats]
    recent_sessions: List[RecentSession]
    last_week: List[Dict[str, Any]]


# === ENDPOINTS ===


@router.post("/progress", status_code=201)
async def record_progress(record: ProgressRecordCreate):
    """Record a single study action result."""
    async with get_session_context() as session:
        entry = StudyProgress(
            user_id=record.user_id,
            hand=record.hand,
            position=record.position,
            stack_depth=record.stack_depth,
            action_chosen=record.action_chosen,
            action_gto=record.action_gto,
            correct=record.correct,
        )
        session.add(entry)
        await session.flush()
        return {
            "id": entry.id,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        }


@router.get("/progress")
async def get_progress(
    user_id: str = Query(..., description="User identifier"),
):
    """Get aggregated study progress stats for a user."""
    if not user_id or user_id.strip() == "":
        raise HTTPException(status_code=400, detail="user_id is required")

    async with get_session_context() as session:
        # Total stats
        total_q = (
            select(func.count()).select_from(StudyProgress).where(StudyProgress.user_id == user_id)
        )
        correct_q = (
            select(func.count())
            .select_from(StudyProgress)
            .where(StudyProgress.user_id == user_id, StudyProgress.correct.is_(True))
        )
        total = (await session.execute(total_q)).scalar() or 0
        correct = (await session.execute(correct_q)).scalar() or 0
        overall_accuracy = round(correct / total, 4) if total > 0 else 0.0

        # By position
        pos_q = (
            select(
                StudyProgress.position,
                func.count().label("total"),
                func.sum(text("case when correct then 1 else 0 end")).label("correct"),
            )
            .where(StudyProgress.user_id == user_id)
            .group_by(StudyProgress.position)
        )
        pos_rows = (await session.execute(pos_q)).all()
        by_position = [
            PositionStats(
                position=row.position,
                total=row.total,
                correct=row.correct or 0,
                accuracy=round((row.correct or 0) / row.total, 4) if row.total > 0 else 0.0,
            )
            for row in pos_rows
        ]

        # By action type (extract base action from action_chosen)
        # We store action_chosen as-is, group by it
        act_q = (
            select(
                StudyProgress.action_chosen,
                func.count().label("total"),
                func.sum(text("case when correct then 1 else 0 end")).label("correct"),
            )
            .where(StudyProgress.user_id == user_id)
            .group_by(StudyProgress.action_chosen)
        )
        act_rows = (await session.execute(act_q)).all()
        by_action = [
            ActionTypeStats(
                action_type=row.action_chosen,
                total=row.total,
                correct=row.correct or 0,
                accuracy=round((row.correct or 0) / row.total, 4) if row.total > 0 else 0.0,
            )
            for row in act_rows
        ]

        # Recent sessions (grouped by date)
        date_q = (
            select(
                func.date(StudyProgress.created_at).label("date"),
                func.count().label("total"),
                func.sum(text("case when correct then 1 else 0 end")).label("correct"),
            )
            .where(StudyProgress.user_id == user_id)
            .group_by(func.date(StudyProgress.created_at))
            .order_by(func.date(StudyProgress.created_at).desc())
            .limit(30)
        )
        date_rows = (await session.execute(date_q)).all()
        recent_sessions = [
            RecentSession(
                date=str(row.date),
                total=row.total,
                correct=row.correct or 0,
                accuracy=round((row.correct or 0) / row.total, 4) if row.total > 0 else 0.0,
            )
            for row in date_rows
        ]

        # Last 7 days breakdown for chart
        last_week_q = (
            select(
                func.date(StudyProgress.created_at).label("date"),
                func.count().label("total"),
                func.sum(text("case when correct then 1 else 0 end")).label("correct"),
            )
            .where(
                StudyProgress.user_id == user_id,
                StudyProgress.created_at >= func.datetime("now", "-7 days", "localtime")
                if "sqlite" in str(session.bind.url)
                else StudyProgress.created_at >= func.now() - text("interval '7 days'"),
            )
            .group_by(func.date(StudyProgress.created_at))
            .order_by(func.date(StudyProgress.created_at))
        )
        try:
            week_rows = (await session.execute(last_week_q)).all()
            last_week = [
                {"date": str(row.date), "total": row.total, "correct": row.correct or 0}
                for row in week_rows
            ]
        except Exception:
            last_week = []

        # Compute streaks from raw records ordered by time
        # Load all records ordered by created_at to figure streak
        streak_q = (
            select(StudyProgress.correct, StudyProgress.created_at)
            .where(StudyProgress.user_id == user_id)
            .order_by(StudyProgress.created_at.asc())
        )
        streak_rows = (await session.execute(streak_q)).all()

        current_streak = 0
        best_streak = 0
        # Count from the end backwards for current streak
        if streak_rows:
            # Build session groups (any records within 2 hours of each other)
            sessions: List[List[bool]] = []
            current_session: List[bool] = [streak_rows[0].correct]
            for i in range(1, len(streak_rows)):
                prev_ts = streak_rows[i - 1].created_at
                curr_ts = streak_rows[i].created_at
                if prev_ts and curr_ts:
                    diff = abs((curr_ts - prev_ts).total_seconds())
                    if diff > 7200:  # 2 hours gap = new session
                        sessions.append(current_session)
                        current_session = []
                current_session.append(streak_rows[i].correct)
            sessions.append(current_session)

            # Streak = consecutive correct answers across sessions
            # Count from most recent backwards
            streak_count = 0
            for session_records in reversed(sessions):
                for is_correct in reversed(session_records):
                    if is_correct:
                        streak_count += 1
                    else:
                        streak_count = 0  # Wrong answer resets streak
                # Don't reset on session boundary — streak persists across sessions
            current_streak = streak_count

            # Best streak = scan forward
            scan_count = 0
            for session_records in sessions:
                for is_correct in session_records:
                    if is_correct:
                        scan_count += 1
                        best_streak = max(best_streak, scan_count)
                    else:
                        scan_count = 0

        return ProgressStatsResponse(
            user_id=user_id,
            total_hands=total,
            correct_hands=correct,
            overall_accuracy=overall_accuracy,
            current_streak=current_streak,
            best_streak=best_streak,
            by_position=by_position,
            by_action=by_action,
            recent_sessions=recent_sessions,
            last_week=last_week,
        )
