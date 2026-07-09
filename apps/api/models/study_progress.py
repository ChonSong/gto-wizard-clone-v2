"""
SQLAlchemy model for study progress persistence.

Tracks per-session training actions (hand, position, action chosen, GTO action, correct/incorrect)
with timestamps for long-term progress tracking across sessions.
"""

import uuid
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import Column, String, Boolean, Integer, Float, DateTime

from apps.api.services.database import Base


class StudyProgress(Base):
    """Individual study session action record."""

    __tablename__ = "study_progress"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    hand = Column(String(10), nullable=False)
    position = Column(String(10), nullable=False)
    stack_depth = Column(Integer, nullable=False)
    action_chosen = Column(String(50), nullable=False)
    action_gto = Column(String(50), nullable=False)
    correct = Column(Boolean, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id) if self.id else None,
            "user_id": self.user_id,
            "hand": self.hand,
            "position": self.position,
            "stack_depth": self.stack_depth,
            "action_chosen": self.action_chosen,
            "action_gto": self.action_gto,
            "correct": self.correct,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
