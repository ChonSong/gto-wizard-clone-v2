"""
Quiz API Router for GTO Wizard training mode.

Provides endpoints for:
- Quiz spot submission and GTO comparison
- Random spot selection with filters
- User stats and accuracy tracking
- Leaderboard ranking
- Spot categories and review mode
"""

import json
import logging
import random
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import cast, Float, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.database import get_session_context
from apps.api.services.quiz_models import (
    QuizSpot,
    QuizSubmission,
    UserStats,
    ReviewSpot,
)
from apps.api.services.cache import cached

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/quiz", tags=["quiz"])


# === REQUEST/RESPONSE MODELS ===


class QuizSubmitRequest(BaseModel):
    """Request model for quiz submission."""

    spot_id: str
    user_id: str
    user_name: Optional[str] = None
    selected_action: str  # "raise", "call", "fold"
    time_taken_ms: Optional[int] = None
    session_id: Optional[str] = None


class QuizSubmitResponse(BaseModel):
    """Response for quiz submission."""

    is_correct: bool
    ev_loss: float
    gto_action: str
    gto_frequency: float
    gto_ev: float
    user_accuracy: float
    current_streak: int
    points_earned: int
    total_points: int


class SpotResponse(BaseModel):
    """Response model for a quiz spot."""

    id: str
    game_type: str
    category: str
    difficulty: str
    position: str
    hero_hand: str
    board: Optional[str]
    turn: Optional[str]
    river: Optional[str]
    pot_size: int
    stack_depth: int
    gto_action: str
    gto_frequency: float
    gto_ev: float
    options: List[Dict[str, Any]]
    street: str
    explanation: Optional[str]


class UserStatsResponse(BaseModel):
    """Response model for user statistics."""

    user_id: str
    total_solves: int
    correct_count: int
    accuracy: float
    current_streak: int
    max_streak: int
    points: int
    level: int
    avg_ev_loss: float
    weak_spots: Dict[str, Any]
    accuracy_history: List[float]


class LeaderboardEntry(BaseModel):
    """Single leaderboard entry."""

    rank: int
    user_id: str
    user_name: Optional[str]
    score: int
    accuracy: float
    correct_count: int
    total_solves: int
    avg_ev_loss: float


class LeaderboardResponse(BaseModel):
    """Response for leaderboard endpoint."""

    entries: List[LeaderboardEntry]
    total_users: int
    user_rank: Optional[int] = None


class CategoriesResponse(BaseModel):
    """Response for categories endpoint."""

    categories: List[str]
    difficulties: List[str]


# === HELPER FUNCTIONS ===


async def get_or_create_user_stats(
    session: AsyncSession, user_id: str, user_name: Optional[str] = None
) -> UserStats:
    """Get or create user stats record."""
    result = await session.execute(select(UserStats).where(UserStats.user_id == user_id))
    stats = result.scalar_one_or_none()

    if not stats:
        stats = UserStats(user_id=user_id, user_name=user_name)
        session.add(stats)
        await session.flush()

    return stats


