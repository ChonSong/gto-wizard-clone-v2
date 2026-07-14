# ════════════════════════════════════════════════════════════
#  ANNOTATIONS MODEL + CRUD API
# ════════════════════════════════════════════════════════════

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, Float, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import relationship, declarative_base

from apps.api.services.models import Base


class SpotAnnotation(Base):
    """Per-hand comment/annotation for a specific spot."""
    
    __tablename__ = "spot_annotations"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    spot_hash = Column(String(32), nullable=False, index=True)  # SHA of spot key
    board = Column(String(10), nullable=False, default="")
    position = Column(String(10), nullable=False, default="")
    stack_depth = Column(Float, nullable=False, default=100)
    tree_path = Column(Text, nullable=False, default="")  # JSON list of actions
    hand = Column(String(5), nullable=False, default="")  # e.g. "AKs", "AA", "72o"
    content = Column(Text, nullable=False)  # Annotation text
    author = Column(Text, nullable=False, default="anonymous")
    is_ai_suggested = Column(Text, nullable=False, default=0)  # 0=user, 1=AI-suggested
    accepted = Column(Text, nullable=False, default=0)  # 0=pending, 1=accepted, -1=rejected
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint("spot_hash", "hand", "author", name="uq_spot_hand_author"),
    )
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "spot_hash": self.spot_hash,
            "board": self.board,
            "position": self.position,
            "stack_depth": self.stack_depth,
            "tree_path": self.tree_path,
            "hand": self.hand,
            "content": self.content,
            "author": self.author,
            "is_ai_suggested": self.is_ai_suggested,
            "accepted": self.accepted,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AnnotationReply(Base):
    """Threaded reply to an annotation."""
    
    __tablename__ = "annotation_replies"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    annotation_id = Column(String(36), ForeignKey("spot_annotations.id", ondelete="CASCADE"), nullable=False)
    parent_reply_id = Column(String(36), ForeignKey("annotation_replies.id", ondelete="CASCADE"), nullable=True)
    content = Column(Text, nullable=False)
    author = Column(Text, nullable=False, default="anonymous")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "annotation_id": self.annotation_id,
            "parent_reply_id": self.parent_reply_id,
            "content": self.content,
            "author": self.author,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
