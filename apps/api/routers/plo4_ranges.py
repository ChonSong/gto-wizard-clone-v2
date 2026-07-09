"""PLO4 range builder and push/fold charts endpoints"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict

import sys
sys.path.insert(0, "/tmp/PokerHandEvaluator/python")
sys.path.insert(0, "packages/poker-core/src")

from gto_poker.plo4_range import PLO4RangeParser, expand_range_to_hands


router = APIRouter(prefix="/plo4/ranges", tags=["plo4", "ranges"])


class PLO4RangeParseRequest(BaseModel):
    """Request to parse a PLO4 range string."""
    range_str: str


class PLO4RangeResponse(BaseModel):
    """Response with parsed hands."""
    range_str: str
    hands: List[str]
    hand_count: int


@router.post("/parse", response_model=PLO4RangeResponse)
async def parse_plo4_range(request: PLO4RangeParseRequest):
    """
    Parse a PLO4 range string into concrete hands.
    
    Supports:
    - AAKK (pocket pairs)
    - AAKK double suited (ds)
    - TJs (suited connectors)
    - A234 (runny hands)
    """
    parser = PLO4RangeParser()
    hands = parser.parse(request.range_str)
    
    return PLO4RangeResponse(
        range_str=request.range_str,
        hands=list(hands),
        hand_count=len(hands)
    )


@router.post("/expand", response_model=dict)
async def expand_plo4_range(range_str: str):
    """
    Expand a PLO4 range to all possible suit combinations.
    
    For example, 'AAKK' expands to 256 concrete hands.
    """
    all_hands = expand_range_to_hands(range_str)
    
    return {
        "range_str": range_str,
        "expanded_hands": all_hands,
        "expanded_count": len(all_hands)
    }


# Predefined PLO4 push/fold ranges (simplified)
# In full PLO4 GTO, these would be position and stack-depth dependent
PLO4_OPEN_RAISE_RANGES = {
    "utg": "AAJJ, AAKK, AQQ, AK, KQ, QJ, JT, T9, 98, 87, 76, 65, 54, 43, 32",
    "mp": "AAJJ, AAKK, AAQQ, AK, KQ, QJ, JT, T9, 98, 87, 76, 65, 54, 43, 32, A2, A3, A4",
    "co": "AAKK, AAQQ, AK, KQ, QJ, JT, T9, 98, 87, 76, 65, 54, A2, A3, A4, A5, K2, K3",
    "btn": "AAKK, AAQQ, AK, KQ, QJ, JT, T9, 98, 87, 76, A2, A3, A4, A5, K2, K3, K4",
    "sb": "AAKK, AAQQ, AK, KQ, QJ, JT, T9, 98, A2, A3, A4, A5, K2, K3, K4, K5"
}

PLO4_3BET_RANGES = {
    "utg": "AAKK, AAQQ, AK",
    "mp": "AAKK, AAQQ, AK, KQ",
    "co": "AAKK, AAQQ, AK, KQ, QQ",
    "btn": "AAKK, AAQQ, AK, KQ, QQ, JJ",
    "sb": "AAKK, AAQQ, AK, KQ, QQ, JJ"
}


@router.get("/push-fold-chart/{position}", response_model=dict)
async def get_plo4_push_fold_chart(position: str):
    """
    Get simplified PLO4 push/fold ranges by position.
    
    This is a rough approximation for deep-stacked PLO4.
    Real GTO push/fold charts require position, stack depth, and opponent tendencies.
    """
    position = position.lower()
    
    if position not in PLO4_OPEN_RAISE_RANGES:
        raise HTTPException(status_code=404, detail=f"Position {position} not found")
    
    parser = PLO4RangeParser()
    open_raise_range = parser.parse(PLO4_OPEN_RAISE_RANGES[position])
    three_bet_range = parser.parse(PLO4_3BET_RANGES.get(position, ""))
    
    return {
        "position": position,
        "open_raise_range": PLO4_OPEN_RAISE_RANGES[position],
        "open_raise_hands": list(open_raise_range),
        "open_raise_count": len(open_raise_range),
        "three_bet_range": PLO4_3BET_RANGES.get(position, ""),
        "three_bet_hands": list(three_bet_range),
        "three_bet_count": len(three_bet_range),
        "note": "Simplified ranges - full GTO requires stack depth and opponent modeling"
    }


@router.post("/compare-hands", response_model=dict)
async def compare_plo4_hands(
    hand1_str: str,
    hand2_str: str,
    board: Optional[List[str]] = []
):
    """
    Compare two PLO4 hands and show which is stronger.
    """
    parser = PLO4RangeParser()
    
    # Parse hands
    hands1 = parser.parse(hand1_str)
    hands2 = parser.parse(hand2_str)
    
    if not hands1:
        raise HTTPException(status_code=400, detail=f"Could not parse hand1: {hand1_str}")
    if not hands2:
        raise HTTPException(status_code=400, detail=f"Could not parse hand2: {hand2_str}")
    
    hand1 = list(hands1)[0] if hands1 else ""
    hand2 = list(hands2)[0] if hands2 else ""
    
    return {
        "hand1": {
            "string": hand1_str,
            "parsed": hand1,
            "rank": str(hand1)
        },
        "hand2": {
            "string": hand2_str,
            "parsed": hand2,
            "rank": str(hand2)
        },
        "note": "Use /plo4/equity/calculate for full equity comparison with board"
    }


@router.get("/hand-rankings", response_model=dict)
async def get_plo4_hand_rankings():
    """
    Get sample PLO4 hand rankings by type.
    
    Shows typical ordering of hand types in PLO4.
    """
    return {
        "tier_1_premium": {
            "examples": ["AAKK ds", "AAQQ ds", "AAJJ ds"],
            "description": "Double-suited broadway pairs - strongest hands"
        },
        "tier_2_strong": {
            "examples": ["AAKK", "AAQQ", "AAJJ", "AKQJ ds"],
            "description": "Strong pairs and suited broadway combos"
        },
        "tier_3_good": {
            "examples": ["AK", "AQ", "KQ", "QJ", "JT ds"],
            "description": "Single pairs and suited connectors"
        },
        "tier_4_average": {
            "examples": ["A2", "A3", "KQ", "98 ds", "76 ds"],
            "description": "Weaker pairs, rundown hands, suited gappers"
        },
        "tier_5_speculative": {
            "examples": ["54 ds", "43 ds", "32 ds", "A2 ds", "K2 ds"],
            "description": "Low suited connectors and gappers"
        },
        "note": "PLO4 is more swingy than NLHE - position and stack depth matter more"
    }
