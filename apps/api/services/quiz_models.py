"""
Quiz Models for GTO Wizard API.

SQLAlchemy models for training mode:
- QuizSpot: Poker spots with GTO solutions for quiz gameplay
- QuizSubmission: User's answer to a quiz spot
- UserStats: Per-user accuracy tracking and streaks
- ReviewSpot: Spots marked for review by user
"""

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.services.database import Base


class QuizSpot(Base):
    """A poker situation (spot) with GTO solution for training."""
    __tablename__ = "quiz_spots"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    game_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True, default="nlh")
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False, index=True, default="medium")

    position: Mapped[str] = mapped_column(String(20), nullable=False)
    hero_hand: Mapped[str] = mapped_column(String(10), nullable=False)
    board: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    turn: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    river: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)

    pot_size: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    stack_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    gto_action: Mapped[str] = mapped_column(String(20), nullable=False)
    gto_frequency: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=1.0)
    gto_ev: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0.0)

    options: Mapped[dict] = mapped_column(JSON, nullable=False)
    explanation: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    street: Mapped[str] = mapped_column(String(20), nullable=False, index=True, default="flop")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("ix_quiz_spots_game_cat_diff", "game_type", "category", "difficulty"),
        Index("ix_quiz_spots_street", "street"),
    )


class QuizSubmission(Base):
    """A user's answer to a quiz spot."""
    __tablename__ = "quiz_submissions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    user_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    spot_id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        ForeignKey("quiz_spots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    spot: Mapped["QuizSpot"] = relationship("QuizSpot", lazy="joined")

    selected_action: Mapped[str] = mapped_column(String(20), nullable=False)
    is_correct: Mapped[bool] = mapped_column(nullable=False, default=False)
    ev_loss: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0.0)

    time_taken_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_quiz_submissions_user_submitted", "user_id", "submitted_at"),
        Index("ix_quiz_submissions_session", "session_id", "submitted_at"),
    )


class UserStats(Base):
    """Per-user training statistics and progress."""
    __tablename__ = "user_stats"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    user_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    user_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    total_solves: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_ev_loss: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=0.0)

    current_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    weak_spots: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    accuracy_history: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True, default=list,
    )
    missed_spot_ids: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True, default=list,
    )

    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    @property
    def accuracy(self) -> float:
        if self.total_solves == 0:
            return 0.0
        return (self.correct_count / self.total_solves) * 100

    @property
    def avg_ev_loss(self) -> float:
        if self.total_solves == 0:
            return 0.0
        return self.total_ev_loss / self.total_solves


class ReviewSpot(Base):
    """Spots that a user has marked for review."""
    __tablename__ = "review_spots"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    spot_id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        ForeignKey("quiz_spots.id", ondelete="CASCADE"),
        nullable=False,
    )
    spot: Mapped["QuizSpot"] = relationship("QuizSpot", lazy="joined")

    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    mastered: Mapped[bool] = mapped_column(nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_review_spots_user_mastered", "user_id", "mastered"),
    )
