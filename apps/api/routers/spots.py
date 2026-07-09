"""
Community spots API router.

Provides endpoints for:
- Creating, reading, updating, deleting community spots
- Liking spots
- Forking spots to user's account
- Commenting on spots

Spots represent poker game situations (board, position, stack depth) with
associated GTO strategy data that can be shared with the community.
"""

import uuid
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.spots import CommunitySpot, SpotComment, SpotLike
from apps.api.services.database import get_session_context

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/spots", tags=["spots"])


# Pydantic models for request/response
class SpotCreate(BaseModel):
    """Request model for creating a spot."""

    title: str = Field(..., description="Spot title")
    description: Optional[str] = Field(None, description="Spot description")
    board: str = Field("", description="Board cards (e.g., 'Kd-Qh-2c')")
    board_type: str = Field("flop", description="Board type: flop, turn, river")
    position: str = Field("", description="Position: btn, sb, bb, utg, etc.")
    pot_size: float = Field(0.0, ge=0.0, description="Pot size in chips")
    stack_depth: int = Field(100, gt=0, description="Stack depth in big blinds")
    author: str = Field("anonymous", description="Author name")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")
    strategy_json: Dict[str, Any] = Field(..., description="Strategy data")


class SpotUpdate(BaseModel):
    """Request model for updating a spot."""

    title: Optional[str] = None
    description: Optional[str] = None
    board: Optional[str] = None
    board_type: Optional[str] = None
    position: Optional[str] = None
    pot_size: Optional[float] = None
    stack_depth: Optional[int] = None
    tags: Optional[List[str]] = None
    strategy_json: Optional[Dict[str, Any]] = None


class SpotCommentCreate(BaseModel):
    """Request model for creating a comment."""

    author: str = Field("anonymous", description="Author name")
    content: str = Field(..., description="Comment content")


class SpotResponse(BaseModel):
    """Response model for spot retrieval."""

    id: str
    title: str
    description: Optional[str] = None
    board: str
    board_type: str
    position: str
    pot_size: float
    stack_depth: int
    author: str
    tags: List[str] = []
    strategy_json: Dict[str, Any]
    likes: int = 0
    fork_count: int = 0
    parent_spot_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    comments_count: int = 0


class SpotListResponse(BaseModel):
    """Response model for listing spots."""

    spots: List[Dict[str, Any]]
    total: int
    offset: int
    limit: int


@router.post("", response_model=Dict[str, Any], status_code=201)
async def create_spot(request: SpotCreate) -> Dict[str, Any]:
    """
    Create a new community spot.

    A spot represents a poker game situation with strategy data
    that can be shared with the community.
    """
    async with get_session_context() as session:
        spot = CommunitySpot(
            title=request.title,
            description=request.description,
            board=request.board,
            board_type=request.board_type,
            position=request.position,
            pot_size=request.pot_size,
            stack_depth=request.stack_depth,
            author=request.author,
            tags=request.tags,
            strategy_json=request.strategy_json,
        )
        session.add(spot)
        await session.flush()
        await session.refresh(spot)

        return spot.to_dict()