async def update_user_stats_on_answer(
    session: AsyncSession,
    stats: UserStats,
    spot: QuizSpot,
    selected_action: str,
    is_correct: bool,
    ev_loss: float,
) -> None:
    """Update user stats after an answer."""
    stats.total_solves += 1

    if is_correct:
        stats.correct_count += 1
        stats.current_streak += 1
        stats.max_streak = max(stats.max_streak, stats.current_streak)
        # Points: 10 for correct, bonus based on difficulty
        difficulty_bonus = {"beginner": 5, "intermediate": 10, "advanced": 20}.get(
            spot.difficulty, 10
        )
        stats.points += 10 + difficulty_bonus
    else:
        stats.current_streak = 0
        # Add to missed spots
        if spot.id not in stats.missed_spot_ids:
            stats.missed_spot_ids.append(spot.id)

    stats.total_ev_loss += ev_loss

    # Update weak spots tracking
    category = spot.category
    weak = dict(stats.weak_spots)
    if category not in weak:
        weak[category] = {"correct": 0, "total": 0}
    weak[category]["total"] += 1
    if is_correct:
        weak[category]["correct"] += 1
    stats.weak_spots = weak

    # Calculate level (every 500 points = 1 level)
    stats.level = (stats.points // 500) + 1

    stats.last_updated = datetime.utcnow()


# === API ENDPOINTS ===


@router.post("/submit", response_model=QuizSubmitResponse)
async def submit_quiz_answer(request: QuizSubmitRequest):
    """
    Submit a quiz answer and get GTO comparison result.

    Compares user's selected action against GTO action,
    calculates EV loss, and updates user stats.
    """
    async with get_session_context() as session:
        # Get spot
        try:
            spot_uuid = uuid.UUID(request.spot_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid spot_id format")

        result = await session.execute(select(QuizSpot).where(QuizSpot.id == spot_uuid))
        spot = result.scalar_one_or_none()

        if not spot:
            raise HTTPException(status_code=404, detail="Spot not found")

        # Compare to GTO action
        is_correct = request.selected_action.lower() == spot.gto_action.lower()

        # Calculate EV loss
        ev_loss = 0.0
        if not is_correct:
            # Find EV of selected action
            options = spot.options if isinstance(spot.options, dict) else {}
            # Handle list format by converting to dict
            if isinstance(spot.options, list):
                options = {}
                for opt in spot.options:
                    act = opt.get("action", "unknown")
                    if act not in options:
                        options[act] = []
                    options[act].append(opt)
            selected_option = None
            for action_key in ["raise", "call", "fold"]:
                if action_key in options:
                    for opt in options[action_key]:
                        if (
                            isinstance(opt, dict)
                            and opt.get("action") == request.selected_action.lower()
                        ):
                            selected_option = opt
                            break

            if selected_option and "ev" in selected_option:
                ev_loss = float(spot.gto_ev) - float(selected_option["ev"])
            else:
                # Fallback - estimate EV loss
                ev_loss = abs(float(spot.gto_ev)) * 0.3
                if request.selected_action == "fold":
                    ev_loss = abs(float(spot.gto_ev))

        # Get or create user stats
        stats = await get_or_create_user_stats(session, request.user_id, request.user_name)

        # Update stats
        await update_user_stats_on_answer(
            session, stats, spot, request.selected_action, is_correct, ev_loss
        )

        # Record submission
        submission = QuizSubmission(
            user_id=request.user_id,
            user_name=request.user_name,
            spot_id=spot.id,
            selected_action=request.selected_action,
            is_correct=is_correct,
            ev_loss=ev_loss,
            time_taken_ms=request.time_taken_ms,
            session_id=request.session_id,
        )
        session.add(submission)

        await session.commit()

        return QuizSubmitResponse(
            is_correct=is_correct,
            ev_loss=ev_loss,
            gto_action=spot.gto_action,
            gto_frequency=float(spot.gto_frequency),
            gto_ev=float(spot.gto_ev),
            user_accuracy=stats.accuracy,
            current_streak=stats.current_streak,
            points_earned=10 if is_correct else 0,
            total_points=stats.points,
        )


@router.get("/random", response_model=SpotResponse)
async def get_random_spot(
    category: Optional[str] = Query(None, description="Filter by category"),
    difficulty: Optional[str] = Query(None, description="Filter by difficulty"),
    street: Optional[str] = Query(None, description="Filter by street"),
    exclude_ids: Optional[str] = Query(None, description="Comma-separated IDs to exclude"),
):
    """
    Get a random quiz spot from the database.

    Supports filtering by category, difficulty, and street.
    Also supports avoiding recently shown spots via exclude_ids.
    """
    async with get_session_context() as session:
        query = select(QuizSpot)

        if category:
            query = query.where(QuizSpot.category == category)
        if difficulty:
            query = query.where(QuizSpot.difficulty == difficulty)
        if street:
            query = query.where(QuizSpot.street == street)

        # Exclude specific IDs
        if exclude_ids:
            try:
                exclude_uuid_list = [uuid.UUID(id.strip()) for id in exclude_ids.split(",")]
                query = query.where(~QuizSpot.id.in_(exclude_uuid_list))
            except ValueError:
                pass  # Skip invalid IDs

        # Get count
        subq = query.subquery()
        count_result = await session.execute(select(func.count()).select_from(subq))
        total_count = count_result.scalar() or 0

        if total_count == 0:
            raise HTTPException(status_code=404, detail="No spots found matching criteria")

        # Get random offset and fetch
        random_offset = random.randint(0, total_count - 1)
        result = await session.execute(query.offset(random_offset).limit(1))
        spot = result.scalar_one_or_none()

        if not spot:
            raise HTTPException(status_code=404, detail="Failed to fetch random spot")

        return SpotResponse(
            id=str(spot.id),
            game_type=spot.game_type,
            category=spot.category,
            difficulty=spot.difficulty,
            position=spot.position,
            hero_hand=spot.hero_hand,
            board=spot.board,
            turn=spot.turn,
            river=spot.river,
            pot_size=spot.pot_size,
            stack_depth=spot.stack_depth,
            gto_action=spot.gto_action,
            gto_frequency=float(spot.gto_frequency),
            gto_ev=float(spot.gto_ev),
            options=spot.options
            if isinstance(spot.options, list)
            else list(spot.options.values())[0]
            if isinstance(spot.options, dict) and spot.options
            else [],
            street=spot.street,
            explanation=spot.explanation,
        )


@router.get("/spot/{spot_id}", response_model=SpotResponse)
async def get_spot(spot_id: str):
    """Get a specific quiz spot by ID."""
    async with get_session_context() as session:
        try:
            spot_uuid = uuid.UUID(spot_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid spot_id format")

        result = await session.execute(select(QuizSpot).where(QuizSpot.id == spot_uuid))
        spot = result.scalar_one_or_none()

        if not spot:
            raise HTTPException(status_code=404, detail="Spot not found")

        return SpotResponse(
            id=str(spot.id),
            game_type=spot.game_type,
            category=spot.category,
            difficulty=spot.difficulty,
            position=spot.position,
            hero_hand=spot.hero_hand,
            board=spot.board,
            turn=spot.turn,
            river=spot.river,
            pot_size=spot.pot_size,
            stack_depth=spot.stack_depth,
            gto_action=spot.gto_action,
            gto_frequency=float(spot.gto_frequency),
            gto_ev=float(spot.gto_ev),
            options=spot.options
            if isinstance(spot.options, list)
            else list(spot.options.values())[0]
            if isinstance(spot.options, dict) and spot.options
            else [],
            street=spot.street,
            explanation=spot.explanation,
        )


@router.get("/stats/{user_id}", response_model=UserStatsResponse)
async def get_user_stats(user_id: str):
    """Get user statistics and progress."""
    async with get_session_context() as session:
        stats = await get_or_create_user_stats(session, user_id)

        return UserStatsResponse(
            user_id=stats.user_id,
            total_solves=stats.total_solves,
            correct_count=stats.correct_count,
            accuracy=stats.accuracy,
            current_streak=stats.current_streak,
            max_streak=stats.max_streak,
            points=stats.points,
            level=stats.level,
            avg_ev_loss=stats.avg_ev_loss,
            weak_spots=dict(stats.weak_spots),
            accuracy_history=list(stats.accuracy_history) if stats.accuracy_history else [],
        )


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    limit: int = Query(20, ge=1, le=100, description="Number of entries to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    user_id: Optional[str] = Query(None, description="Current user ID to show their rank"),
    period: str = Query(
        "all-time", regex="^(all-time|weekly|daily)$", description="Leaderboard time period"
    ),
):
    """Get leaderboard ranked by accuracy and solves completed."""
    async with get_session_context() as session:
        # Build base query with optional time filter
        base_select = select(
            UserStats.user_id,
            UserStats.user_name,
            UserStats.total_solves,
            UserStats.correct_count,
            UserStats.total_ev_loss,
        )

        if period == "weekly":
            # Last 7 days
            base_select = base_select.where(text("last_updated >= NOW() - INTERVAL '7 days'"))
        elif period == "daily":
            # Last 24 hours
            base_select = base_select.where(text("last_updated >= NOW() - INTERVAL '1 day'"))

        base_select = base_select.where(UserStats.total_solves >= 10)

        # Calculate accuracy in SQL
        accuracy_expr = (
            cast(UserStats.correct_count, Float) / cast(UserStats.total_solves, Float) * 100
        )

        result = await session.execute(
            select(
                UserStats.user_id,
                UserStats.user_name,
                UserStats.total_solves,
                UserStats.correct_count,
                UserStats.total_ev_loss,
                accuracy_expr.label("accuracy"),
            )
            .where(UserStats.total_solves >= 10)
            .order_by(accuracy_expr.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = result.all()

        # Get total count
        count_where = UserStats.total_solves >= 10
        if period == "weekly":
            count_where = text("last_updated >= NOW() - INTERVAL '7 days' AND total_solves >= 10")
        elif period == "daily":
            count_where = text("last_updated >= NOW() - INTERVAL '1 day' AND total_solves >= 10")

        count_result = await session.execute(
            select(func.count(UserStats.user_id)).where(count_where)
        )
        total_users = count_result.scalar() or 0

        # Build entries with ranks
        entries = []
        for i, row in enumerate(rows):
            avg_ev = (
                float(row.total_ev_loss) / float(row.total_solves) if row.total_solves > 0 else 0
            )
            entries.append(
                LeaderboardEntry(
                    rank=offset + i + 1,
                    user_id=row.user_id,
                    user_name=row.user_name,
                    score=row.correct_count * 10,  # Points based on correct answers
                    accuracy=float(row.accuracy) if hasattr(row, "accuracy") else 0,
                    correct_count=row.correct_count,
                    total_solves=row.total_solves,
                    avg_ev_loss=avg_ev,
                )
            )

        # Find user's rank if specified
        user_rank = None
        if user_id:
            rank_result = await session.execute(
                select(
                    UserStats.user_id,
                    accuracy_expr.label("_accuracy"),
                )
                .where(UserStats.total_solves >= 10)
                .order_by(accuracy_expr.desc())
            )
            all_rows = rank_result.all()
            for idx, row in enumerate(all_rows):
                if row.user_id == user_id:
                    user_rank = idx + 1
                    break

        return LeaderboardResponse(
            entries=entries,
            total_users=total_users,
            user_rank=user_rank,
        )


@router.get("/categories", response_model=CategoriesResponse)
@cached(ttl=600)
async def get_categories():
    """Get all available spot categories and difficulties."""
    async with get_session_context() as session:
        # Get distinct categories
        cat_result = await session.execute(select(QuizSpot.category).distinct())
        categories = [row[0] for row in cat_result.all()]

        # Get distinct difficulties
        diff_result = await session.execute(select(QuizSpot.difficulty).distinct())
        difficulties = [row[0] for row in diff_result.all()]

        return CategoriesResponse(
            categories=categories,
            difficulties=difficulties,
        )


@router.post("/review/{spot_id}")
async def mark_for_review(
    spot_id: str,
    user_id: str = Query(..., description="User ID"),
    mastered: bool = Query(False, description="Whether user has mastered this spot"),
):
    """Mark a spot for review mode."""
    async with get_session_context() as session:
        try:
            spot_uuid = uuid.UUID(spot_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid spot_id format")

        # Check spot exists
        spot_result = await session.execute(select(QuizSpot).where(QuizSpot.id == spot_uuid))
        spot = spot_result.scalar_one_or_none()
        if not spot:
            raise HTTPException(status_code=404, detail="Spot not found")

        # Check if already marked for review
        existing = await session.execute(
            select(ReviewSpot).where(
                ReviewSpot.user_id == user_id,
                ReviewSpot.spot_id == spot_uuid,
            )
        )
        review = existing.scalar_one_or_none()

        if review:
            review.review_count += 1
            review.last_reviewed_at = datetime.utcnow()
            review.mastered = mastered
        else:
            review = ReviewSpot(
                user_id=user_id,
                spot_id=spot_uuid,
                mastered=mastered,
            )
            session.add(review)

        await session.commit()

        return {"status": "ok", "message": "Spot marked for review"}


@router.get("/review/{user_id}")
async def get_review_spots(
    user_id: str,
    mastered_only: bool = Query(False, description="Only show not-yet-mastered spots"),
):
    """Get spots a user has marked for review."""
    async with get_session_context() as session:
        query = (
            select(ReviewSpot, QuizSpot)
            .join(QuizSpot, ReviewSpot.spot_id == QuizSpot.id)
            .where(ReviewSpot.user_id == user_id)
        )

        if mastered_only:
            query = query.where(ReviewSpot.mastered == False)

        result = await session.execute(query)
        rows = result.all()

        spots = []
        for review, spot in rows:
            spots.append(
                SpotResponse(
                    id=str(spot.id),
                    game_type=spot.game_type,
                    category=spot.category,
                    difficulty=spot.difficulty,
                    position=spot.position,
                    hero_hand=spot.hero_hand,
                    board=spot.board,
                    turn=spot.turn,
                    river=spot.river,
                    pot_size=spot.pot_size,
                    stack_depth=spot.stack_depth,
                    gto_action=spot.gto_action,
                    gto_frequency=float(spot.gto_frequency),
                    gto_ev=float(spot.gto_ev),
                    options=spot.options
                    if isinstance(spot.options, list)
                    else list(spot.options.values())[0]
                    if isinstance(spot.options, dict) and spot.options
                    else [],
                    street=spot.street,
                    explanation=spot.explanation,
                )
            )

        return {"spots": spots, "count": len(spots)}


@router.get("/missed/{user_id}")
async def get_missed_spots(user_id: str):
    """Get spots that user has gotten wrong (for review mode)."""
    async with get_session_context() as session:
        stats_result = await session.execute(select(UserStats).where(UserStats.user_id == user_id))
        stats = stats_result.scalar_one_or_none()

        if not stats or not stats.missed_spot_ids:
            return {"spots": [], "count": 0}

        # Get spots
        result = await session.execute(
            select(QuizSpot).where(QuizSpot.id.in_(stats.missed_spot_ids))
        )
        spots = result.scalars().all()

        return {
            "spots": [
                SpotResponse(
                    id=str(spot.id),
                    game_type=spot.game_type,
                    category=spot.category,
                    difficulty=spot.difficulty,
                    position=spot.position,
                    hero_hand=spot.hero_hand,
                    board=spot.board,
                    turn=spot.turn,
                    river=spot.river,
                    pot_size=spot.pot_size,
                    stack_depth=spot.stack_depth,
                    gto_action=spot.gto_action,
                    gto_frequency=float(spot.gto_frequency),
                    gto_ev=float(spot.gto_ev),
                    options=spot.options
                    if isinstance(spot.options, list)
                    else list(spot.options.values())[0]
                    if isinstance(spot.options, dict) and spot.options
                    else [],
                    street=spot.street,
                    explanation=spot.explanation,
                )
                for spot in spots
            ],
            "count": len(spots),
        }
