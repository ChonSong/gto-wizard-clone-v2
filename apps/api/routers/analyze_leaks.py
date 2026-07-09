"""
Analyze Leaks Router.

Provides endpoint for comparing parsed hands against GTO baselines
to identify strategic leaks with actionable feedback.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from apps.api.services.gto_comparison import (
    GTOComparisonResult,
    compare_to_gto,
    summarize_leaks,
)
from apps.api.services.gto_comparison import SpotCategory
from apps.api.services.strategy_storage import get_strategy_storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/leaks", tags=["leaks"])


class HandParseRequest(BaseModel):
    """Request model for hand parsing and leak analysis."""

    hand_text: str = Field(..., description="Raw hand history text (PokerStars or GGPoker format)")
    hero_name: Optional[str] = Field(None, description="Hero player name override")
    game_type: str = Field("nlh", description="Game type (nlh, plo)")
    players: int = Field(2, ge=2, le=10, description="Number of players")


class LeakAnalysisResponse(BaseModel):
    """Response model for leak analysis."""

    hand_id: str
    hero_name: str
    street: str
    board: str
    pot_size: float
    total_ev_loss: float
    leak_count: int
    leaks: List[Dict[str, Any]]
    summary: str
    gto_strategies_used: bool = False


class SingleLeakResponse(BaseModel):
    """Response model for a single leak comparison."""

    spot_category: str
    ev_loss: float
    gto_action: str
    gto_frequency: float
    user_action: str
    user_frequency: float
    recommendation: str
    severity: str
    board_texture: Optional[str] = None
    position: Optional[str] = None
    pot_size: Optional[float] = None


class LeakSummaryResponse(BaseModel):
    """Response model for aggregated leak summary."""

    total_ev_loss: float
    leak_count: int
    high_severity: List[Dict[str, Any]]
    medium_severity: List[Dict[str, Any]]
    low_severity: List[Dict[str, Any]]
    summary: str


@router.post("/analyze", response_model=LeakAnalysisResponse)
async def analyze_hand_leaks(request: HandParseRequest) -> LeakAnalysisResponse:
    """
    Analyze a hand history for GTO leaks.

    Parses the hand history, extracts actions by street, and compares
    against GTO baselines to identify strategic leaks with actionable
    recommendations.
    """
    # Import parsers
    from gto_poker.hand_history import parse_pokerstars_hand, parse_ggpoker_hand

    # Try to determine format and parse
    hand_text = request.hand_text.strip()

    if "PokerStars" in hand_text:
        try:
            hand_parsed = parse_pokerstars_hand(hand_text)
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Failed to parse PokerStars hand: {str(e)}"
            )
    elif "GGPoker" in hand_text:
        try:
            hand_parsed = parse_ggpoker_hand(hand_text)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse GGPoker hand: {str(e)}")
    else:
        # Try PokerStars format by default
        try:
            hand_parsed = parse_pokerstars_hand(hand_text)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not parse hand history: {str(e)}")

    # Get hero name
    hero_name = request.hero_name or hand_parsed.hero_name()
    if hero_name is None:
        raise HTTPException(
            status_code=400, detail="Could not determine hero player. Please specify hero_name."
        )

    # Get board string
    board_str = ""
    if hand_parsed.board.flop:
        board_str = "".join(hand_parsed.board.flop)
        if hand_parsed.board.turn:
            board_str += hand_parsed.board.turn
        if hand_parsed.board.river:
            board_str += hand_parsed.board.river

    # Determine current street based on actions
    street = "preflop"
    if hand_parsed.board.flop:
        street = "flop"
    if hand_parsed.board.turn:
        street = "turn"
    if hand_parsed.board.river:
        street = "river"

    # Compare to GTO and get leaks
    leaks = await compare_to_gto(hand_parsed, hero_name)

    # Summarize leaks
    summary = summarize_leaks(leaks)

    # Try to get GTO strategies from storage for context
    gto_strategies_used = False
    try:
        storage = await get_strategy_storage()
        if board_str:
            board_hash = board_str
            strategy = await storage.get_strategy_by_params(
                street=street,
                board_hash=board_hash,
                bet_size=0.5,
                stack_depth=100,
                game_type="nlh",
                players=request.players,
            )
            if strategy:
                gto_strategies_used = True
    except Exception as e:
        logger.debug(f"Could not fetch GTO strategies: {e}")

    return LeakAnalysisResponse(
        hand_id=hand_parsed.hand_id,
        hero_name=hero_name,
        street=street,
        board=board_str,
        pot_size=hand_parsed.pot,
        total_ev_loss=summary["total_ev_loss"],
        leak_count=summary["leak_count"],
        leaks=[
            {
                "spot_category": l.spot_category,
                "ev_loss": l.ev_loss,
                "gto_action": l.gto_action,
                "gto_frequency": l.gto_frequency,
                "user_action": l.user_action,
                "user_frequency": l.user_frequency,
                "recommendation": l.recommendation,
                "severity": l.severity,
                "board_texture": l.board_texture,
                "position": l.position,
                "pot_size": l.pot_size,
            }
            for l in leaks
        ],
        summary=summary["summary"],
        gto_strategies_used=gto_strategies_used,
    )


@router.get("/compare", response_model=List[SingleLeakResponse])
async def compare_action_to_gto(
    street: str = Query(..., description="Street: preflop, flop, turn, river"),
    board: str = Query("", description="Board cards (e.g., 'Kd7h2c' or empty for preflop)"),
    position: str = Query(..., description="Position: btn, sb, bb, utg, co"),
    action: str = Query(..., description="User action: bet, check, call, raise, fold"),
    pot_size: float = Query(100.0, description="Pot size in chips"),
    stack_depth: int = Query(100, description="Stack depth in big blinds"),
    is_oop: bool = Query(False, description="Is player out of position"),
    game_type: str = Query("nlh", description="Game type (nlh, plo)"),
    players: int = Query(2, description="Number of players"),
) -> List[SingleLeakResponse]:
    """
    Compare a single action against GTO baseline for a given spot.

    This endpoint allows direct comparison of a specific action without
    needing to parse a full hand history.
    """
    from apps.api.services.gto_comparison import (
        BoardTexture,
        SpotCategory,
        calculate_ev_loss,
        classify_board_texture,
        determine_spot_category,
        generate_recommendation,
        normalize_action,
        GTO_BASELINE,
    )

    # Classify board texture
    board_texture = classify_board_texture(board)

    # Determine spot category
    action_history = [{"action": normalize_action(action), "street": street}]
    spot_cat = determine_spot_category(
        street=street,
        board=board,
        position=position,
        pot_size=pot_size,
        stack_depth=stack_depth,
        action_history=action_history,
        is_oop=is_oop,
    )

    # Get GTO baseline
    baseline = GTO_BASELINE.get(spot_cat, {})

    if not baseline:
        raise HTTPException(
            status_code=404, detail=f"No GTO baseline found for spot category: {spot_cat.value}"
        )

    # Determine GTO recommended action
    gto_action = max(baseline.keys(), key=lambda k: baseline[k])
    gto_freq = baseline[gto_action]

    # Calculate EV loss
    ev_loss = calculate_ev_loss(
        user_action=normalize_action(action),
        gto_action=gto_action,
        gto_frequency=gto_freq,
        pot_size=pot_size,
        stack_depth=stack_depth,
    )

    # Generate recommendation
    recommendation = generate_recommendation(
        user_action=normalize_action(action),
        gto_action=gto_action,
        gto_frequency=gto_freq,
        spot_category=spot_cat,
        board_texture=board_texture,
        pot_size=pot_size,
    )

    severity = "high" if ev_loss >= 0.5 else "medium" if ev_loss >= 0.2 else "low"

    return [
        SingleLeakResponse(
            spot_category=spot_cat.value,
            ev_loss=ev_loss,
            gto_action=gto_action,
            gto_frequency=gto_freq,
            user_action=normalize_action(action),
            user_frequency=0.0,
            recommendation=recommendation,
            severity=severity,
            board_texture=board_texture.value,
            position=position,
            pot_size=pot_size,
        )
    ]


@router.post("/summary", response_model=LeakSummaryResponse)
async def get_leak_summary(
    leaks: List[Dict[str, Any]],
) -> LeakSummaryResponse:
    """
    Get aggregated summary of multiple leaks.

    Takes a list of leak results and returns aggregated statistics.
    """
    from apps.api.services.gto_comparison import GTOComparisonResult, summarize_leaks as summarize

    # Convert dicts back to GTOComparisonResult
    results = []
    for leak in leaks:
        try:
            results.append(
                GTOComparisonResult(
                    spot_category=leak.get("spot_category", ""),
                    ev_loss=leak.get("ev_loss", 0.0),
                    gto_action=leak.get("gto_action", ""),
                    gto_frequency=leak.get("gto_frequency", 0.0),
                    user_action=leak.get("user_action", ""),
                    user_frequency=leak.get("user_frequency", 0.0),
                    recommendation=leak.get("recommendation", ""),
                    severity=leak.get("severity", "low"),
                    board_texture=leak.get("board_texture"),
                    position=leak.get("position"),
                    pot_size=leak.get("pot_size"),
                )
            )
        except Exception:
            continue

    summary = summarize(results)

    return LeakSummaryResponse(
        total_ev_loss=summary["total_ev_loss"],
        leak_count=summary["leak_count"],
        high_severity=[
            {
                "spot_category": l.spot_category,
                "ev_loss": l.ev_loss,
                "gto_action": l.gto_action,
                "user_action": l.user_action,
                "recommendation": l.recommendation,
            }
            for l in summary.get("high_severity", [])
        ],
        medium_severity=[
            {
                "spot_category": l.spot_category,
                "ev_loss": l.ev_loss,
                "gto_action": l.gto_action,
                "user_action": l.user_action,
                "recommendation": l.recommendation,
            }
            for l in summary.get("medium_severity", [])
        ],
        low_severity=[
            {
                "spot_category": l.spot_category,
                "ev_loss": l.ev_loss,
                "gto_action": l.gto_action,
                "user_action": l.user_action,
                "recommendation": l.recommendation,
            }
            for l in summary.get("low_severity", [])
        ],
        summary=summary["summary"],
    )


@router.get("/baseline/{spot_category}")
async def get_gto_baseline(
    spot_category: str,
    board_texture: str = Query("", description="Optional board texture override"),
) -> Dict[str, Any]:
    """
    Get GTO baseline frequencies for a specific spot category.
    """
    from apps.api.services.gto_comparison import SpotCategory, GTO_BASELINE

    try:
        cat = SpotCategory(spot_category)
    except ValueError:
        valid = [e.value for e in SpotCategory]
        raise HTTPException(status_code=400, detail=f"Invalid spot_category. Valid values: {valid}")

    baseline = GTO_BASELINE.get(cat, {})

    if not baseline:
        return {"spot_category": spot_category, "baseline": {}, "message": "No baseline data"}

    return {
        "spot_category": spot_category,
        "baseline": baseline,
        "description": _get_spot_description(cat),
    }


def _get_spot_description(spot_cat: SpotCategory) -> str:
    """Get description for spot category."""
    descriptions = {
        SpotCategory.CBET_FLOP: "Continuation bet on the flop after raising preflop",
        SpotCategory.CHECK_RAISE_FLOP: "Check-raise spot on the flop",
        SpotCategory.FLOAT_FLOP: "Floating the flop with a weak hand",
        SpotCategory.DELAY_CBET: "Delayed continuation bet on later streets",
        SpotCategory.BARREL_TURN: "Second barrel on the turn",
        SpotCategory.THIRD_BARREL: "Third barrel (river) as bluff or value",
        SpotCategory.CHECK_FOLD: "Check-fold on the flop or turn",
        SpotCategory.CHECK_CALL: "Check-call on the flop or turn",
        SpotCategory.LEAD_RIVER: "Leading into the river",
        SpotCategory.CHECK_RAISE_TURN: "Check-raise on the turn",
        SpotCategory.DONK_BET: "Donk bet after being the preflop caller",
        SpotCategory.HERO_3BET: "Hero 3-bet preflop",
        SpotCategory.HERO_4BET: "Hero 4-bet preflop",
    }
    return descriptions.get(spot_cat, "Unknown spot category")
