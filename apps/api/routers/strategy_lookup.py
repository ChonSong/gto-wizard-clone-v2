"""
Strategy lookup API router.

Provides endpoints for looking up GTO strategies from PostgreSQL storage
using board/stack/position parameters.

Endpoint: GET /api/v1/strategy-lookup?board=Kh8c3d&stack_depth=100&position=BTN&street=river&bet_size=0.5
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from apps.api.services.strategy_storage import (
    StrategyStorageService,
    StrategyFilters,
    get_strategy_storage,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/strategy-lookup", tags=["strategy-lookup"])


class StrategyLookupResponse(BaseModel):
    """Response model for strategy lookup."""

    key: str
    game_type: str = "nlh"
    players: int = 2
    street: str
    board: str
    board_hash: str
    bet_size: float
    stack_depth: int
    position: str
    strategy: Dict[str, Any]
    status: str = "found"


class StrategyLookupError(BaseModel):
    """Error response model."""

    error: str
    detail: str
    suggestion: Optional[str] = None


def parse_board_to_street(board: str) -> str:
    """
    Parse board string to determine street.

    Args:
        board: Board cards like "Kd7h2c" or "preflop"

    Returns:
        Street name: preflop, flop, turn, or river
    """
    if board.lower() == "preflop":
        return "preflop"

    # Remove spaces and count cards
    cards = board.replace(" ", "")
    num_cards = len(cards) // 2  # Each card is 2 chars (rank + suit)

    if num_cards == 0:
        return "preflop"
    elif num_cards == 3:
        return "flop"
    elif num_cards == 4:
        return "turn"
    elif num_cards == 5:
        return "river"
    else:
        # Default to flop for malformed input
        return "flop"


def transform_strategy_for_heatmap(strategy_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform stored strategy data into format expected by StrategyHeatmap.

    Args:
        strategy_data: Raw strategy data from storage

    Returns:
        Transformed strategy keyed by hand string (e.g., "AKs", "TT", "72o")
    """
    # The strategy_data may contain 'actions' or 'strategy' key with hand data
    if isinstance(strategy_data, dict):
        # Check for common formats
        if "strategy" in strategy_data and isinstance(strategy_data["strategy"], dict):
            return strategy_data["strategy"]
        if "actions" in strategy_data and isinstance(strategy_data["actions"], list):
            # Convert list format to dict keyed by hand
            result = {}
            for action in strategy_data["actions"]:
                if "hand" in action:
                    result[action["hand"]] = {
                        "action": action.get("action", "unknown"),
                        "frequency": action.get("frequency", 0.0),
                        "ev": action.get("ev", 0.0),
                    }
            return result
        # Already in correct format
        return strategy_data
    return {}


