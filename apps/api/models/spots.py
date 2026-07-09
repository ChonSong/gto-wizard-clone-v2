"""
SQLAlchemy models for community spot storage.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, String, Integer, Float, DateTime, Text, ForeignKey
from sqlalchemy import JSON
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import relationship, declarative_base

from apps.api.services.models import Base


class CommunitySpot(Base):
    """Community spot sharing model."""
    
    __tablename__ = "community_spots"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    board = Column(Text, nullable=False, default="")
    board_type = Column(String(20), nullable=False, default="flop")  # flop, turn, river
    position = Column(String(10), nullable=False, default="")  # btn, sb, bb, utg, etc.
    pot_size = Column(Float, nullable=False, default=0.0)
    stack_depth = Column(Integer, nullable=False, default=100)
    author = Column(Text, nullable=False, default="anonymous")
    tags = Column(JSON, nullable=True, default=[])
    strategy_json = Column(JSON, nullable=False)
    likes_count = Column(Integer, nullable=False, default=0)
    fork_count = Column(Integer, nullable=False, default=0)
    parent_spot_id = Column(String(36), nullable=True)  # For forked spots
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    comments = relationship("SpotComment", back_populates="spot", cascade="all, delete-orphan")
    likes = relationship("SpotLike", back_populates="spot", cascade="all, delete-orphan")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id) if self.id else None,
            "title": self.title,
            "description": self.description,
            "board": self.board,
            "board_type": self.board_type,
            "position": self.position,
            "pot_size": self.pot_size,
            "stack_depth": self.stack_depth,
            "author": self.author,
            "tags": self.tags or [],
            "strategy_json": self.strategy_json,
            "likes": self.likes_count,
            "fork_count": self.fork_count,
            "parent_spot_id": str(self.parent_spot_id) if self.parent_spot_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "comments_count": 0,  # Avoid lazy-load relationship in async context
        }


class SpotComment(Base):
    """Comment on a community spot."""
    
    __tablename__ = "spot_comments"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    spot_id = Column(String(36), ForeignKey("community_spots.id", ondelete="CASCADE"), nullable=False)
    author = Column(Text, nullable=False, default="anonymous")
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    spot = relationship("CommunitySpot", back_populates="comments")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id) if self.id else None,
            "spot_id": str(self.spot_id) if self.spot_id else None,
            "author": self.author,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SpotLike(Base):
    """Like on a community spot."""
    
    __tablename__ = "spot_likes"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    spot_id = Column(String(36), ForeignKey("community_spots.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Text, nullable=False, default="anonymous")  # User who liked
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    # Relationships
    spot = relationship("CommunitySpot", back_populates="likes")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id) if self.id else None,
            "spot_id": str(self.spot_id) if self.spot_id else None,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
