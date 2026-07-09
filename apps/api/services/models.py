"""
SQLAlchemy models for strategy storage.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, String, Integer, Float, DateTime, Text
from sqlalchemy import JSON

from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import declarative_base

Base = declarative_base(cls=AsyncAttrs)


class Strategy(Base):
    """Strategy storage model."""
    
    __tablename__ = "strategies"
    
    id = Column(String(36), primary_key=True, default=lambda: None)
    key = Column(Text, unique=True, nullable=False, index=True)
    game_type = Column(String(10), nullable=False, default="nlh")
    players = Column(Integer, nullable=False, default=2)
    street = Column(String(20), nullable=False, default="preflop")
    board_hash = Column(Text, nullable=False, default="")
    bet_size = Column(Float, nullable=False, default=0.0)
    stack_depth = Column(Integer, nullable=False)
    strategy_data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id) if self.id else None,
            "key": self.key,
            "game_type": self.game_type,
            "players": self.players,
            "street": self.street,
            "board_hash": self.board_hash,
            "bet_size": self.bet_size,
            "stack_depth": self.stack_depth,
            "strategy_data": self.strategy_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
