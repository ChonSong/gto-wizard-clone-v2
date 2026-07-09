"""Omaha variants equity calculator endpoints (PLO5, Omaha Hi/Lo, Shortdeck)"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

import sys
sys.path.insert(0, "/tmp/PokerHandEvaluator/python")
# sys.path removed — gto-poker is pip-installed

from gto_poker.plo5 import PLO5Evaluator, PLO5Equity
from gto_poker.omaha_hi_lo import OmahaHiLoEvaluator, OmahaHiLoEquity
from gto_poker.shortdeck import ShortdeckHand, ShortdeckEquity


# Main router for /omaha prefix
router = APIRouter(prefix="/omaha", tags=["omaha", "equity"])


# ============== PLO5 Endpoints ==============

class PLO5EquityRequest(BaseModel):
    """Request for PLO5 (5-card Omaha) equity calculation."""
    hand1: List[str]  # 5 hole cards
    hand2: List[str]  # 5 hole cards
    board: Optional[List[str]] = []  # Known board cards (0-5)
    samples: int = 10000


class PLO5EquityResponse(BaseModel):
    """Response with PLO5 equity percentages."""
    hand1: List[str]
    hand2: List[str]
    equity1: float
    equity2: float
    samples: int


@router.post("/plo5/equity/calculate", response_model=PLO5EquityResponse)
async def calculate_plo5_equity(request: PLO5EquityRequest):
    """
    Calculate PLO5 (5-card Omaha) equity for two hands.
    
    Uses Monte Carlo simulation when no board is provided,
    or exact calculation when 5 board cards are known.
    """
    if len(request.hand1) != 5:
        raise HTTPException(status_code=400, detail="hand1 must have 5 cards")
    if len(request.hand2) != 5:
        raise HTTPException(status_code=400, detail="hand2 must have 5 cards")
    if len(request.board) > 5:
        raise HTTPException(status_code=400, detail="board can have at most 5 cards")
    
    equity_calc = PLO5Equity()
    
    eq1, eq2 = equity_calc.calculate(
        request.hand1,
        request.hand2,
        request.board,
        request.samples
    )
    
    return PLO5EquityResponse(
        hand1=request.hand1,
        hand2=request.hand2,
        equity1=round(eq1, 2),
        equity2=round(eq2, 2),
        samples=request.samples
    )


# ============== Omaha Hi/Lo Endpoints ==============

class OmahaHiLoEquityRequest(BaseModel):
    """Request for Omaha Hi/Lo equity calculation."""
    hand1: List[str]  # 4 hole cards
    hand2: List[str]  # 4 hole cards
    board: Optional[List[str]] = []  # Known board cards (0-5)
    samples: int = 10000


class OmahaHiLoEquityResponse(BaseModel):
    """Response with Omaha Hi/Lo equity percentages."""
    hand1: List[str]
    hand2: List[str]
    high_equity1: float
    high_equity2: float
    low_equity1: float
    low_equity2: float
    scoop_equity1: float
    scoop_equity2: float
    samples: int


@router.post("/hi-lo/equity/calculate", response_model=OmahaHiLoEquityResponse)
async def calculate_omaha_hi_lo_equity(request: OmahaHiLoEquityRequest):
    """
    Calculate Omaha Hi/Lo (8-or-better) equity for two hands.
    
    Returns high, low, and scoop equities for both hands.
    """
    if len(request.hand1) != 4:
        raise HTTPException(status_code=400, detail="hand1 must have 4 cards")
    if len(request.hand2) != 4:
        raise HTTPException(status_code=400, detail="hand2 must have 4 cards")
    if len(request.board) > 5:
        raise HTTPException(status_code=400, detail="board can have at most 5 cards")
    
    evaluator = OmahaHiLoEvaluator()
    equity_calc = OmahaHiLoEquity()
    
    h1_eq, h2_eq, h1_low, h2_low = equity_calc.calculate(
        request.hand1,
        request.hand2,
        request.board,
        request.samples
    )
    
    # Scoop equity = both high AND low won
    scoop1 = 0.0
    scoop2 = 0.0
    
    board_list = request.board or []
    # Simple estimate: if both equities are high, calculate scoop probability
    if board_list and len(board_list) == 5:
        # With known board, can compute exact scoop
        from gto_poker.deck import Deck
        h1_cards = [Deck.parse(c) for c in request.hand1]
        h2_cards = [Deck.parse(c) for c in request.hand2]
        board_cards = [Deck.parse(c) for c in request.board]
        result1 = evaluator.evaluate(h1_cards, board_cards)
        result2 = evaluator.evaluate(h2_cards, board_cards)
        
        # If h1 wins both halves, h1 scoops
        if result1.high_rank_key > result2.high_rank_key:
            if result1.can_win_low and result2.can_win_low:
                if result1.low_rank_key < result2.low_rank_key:
                    scoop1 = 1.0
                elif result1.low_rank_key == result2.low_rank_key:
                    scoop1 = 0.5
            elif result1.can_win_low and not result2.can_win_low:
                scoop1 = 1.0
        elif result1.high_rank_key == result2.high_rank_key:
            if result1.can_win_low and result2.can_win_low:
                if result1.low_rank_key < result2.low_rank_key:
                    scoop1 = 1.0
                elif result1.low_rank_key == result2.low_rank_key:
                    scoop1 = 0.5  # Split both
            elif result1.can_win_low and not result2.can_win_low:
                scoop1 = 1.0
        scoop2 = 1.0 - scoop1
    
    return OmahaHiLoEquityResponse(
        hand1=request.hand1,
        hand2=request.hand2,
        high_equity1=round(h1_eq, 2),
        high_equity2=round(h2_eq, 2),
        low_equity1=round(h1_low, 2),
        low_equity2=round(h2_low, 2),
        scoop_equity1=round(scoop1 * 100, 2),
        scoop_equity2=round(scoop2 * 100, 2),
        samples=request.samples
    )


# ============== Shortdeck Endpoints ==============

class ShortdeckEquityRequest(BaseModel):
    """Request for Shortdeck equity calculation."""
    hand1: List[str]  # 2 hole cards
    hand2: List[str]  # 2 hole cards
    board: Optional[List[str]] = []  # Known board cards (0-5)
    samples: int = 10000


class ShortdeckEquityResponse(BaseModel):
    """Response with Shortdeck equity percentages."""
    hand1: List[str]
    hand2: List[str]
    equity1: float
    equity2: float
    samples: int


@router.post("/shortdeck/equity/calculate", response_model=ShortdeckEquityResponse)
async def calculate_shortdeck_equity(request: ShortdeckEquityRequest):
    """
    Calculate Shortdeck (6+ hold'em) equity for two hands.
    
    Shortdeck uses a 36-card deck (6-A) with adjusted hand rankings:
    flush beats full house, full house beats straight.
    """
    if len(request.hand1) != 2:
        raise HTTPException(status_code=400, detail="hand1 must have 2 cards")
    if len(request.hand2) != 2:
        raise HTTPException(status_code=400, detail="hand2 must have 2 cards")
    if len(request.board) > 5:
        raise HTTPException(status_code=400, detail="board can have at most 5 cards")
    
    board_list = request.board or []
    
    equity_calc = ShortdeckEquity()
    eq1, eq2 = equity_calc.calculate(
        request.hand1,
        request.hand2,
        board_list,
        request.samples
    )
    
    return ShortdeckEquityResponse(
        hand1=request.hand1,
        hand2=request.hand2,
        equity1=round(eq1, 2),
        equity2=round(eq2, 2),
        samples=request.samples
    )


__all__ = ["router"]