@router.get("", response_model=StrategyLookupResponse)
async def lookup_strategy(
    board: str = Query(..., description="Board cards (e.g., 'Kh8c3d' or 'preflop')"),
    stack_depth: int = Query(100, description="Stack depth in big blinds"),
    position: str = Query("BTN", description="Player position (BTN, SB, BB, CO, etc.)"),
    street: Optional[str] = Query(
        None, description="Street (preflop, flop, turn, river) - auto-detected if not provided"
    ),
    bet_size: float = Query(0.5, description="Bet size as fraction of pot"),
    game_type: str = Query("nlh", description="Game type (nlh, plo)"),
    players: int = Query(2, description="Number of players"),
) -> StrategyLookupResponse:
    """
    Look up a GTO strategy by board/stack/position parameters.

    The strategy is looked up from PostgreSQL via StrategyStorageService.
    Board cards are parsed to determine the street automatically.

    Query parameters:
    - board: Board cards or 'preflop' (e.g., 'Kh8c3d')
    - stack_depth: Stack depth in big blinds (default: 100)
    - position: Player position (BTN, SB, BB, CO, etc.)
    - street: Optional street override (auto-detected from board)
    - bet_size: Bet size as fraction of pot (default: 0.5)
    - game_type: Game type (nlh, plo)
    - players: Number of players
    """
    # Auto-detect street from board if not provided
    detected_street = street or parse_board_to_street(board)

    # For preflop, encode position in board_hash to match seed data format
    # Seed script stores preflop strategies with board_hash=position.lower()
    if detected_street == "preflop":
        board_hash = position.lower() if position else ""
    else:
        # Hash the board for lookup
        board_hash = StrategyStorageService.hash_board(board) if board else ""

    try:
        storage = await get_strategy_storage()

        # Try to get strategy by exact parameters
        strategy = await storage.get_strategy_by_params(
            street=detected_street,
            board_hash=board_hash,
            bet_size=bet_size,
            stack_depth=stack_depth,
            game_type=game_type,
            players=players,
        )

        if strategy is None:
            # Try to find closest match
            candidates = await storage.list_strategies(
                filters=StrategyFilters(
                    game_type=game_type,
                    players=players,
                    street=detected_street,
                    board_hash=board_hash if board_hash else None,
                    stack_depth=None,
                    limit=10,
                    offset=0,
                )
            )

            if candidates:
                # Try first candidate that has strategy data
                for candidate in candidates:
                    key = candidate["key"]
                    strategy = await storage.get_strategy(key)
                    if strategy:
                        break

            if strategy is None:
                available_boards = await storage.list_flop_strategies(
                    game_type=game_type,
                    players=players,
                    stack_depth=stack_depth,
                    limit=5,
                )

                suggestion = None
                if available_boards:
                    boards_list = [b.get("board_hash", "") for b in available_boards[:5]]
                    suggestion = f"Available boards for {stack_depth}bb: {', '.join(boards_list)}"

                raise HTTPException(
                    status_code=404,
                    detail=f"Strategy not found for: board={board}, stack={stack_depth}bb, street={detected_street}, bet_size={bet_size}",
                )

        # Transform strategy data for heatmap
        heatmap_strategy = transform_strategy_for_heatmap(strategy.strategy_data)

        return StrategyLookupResponse(
            key=strategy.key,
            game_type=strategy.game_type,
            players=strategy.players,
            street=strategy.street,
            board=board,
            board_hash=strategy.board_hash,
            bet_size=strategy.bet_size,
            stack_depth=strategy.stack_depth,
            position=position,
            strategy=heatmap_strategy,
            status="found",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Strategy lookup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Strategy lookup failed: {str(e)}")


@router.get("/streets", response_model=Dict[str, Any])
async def get_available_streets():
    """Get available streets for strategy lookup."""
    return {
        "streets": [
            {"value": "preflop", "label": "Preflop"},
            {"value": "flop", "label": "Flop"},
            {"value": "turn", "label": "Turn"},
            {"value": "river", "label": "River"},
        ]
    }


@router.get("/positions", response_model=Dict[str, Any])
async def get_available_positions():
    """Get available positions for strategy lookup."""
    return {
        "positions": [
            {"value": "BTN", "label": "Button"},
            {"value": "SB", "label": "Small Blind"},
            {"value": "BB", "label": "Big Blind"},
            {"value": "CO", "label": "Cutoff"},
            {"value": "HJ", "label": "Hijack"},
            {"value": "LJ", "label": "Lojack"},
            {"value": "UTG", "label": "Under the Gun"},
            {"value": "UTG+1", "label": "UTG+1"},
            {"value": "UTG+2", "label": "UTG+2"},
        ]
    }


@router.get("/stack-depths", response_model=Dict[str, Any])
async def get_available_stack_depths(
    game_type: str = Query("nlh", description="Game type"),
    players: int = Query(2, description="Number of players"),
):
    """Get available stack depths for strategy lookup."""
    # Return common stack depths
    return {
        "stack_depths": [
            {"value": 50, "label": "50bb"},
            {"value": 75, "label": "75bb"},
            {"value": 100, "label": "100bb"},
            {"value": 125, "label": "125bb"},
            {"value": 150, "label": "150bb"},
            {"value": 200, "label": "200bb"},
        ]
    }


@router.get("/bet-sizes", response_model=Dict[str, Any])
async def get_available_bet_sizes():
    """Get available bet sizes for strategy lookup."""
    return {
        "bet_sizes": [
            {"value": 0.25, "label": "25% pot"},
            {"value": 0.33, "label": "33% pot"},
            {"value": 0.5, "label": "50% pot"},
            {"value": 0.67, "label": "67% pot"},
            {"value": 0.75, "label": "75% pot"},
            {"value": 1.0, "label": "100% pot"},
            {"value": 1.5, "label": "150% pot"},
        ]
    }
