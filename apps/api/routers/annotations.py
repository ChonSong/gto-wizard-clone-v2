# ════════════════════════════════════════════════════════════
#  ANNOTATIONS API CRUD
# ════════════════════════════════════════════════════════════

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.api.services.models import Strategy, Base as ModelsBase
from apps.api.services.database import get_session_context
from apps.api.models.annotations import SpotAnnotation, AnnotationReply

router = APIRouter(prefix="/api/v1/annotations", tags=["annotations"])


class AnnotationIn(BaseModel):
    spot_hash: str
    board: str = ""
    position: str = "BTN"
    stack_depth: float = 100
    tree_path: list[str] = []
    hand: str = ""
    content: str = ""
    author: str = "anonymous"
    is_ai_suggested: int = 0


class AnnotationUpdate(BaseModel):
    content: Optional[str] = None
    accepted: Optional[int] = None


class ReplyIn(BaseModel):
    annotation_id: str
    content: str
    author: str = "anonymous"
    parent_reply_id: Optional[str] = None


@router.get("/spot/{spot_hash}")
async def get_annotations(spot_hash: str, hand: Optional[str] = None):
    """Get all annotations for a specific spot, optionally filtered by hand."""
    async with get_session_context() as session:
        from sqlalchemy import select, and_
        query = select(SpotAnnotation).where(SpotAnnotation.spot_hash == spot_hash)
        if hand:
            query = query.where(SpotAnnotation.hand == hand)
        result = await session.execute(query.order_by(SpotAnnotation.created_at))
        annotations = result.scalars().all()
        return [a.to_dict() for a in annotations]


@router.post("/")
async def create_annotation(data: AnnotationIn):
    """Create a new annotation for a hand+spot."""
    async with get_session_context() as session:
        # Check for duplicate
        from sqlalchemy import select, and_
        existing = await session.execute(
            select(SpotAnnotation).where(
                and_(
                    SpotAnnotation.spot_hash == data.spot_hash,
                    SpotAnnotation.hand == data.hand,
                    SpotAnnotation.author == data.author,
                )
            )
        )
        if existing.scalar():
            raise HTTPException(409, "Annotation already exists for this spot+hand+author")
        
        ann = SpotAnnotation(
            spot_hash=data.spot_hash,
            board=data.board,
            position=data.position,
            stack_depth=data.stack_depth,
            tree_path=json.dumps(data.tree_path),
            hand=data.hand,
            content=data.content,
            author=data.author,
            is_ai_suggested=data.is_ai_suggested,
        )
        session.add(ann)
        await session.flush()
        return ann.to_dict()


@router.patch("/{ann_id}")
async def update_annotation(ann_id: str, data: AnnotationUpdate):
    """Update annotation content or acceptance status."""
    async with get_session_context() as session:
        from sqlalchemy import select
        result = await session.execute(select(SpotAnnotation).where(SpotAnnotation.id == ann_id))
        ann = result.scalar()
        if not ann:
            raise HTTPException(404, "Annotation not found")
        if data.content is not None:
            ann.content = data.content
        if data.accepted is not None:
            ann.accepted = str(data.accepted)
        ann.updated_at = datetime.utcnow()
        return ann.to_dict()


@router.delete("/{ann_id}")
async def delete_annotation(ann_id: str):
    """Delete an annotation."""
    async with get_session_context() as session:
        from sqlalchemy import select
        result = await session.execute(select(SpotAnnotation).where(SpotAnnotation.id == ann_id))
        ann = result.scalar()
        if not ann:
            raise HTTPException(404, "Annotation not found")
        await session.delete(ann)
        return {"deleted": True}


@router.post("/reply")
async def create_reply(data: ReplyIn):
    """Add a reply to an annotation."""
    async with get_session_context() as session:
        reply = AnnotationReply(
            annotation_id=data.annotation_id,
            parent_reply_id=data.parent_reply_id,
            content=data.content,
            author=data.author,
        )
        session.add(reply)
        await session.flush()
        return reply.to_dict()


@router.get("/{ann_id}/replies")
async def get_replies(ann_id: str):
    """Get all replies for an annotation."""
    async with get_session_context() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(AnnotationReply)
            .where(AnnotationReply.annotation_id == ann_id)
            .order_by(AnnotationReply.created_at)
        )
        return [r.to_dict() for r in result.scalars().all()]
