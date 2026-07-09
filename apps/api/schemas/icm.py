"""Pydantic schemas for ICM API."""

from typing import Optional
from pydantic import BaseModel, Field


class ICMPlayer(BaseModel):
    """Player in an ICM calculation."""
    name: str = Field(..., description="Player name")
    stack: float = Field(..., gt=0, description="Chip stack")


class ICMCalculationRequest(BaseModel):
    """Request to calculate ICM equity."""
    stacks: list[float] = Field(..., min_length=2, description="List of chip stacks")
    prizes: list[float] = Field(..., min_length=1, description="Prize amounts per place (index 0 = 1st)")
    players: Optional[list[str]] = Field(None, description="Player names (auto-generated if not provided)")
    n_simulations: int = Field(100_000, ge=1000, le=1_000_000, description="Monte Carlo simulations")
    seed: Optional[int] = Field(None, description="Random seed for reproducibility")


class ICMResult(BaseModel):
    """Result of ICM calculation for a player."""
    player: str
    equity: float = Field(..., description="Total equity in currency")
    chip_equity: float = Field(..., description="Equity based on chip count only")
    bubble_factor: float = Field(..., description="Bubble factor multiplier")
    ev: float = Field(..., description="Expected value")


class ICMCalculationResponse(BaseModel):
    """Response containing ICM results."""
    results: list[ICMResult]
    total_prize_pool: float
    total_chips: float


class TournamentScenario(BaseModel):
    """Tournament scenario for training/analysis."""
    name: str = Field(..., description="Scenario name")
    players: list[str] = Field(..., min_length=2, description="Player names")
    stacks: list[float] = Field(..., description="Chip stacks")
    prizes: list[float] = Field(..., description="Prize structure")
    street: Optional[str] = Field(None, description="Tournament street (e.g., 'bubble', 'FT', 'final')")
    ICM_positions: Optional[list[ICMResult]] = Field(None, description="Pre-calculated ICM positions")


class TournamentScenarioCreate(BaseModel):
    """Request to create a tournament scenario."""
    name: str
    players: list[str]
    stacks: list[float]
    prizes: list[float]
    street: Optional[str] = None


class TournamentScenarioList(BaseModel):
    """List of tournament scenarios."""
    scenarios: list[TournamentScenario]
    total: int