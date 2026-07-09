"""Pydantic schemas for community spots API."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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


class SpotListResponse(BaseModel):
    """Response model for listing spots."""
    spots: List[SpotResponse]
    total: int
    offset: int
    limit: int


class LikeResponse(BaseModel):
    """Response model for like action."""
    id: str
    likes: int
    message: str


class ForkResponse(BaseModel):
    """Response model for fork action."""
    id: str
    parent_spot_id: str
    message: str
