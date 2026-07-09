"""Double Board PLO equity calculator endpoints"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
import sys

sys.path.insert(0, "/tmp/PokerHandEvaluator/python")
sys.path.insert(0, "packages/poker-core/src")

from gto_poker.double_board import DoubleBoardEvaluator, DoubleBoardEquity, ScoopTracker


router = APIRouter(prefix="/double-board", tags=["double-board", "equity"])


class DoubleBoardEquityRequest(BaseModel):
    """Request for double board PLO equity calculation."""
    hand1: List[str]  # 4 hole cards
    hand2: List[str]  # 4 hole cards
    board1: Optional[List[str]] = []  # Known board1 cards (0-5)
    board2: Optional[List[str]] = []  # Known board2 cards (0-5)
    samples: int = 10000


class ScoopStats(BaseModel):
    """Scoop/chop tracking statistics."""
    total_sims: int
    scoop_wins: int
    chop_wins: int
    scoop_losses: int
    adjusted_equity: float


class DoubleBoardEquityResponse(BaseModel):
    """Response with double board equity percentages."""
    hand1: List[str]
    hand2: List[str]
    equity1: float
    equity2: float
    samples: int
    scoop_stats: Dict


@router.post("/equity", response_model=DoubleBoardEquityResponse)
async def calculate_double_board_equity(request: DoubleBoardEquityRequest):
    """
    Calculate double board PLO equity for two hands.

    Two independent boards. Player scoops if they win BOTH boards.
    Chop if they win one, lose both.

    Scoring: adjusted_equity = (scoop_wins × 1.0 + chop_wins × 0.5) / total_sims
    """
    if len(request.hand1) != 4:
        raise HTTPException(status_code=400, detail="hand1 must have 4 cards")
    if len(request.hand2) != 4:
        raise HTTPException(status_code=400, detail="hand2 must have 4 cards")

    equity_calc = DoubleBoardEquity()
    evaluator = DoubleBoardEvaluator()

    eq1, eq2, tracker = equity_calc.calculate(
        request.hand1,
        request.hand2,
        request.board1,
        request.board2,
        request.samples
    )

    scoop_stats = {
        "total_sims": tracker.total_sims,
        "scoop_wins": tracker.scoop_wins,
        "chop_wins": tracker.chop_wins,
        "scoop_losses": tracker.scoop_losses,
        "adjusted_equity": round(tracker.adjusted_equity, 4)
    }

    return DoubleBoardEquityResponse(
        hand1=request.hand1,
        hand2=request.hand2,
        equity1=round(eq1 * 100, 2),
        equity2=round(eq2 * 100, 2),
        samples=tracker.total_sims,
        scoop_stats=scoop_stats
    )


@router.post("/hand-rank", response_model=dict)
async def evaluate_double_board_hand(
    hole: List[str],
    board1: List[str],
    board2: List[str]
):
    """Evaluate a hand on two boards and return ranks."""
    if len(hole) != 4:
        raise HTTPException(status_code=400, detail="hole must have 4 cards")

    evaluator = DoubleBoardEvaluator()

    try:
        rank1, rank2 = evaluator.evaluate(hole, board1, board2)

        return {
            "hole": hole,
            "board1": board1,
            "board2": board2,
            "rank1": rank1,
            "rank2": rank2,
            "strength1_percent": round((7462 - rank1) / 7462 * 100, 2),
            "strength2_percent": round((7462 - rank2) / 7462 * 100, 2)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/showdown", response_model=dict)
async def evaluate_showdown(
    hands: List[List[str]],
    board1: List[str],
    board2: List[str]
):
    """
    Evaluate showdown for multiple players on two boards.

    Returns adjusted equities for each player based on scoop/chop scoring.
    """
    if len(hands) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 players")

    for h in hands:
        if len(h) != 4:
            raise HTTPException(status_code=400, detail="Each hand must have 4 cards")

    if len(board1) != 5:
        raise HTTPException(status_code=400, detail="board1 must have 5 cards")
    if len(board2) != 5:
        raise HTTPException(status_code=400, detail="board2 must have 5 cards")

    evaluator = DoubleBoardEvaluator()

    try:
        equities = evaluator.evaluate_showdown(hands, board1, board2)

        return {
            "hands": hands,
            "board1": board1,
            "board2": board2,
            "equities": [round(eq * 100, 2) for eq in equities],
            "winner": equities.index(max(equities)) if equities else 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))