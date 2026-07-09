"""
SQLAlchemy models for training courses system.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, String, Integer, Float, DateTime, Text, Boolean, ForeignKey
from sqlalchemy import JSON

 
from sqlalchemy.orm import relationship

from apps.api.services.database import Base


class Course(Base):
    """Training course model."""
    
    __tablename__ = "courses"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    short_description = Column(Text, nullable=True)
    thumbnail_url = Column(Text, nullable=True)
    game_type = Column(String(20), nullable=False, default="nlh")  # nlh, plo4, plo6, omaha
    difficulty = Column(String(20), nullable=False, default="beginner")  # beginner, intermediate, advanced
    category = Column(String(50), nullable=False, default="general")  # preflop, postflop, mental_game, etc.
    duration_minutes = Column(Integer, nullable=False, default=0)
    lesson_count = Column(Integer, nullable=False, default=0)
    is_published = Column(Boolean, nullable=False, default=False)
    is_featured = Column(Boolean, nullable=False, default=False)
    prerequisites = Column(JSON, nullable=True, default=[])  # List of course IDs
    tags = Column(JSON, nullable=True, default=[])
    author = Column(Text, nullable=False, default="GTO Wizard")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    lessons = relationship("Lesson", back_populates="course", cascade="all, delete-orphan")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id) if self.id else None,
            "title": self.title,
            "description": self.description,
            "short_description": self.short_description,
            "thumbnail_url": self.thumbnail_url,
            "game_type": self.game_type,
            "difficulty": self.difficulty,
            "category": self.category,
            "duration_minutes": self.duration_minutes,
            "lesson_count": self.lesson_count,
            "is_published": self.is_published,
            "is_featured": self.is_featured,
            "prerequisites": self.prerequisites or [],
            "tags": self.tags or [],
            "author": self.author,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Lesson(Base):
    """Individual lesson within a course."""
    
    __tablename__ = "lessons"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id = Column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=True)  # Markdown/HTML content
    content_type = Column(String(20), nullable=False, default="text")  # text, video, quiz, interactive
    video_url = Column(Text, nullable=True)
    order_index = Column(Integer, nullable=False, default=0)
    duration_minutes = Column(Integer, nullable=False, default=0)
    is_preview = Column(Boolean, nullable=False, default=False)  # Free preview lesson
    quiz_data = Column(JSON, nullable=True)  # Quiz questions if content_type is quiz
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    course = relationship("Course", back_populates="lessons")
    user_progress = relationship("UserProgress", back_populates="lesson", cascade="all, delete-orphan")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id) if self.id else None,
            "course_id": str(self.course_id) if self.course_id else None,
            "title": self.title,
            "content": self.content,
            "content_type": self.content_type,
            "video_url": self.video_url,
            "order_index": self.order_index,
            "duration_minutes": self.duration_minutes,
            "is_preview": self.is_preview,
            "quiz_data": self.quiz_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class UserProgress(Base):
    """Tracks user progress through courses and lessons."""
    
    __tablename__ = "user_progress"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Text, nullable=False, index=True)
    course_id = Column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    lesson_id = Column(String(36), ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), nullable=False, default="not_started")  # not_started, in_progress, completed
    progress_percent = Column(Float, nullable=False, default=0.0)
    time_spent_minutes = Column(Integer, nullable=False, default=0)
    quiz_score = Column(Float, nullable=True)  # Quiz score if lesson has quiz
    completed_at = Column(DateTime(timezone=True), nullable=True)
    last_accessed_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    lesson = relationship("Lesson", back_populates="user_progress")
    course = relationship("Course")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id) if self.id else None,
            "user_id": self.user_id,
            "course_id": str(self.course_id) if self.course_id else None,
            "lesson_id": str(self.lesson_id) if self.lesson_id else None,
            "status": self.status,
            "progress_percent": self.progress_percent,
            "time_spent_minutes": self.time_spent_minutes,
            "quiz_score": self.quiz_score,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "last_accessed_at": self.last_accessed_at.isoformat() if self.last_accessed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
