"""PLO4 equity calculator endpoints"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from gto_poker.plo4 import PLO4Evaluator, PLO4Equity
from gto_poker.plo4_range import PLO4RangeParser


router = APIRouter(prefix="/plo4/equity", tags=["plo4", "equity"])


class PLO4EquityRequest(BaseModel):
    """Request for PLO4 equity calculation."""
    hand1: List[str]  # 4 hole cards
    hand2: List[str]  # 4 hole cards
    board: Optional[List[str]] = []  # Known board cards (0-5)
    samples: int = 10000


class PLO4EquityResponse(BaseModel):
    """Response with equity percentages."""
    hand1: List[str]
    hand2: List[str]
    equity1: float
    equity2: float
    samples: int
    hand1_rank: Optional[int] = None
    hand2_rank: Optional[int] = None


@router.post("/calculate", response_model=PLO4EquityResponse)
async def calculate_plo4_equity(request: PLO4EquityRequest):
    """
    Calculate PLO4 equity for two hands.
    
    Uses Monte Carlo simulation when no board is provided,
    or exact calculation when 5 board cards are known.
    """
    if len(request.hand1) != 4:
        raise HTTPException(status_code=400, detail="hand1 must have 4 cards")
    if len(request.hand2) != 4:
        raise HTTPException(status_code=400, detail="hand2 must have 4 cards")
    if len(request.board) > 5:
        raise HTTPException(status_code=400, detail="board can have at most 5 cards")
    
    equity_calc = PLO4Equity()
    evaluator = PLO4Evaluator()
    
    eq1, eq2 = equity_calc.calculate(
        request.hand1,
        request.hand2,
        request.board,
        request.samples
    )
    
    # Calculate ranks if board is complete
    rank1 = None
    rank2 = None
    if len(request.board) == 5:
        rank1 = evaluator.evaluate_cards(request.hand1, request.board)
        rank2 = evaluator.evaluate_cards(request.hand2, request.board)
    
    return PLO4EquityResponse(
        hand1=request.hand1,
        hand2=request.hand2,
        equity1=round(eq1, 2),
        equity2=round(eq2, 2),
        samples=request.samples,
        hand1_rank=rank1,
        hand2_rank=rank2
    )


@router.post("/hand-rank", response_model=dict)
async def evaluate_plo4_hand(
    hole: List[str],
    board: List[str]
):
    """Evaluate a single PLO4 hand and return its rank."""
    if len(hole) != 4:
        raise HTTPException(status_code=400, detail="hole must have 4 cards")
    if len(board) > 5:
        raise HTTPException(status_code=400, detail="board can have at most 5 cards")
    
    evaluator = PLO4Evaluator()
    
    # Handle partial board with Monte Carlo
    if len(board) < 5:
        equity_calc = PLO4Equity()
        eq, _ = equity_calc.calculate(hole, ["Tc", "9c", "8c", "7c"], board, samples=1000)
        return {
            "hole": hole,
            "board": board,
            "note": "Partial board - rank requires full board or Monte Carlo"
        }
    
    rank = evaluator.evaluate(*hole, *board)
    
    return {
        "hole": hole,
        "board": board,
        "rank": rank,
        "strength_percent": round((rank / 7462) * 100, 2)
    }


@router.post("/range-vs-range", response_model=dict)
async def plo4_range_vs_range(
    range1: str,  # Range string like "AAKK, JJQQ, TJs"
    range2: str,
    board: Optional[List[str]] = [],
    samples: int = 5000
):
    """
    Calculate equity of one range vs another range.
    
    Samples random hands from each range.
    """
    parser = PLO4RangeParser()
    hands1 = parser.parse(range1)
    hands2 = parser.parse(range2)
    
    if not hands1 or not hands2:
        raise HTTPException(status_code=400, detail="Invalid range string")
    
    # Sample for efficiency
    import random
    sample_size = min(100, len(hands1), len(hands2))
    sample1 = random.sample(list(hands1), sample_size)
    sample2 = random.sample(list(hands2), sample_size)
    
    equity_calc = PLO4Equity()
    
    total_eq1 = 0
    total_eq2 = 0
    comparisons = 0
    
    for h1 in sample1:
        for h2 in sample2:
            if h1 == h2:
                continue
            eq1, eq2 = equity_calc.calculate(
                list(h1) if isinstance(h1, str) else list(h1),
                list(h2) if isinstance(h2, str) else list(h2),
                board or [],
                samples=min(100, samples // 10)
            )
            total_eq1 += eq1
            total_eq2 += eq2
            comparisons += 1
    
    if comparisons == 0:
        return {"equity1": 50, "equity2": 50, "comparisons": 0}
    
    return {
        "range1": range1,
        "range2": range2,
        "equity1": round(total_eq1 / comparisons, 2),
        "equity2": round(total_eq2 / comparisons, 2),
        "comparisons": comparisons,
        "sample_size": sample_size
    }