@router.get("", response_model=SpotListResponse)
async def list_spots(
    board_type: Optional[str] = Query(None, description="Filter by board type"),
    position: Optional[str] = Query(None, description="Filter by position"),
    author: Optional[str] = Query(None, description="Filter by author"),
    tags: Optional[str] = Query(None, description="Comma-separated tags to filter by"),
    stack_depth_min: Optional[int] = Query(None, description="Minimum stack depth"),
    sort_by: str = Query("recent", description="Sort by: recent, popular"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Results offset"),
) -> SpotListResponse:
    """
    List community spots with optional filters.

    Supports filtering by board_type, position, author, tags, and stack_depth.
    Results can be sorted by creation date (newest first) or popularity (most likes).
    """
    async with get_session_context() as session:
        # Build query
        query = select(CommunitySpot)

        # Apply filters
        if board_type:
            query = query.where(CommunitySpot.board_type == board_type)
        if position:
            query = query.where(CommunitySpot.position == position)
        if author:
            query = query.where(CommunitySpot.author == author)
        if stack_depth_min:
            query = query.where(CommunitySpot.stack_depth >= stack_depth_min)
        if tags:
            filter_tags = tags.split(",")
            for tag in filter_tags:
                query = query.where(CommunitySpot.tags.contains([tag]))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        # Apply sorting
        if sort_by == "popular":
            query = query.order_by(CommunitySpot.likes_count.desc())
        else:
            query = query.order_by(CommunitySpot.created_at.desc())

        # Apply pagination
        query = query.offset(offset).limit(limit)

        # Execute
        result = await session.execute(query)
        spots = result.scalars().all()

        return SpotListResponse(
            spots=[spot.to_dict() for spot in spots],
            total=total,
            offset=offset,
            limit=limit,
        )


@router.get("/{spot_id}", response_model=Dict[str, Any])
async def get_spot(spot_id: str) -> Dict[str, Any]:
    """Get a single spot by ID."""
    async with get_session_context() as session:
        if not spot_id or len(spot_id) > 50:
            raise HTTPException(status_code=400, detail=f"Invalid spot ID: {spot_id}")

        query = select(CommunitySpot).where(CommunitySpot.id == spot_id)
        result = await session.execute(query)
        spot = result.scalar_one_or_none()

        if not spot:
            raise HTTPException(status_code=404, detail=f"Spot not found: {spot_id}")

        return spot.to_dict()


@router.put("/{spot_id}", response_model=Dict[str, Any])
async def update_spot(spot_id: str, request: SpotUpdate) -> Dict[str, Any]:
    """Update an existing spot."""
    async with get_session_context() as session:
        try:
            spot_uuid = uuid.UUID(spot_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid spot ID: {spot_id}")

        query = select(CommunitySpot).where(CommunitySpot.id == spot_uuid)
        result = await session.execute(query)
        spot = result.scalar_one_or_none()

        if not spot:
            raise HTTPException(status_code=404, detail=f"Spot not found: {spot_id}")

        # Update fields
        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(spot, field):
                setattr(spot, field, value)

        await session.flush()
        await session.refresh(spot)

        return spot.to_dict()


@router.delete("/{spot_id}")
async def delete_spot(spot_id: str) -> Dict[str, str]:
    """Delete a spot."""
    async with get_session_context() as session:
        try:
            spot_uuid = uuid.UUID(spot_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid spot ID: {spot_id}")

        query = select(CommunitySpot).where(CommunitySpot.id == spot_uuid)
        result = await session.execute(query)
        spot = result.scalar_one_or_none()

        if not spot:
            raise HTTPException(status_code=404, detail=f"Spot not found: {spot_id}")

        await session.delete(spot)

        return {"status": "deleted", "id": spot_id}


# Like endpoints
@router.post("/{spot_id}/like", response_model=Dict[str, Any])
async def like_spot(
    spot_id: str, user_id: str = Query("anonymous", description="User ID who is liking")
) -> Dict[str, Any]:
    """
    Like a spot.

    Creates a like record for the spot. Each user can only like a spot once.
    """
    async with get_session_context() as session:
        try:
            spot_uuid = uuid.UUID(spot_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid spot ID: {spot_id}")

        # Get spot
        query = select(CommunitySpot).where(CommunitySpot.id == spot_uuid)
        result = await session.execute(query)
        spot = result.scalar_one_or_none()

        if not spot:
            raise HTTPException(status_code=404, detail=f"Spot not found: {spot_id}")

        # Check if already liked
        like_query = select(SpotLike).where(
            SpotLike.spot_id == spot_uuid, SpotLike.user_id == user_id
        )
        like_result = await session.execute(like_query)
        existing_like = like_result.scalar_one_or_none()

        if existing_like:
            return {
                "id": spot_id,
                "likes": spot.likes_count,
                "message": "Already liked",
            }

        # Create like
        like = SpotLike(spot_id=spot_uuid, user_id=user_id)
        session.add(like)

        # Increment likes count
        spot.likes_count = (spot.likes_count or 0) + 1

        await session.flush()

        return {
            "id": spot_id,
            "likes": spot.likes_count,
            "message": f"Spot liked successfully. Total likes: {spot.likes_count}",
        }


@router.delete("/{spot_id}/like", response_model=Dict[str, Any])
async def unlike_spot(
    spot_id: str, user_id: str = Query("anonymous", description="User ID who is unliking")
) -> Dict[str, Any]:
    """Unlike a spot."""
    async with get_session_context() as session:
        try:
            spot_uuid = uuid.UUID(spot_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid spot ID: {spot_id}")

        # Get spot
        query = select(CommunitySpot).where(CommunitySpot.id == spot_uuid)
        result = await session.execute(query)
        spot = result.scalar_one_or_none()

        if not spot:
            raise HTTPException(status_code=404, detail=f"Spot not found: {spot_id}")

        # Find and delete like
        like_query = select(SpotLike).where(
            SpotLike.spot_id == spot_uuid, SpotLike.user_id == user_id
        )
        like_result = await session.execute(like_query)
        existing_like = like_result.scalar_one_or_none()

        if existing_like:
            await session.delete(existing_like)
            spot.likes_count = max(0, (spot.likes_count or 0) - 1)

        await session.flush()

        return {
            "id": spot_id,
            "likes": spot.likes_count,
            "message": "Spot unliked" if existing_like else "Was not liked",
        }


@router.get("/{spot_id}/likes", response_model=List[Dict[str, Any]])
async def get_spot_likes(spot_id: str) -> List[Dict[str, Any]]:
    """Get all likes for a spot."""
    async with get_session_context() as session:
        try:
            spot_uuid = uuid.UUID(spot_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid spot ID: {spot_id}")

        query = select(SpotLike).where(SpotLike.spot_id == spot_uuid)
        result = await session.execute(query)
        likes = result.scalars().all()

        return [like.to_dict() for like in likes]


# Fork endpoint
@router.post("/{spot_id}/fork", response_model=Dict[str, Any])
async def fork_spot(
    spot_id: str, author: str = Query("anonymous", description="Author for the forked spot")
) -> Dict[str, Any]:
    """
    Fork a spot to user's account.

    Creates a copy of the spot under a new author. The forked spot
    maintains a reference to its parent spot.
    """
    async with get_session_context() as session:
        try:
            spot_uuid = uuid.UUID(spot_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid spot ID: {spot_id}")

        # Get parent spot
        query = select(CommunitySpot).where(CommunitySpot.id == spot_uuid)
        result = await session.execute(query)
        parent_spot = result.scalar_one_or_none()

        if not parent_spot:
            raise HTTPException(status_code=404, detail=f"Spot not found: {spot_id}")

        # Create forked spot
        forked_spot = CommunitySpot(
            title=f"{parent_spot.title} (fork)",
            description=parent_spot.description,
            board=parent_spot.board,
            board_type=parent_spot.board_type,
            position=parent_spot.position,
            pot_size=parent_spot.pot_size,
            stack_depth=parent_spot.stack_depth,
            author=author,
            tags=parent_spot.tags or [],
            strategy_json=parent_spot.strategy_json,
            parent_spot_id=spot_uuid,
        )
        session.add(forked_spot)

        # Increment fork count on parent
        parent_spot.fork_count = (parent_spot.fork_count or 0) + 1

        await session.flush()
        await session.refresh(forked_spot)

        return {
            "id": str(forked_spot.id),
            "parent_spot_id": spot_id,
            "message": f"Spot forked successfully by {author}",
        }


# Comment endpoints
@router.post("/{spot_id}/comments", response_model=Dict[str, Any], status_code=201)
async def create_comment(spot_id: str, request: SpotCommentCreate) -> Dict[str, Any]:
    """Add a comment to a spot."""
    async with get_session_context() as session:
        try:
            spot_uuid = uuid.UUID(spot_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid spot ID: {spot_id}")

        # Get spot
        query = select(CommunitySpot).where(CommunitySpot.id == spot_uuid)
        result = await session.execute(query)
        spot = result.scalar_one_or_none()

        if not spot:
            raise HTTPException(status_code=404, detail=f"Spot not found: {spot_id}")

        # Create comment
        comment = SpotComment(
            spot_id=spot_uuid,
            author=request.author,
            content=request.content,
        )
        session.add(comment)

        await session.flush()
        await session.refresh(comment)

        return comment.to_dict()


@router.get("/{spot_id}/comments", response_model=List[Dict[str, Any]])
async def get_comments(spot_id: str) -> List[Dict[str, Any]]:
    """Get all comments for a spot."""
    async with get_session_context() as session:
        try:
            spot_uuid = uuid.UUID(spot_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid spot ID: {spot_id}")

        query = (
            select(SpotComment)
            .where(SpotComment.spot_id == spot_uuid)
            .order_by(SpotComment.created_at.desc())
        )

        result = await session.execute(query)
        comments = result.scalars().all()

        return [comment.to_dict() for comment in comments]


@router.delete("/{spot_id}/comments/{comment_id}")
async def delete_comment(spot_id: str, comment_id: str) -> Dict[str, str]:
    """Delete a comment."""
    async with get_session_context() as session:
        try:
            comment_uuid = uuid.UUID(comment_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid comment ID: {comment_id}")

        query = select(SpotComment).where(SpotComment.id == comment_uuid)
        result = await session.execute(query)
        comment = result.scalar_one_or_none()

        if not comment:
            raise HTTPException(status_code=404, detail=f"Comment not found: {comment_id}")

        await session.delete(comment)

        return {"status": "deleted", "id": comment_id}
