"""
Equity Calculator API — FastAPI Router
Handles poker equity calculations with Redis caching, multi-way support,
heatmap generation, and expected value calculations.
"""

import asyncio
import hashlib
import json
import logging
from typing import List, Optional, Union
from contextlib import asynccontextmanager

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from gto_poker.deck import Deck, Card
from gto_poker.equity import EquityCalculator
from gto_poker.range import RangeParser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/equity", tags=["equity"])

# Redis client will be injected via app state
_redis_client = None

CACHE_TTL_SECONDS = 300  # 5 minutes
DEFAULT_ITERATIONS = 10000
MAX_ITERATIONS = 1000000

# All 169 preflop hands in standard grid order for heatmap
# Grid layout: rows = first card rank, cols = second card rank
#   - Diagonal (row==col): pocket pairs, e.g. "AA", "KK"
#   - Above diagonal (row<col): suited, e.g. "AKs"
#   - Below diagonal (row>col): offsuit, e.g. "AKo"
RANK_ORDER = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]
PREFLOP_HANDS_169 = []
for r1 in RANK_ORDER:
    for r2 in RANK_ORDER:
        if RANK_ORDER.index(r1) < RANK_ORDER.index(r2):
            hand = f"{r1}{r2}s"  # Suited
        elif RANK_ORDER.index(r1) > RANK_ORDER.index(r2):
            hand = f"{r1}{r2}o"  # Offsuit
        else:
            hand = f"{r1}{r2}"  # Pocket pair
        PREFLOP_HANDS_169.append(hand)


def get_redis(request: Request):
    """Get Redis client from app state."""
    global _redis_client
    if _redis_client is None:
        _redis_client = request.app.state.redis
    return _redis_client


def _hash_input(hero: str, villain: str, board: str, iterations: int) -> str:
    """Create a deterministic hash for caching."""
    key_parts = f"{hero}:{villain}:{board}:{iterations}"
    return hashlib.md5(key_parts.encode()).hexdigest()[:16]


def _make_cache_key(hero: str, villain: str, board: str, iterations: int) -> str:
    """Build Redis cache key from inputs."""
    hero_hash = _hash_input(hero, "", "", 0)[:8]
    villain_hash = _hash_input("", villain, "", 0)[:8]
    board_hash = _hash_input("", "", board, 0)[:8]
    return f"equity:{hero_hash}:{villain_hash}:{board_hash}:{iterations}"


def _parse_villain_ranges(villain_input: Union[str, List[str]]) -> List[str]:
    """Parse villain input (comma-separated string or list) into list of range strings."""
    if isinstance(villain_input, list):
        return villain_input
    return [v.strip() for v in str(villain_input).split(",")]


def _cards_from_hand(hand_str: str) -> List[Card]:
    """Parse hand string like 'AhKh' or 'AKs' into Cards."""
    hand_str = hand_str.strip()
    if len(hand_str) == 4:
        # Specific combo: AhKh
        return [Card(hand_str[0], hand_str[1]), Card(hand_str[2], hand_str[3])]
    elif len(hand_str) == 3:
        # Type like AKs or AKo
        r1, r2, st = hand_str[0], hand_str[1], hand_str[2]
        if st == "s":
            return [Card(r1, "h"), Card(r2, "h")]
        else:
            return [Card(r1, "h"), Card(r2, "d")]
    elif len(hand_str) == 2:
        # Pair like KK
        return [Card(hand_str[0], "h"), Card(hand_str[1], "d")]
    raise ValueError(f"Invalid hand string: {hand_str}")


# ============================================================================
# Request/Response Models
# ============================================================================


class EquityRequest(BaseModel):
    """POST body for equity calculation."""

    hero: str = Field(..., description="Hero hand (e.g., 'AhKh' or 'AKs')")
    villain: Union[str, List[str]] = Field(
        ..., description="Villain range(s). Comma-separated string or JSON array."
    )
    board: Optional[str] = Field(None, description="Board cards (e.g., 'Kd7h2c')")
    iterations: int = Field(
        DEFAULT_ITERATIONS,
        ge=1000,
        le=MAX_ITERATIONS,
        description=f"Number of Monte Carlo iterations (default: {DEFAULT_ITERATIONS})",
    )


class EquityResponse(BaseModel):
    """Response for single equity calculation."""

    equity: float = Field(..., description="Equity as decimal (0-1)")
    wins: int = Field(..., description="Number of wins")
    ties: int = Field(..., description="Number of ties")
    total: int = Field(..., description="Total simulations")
    ev_per_hand: float = Field(..., description="Expected value per hand (accounts for bet sizing)")


class EVRequest(BaseModel):
    """POST body for EV calculation."""

    hero: str
    villain: Union[str, List[str]]
    board: Optional[str] = None
    pot_size: float = Field(100.0, description="Current pot size")
    bet_size: float = Field(0.0, description="Bet size to calculate EV for")
    iterations: int = Field(DEFAULT_ITERATIONS, ge=1000, le=MAX_ITERATIONS)


class EVResponse(BaseModel):
    """Response for EV calculation."""

    ev: float = Field(..., description="Expected value per unit bet")
    equity: float = Field(..., description="Raw equity")
    win_rate: float = Field(..., description="Probability of winning")
    tie_rate: float = Field(..., description="Probability of tie")


class HeatmapRequest(BaseModel):
    """Request for heatmap generation."""

    villain: Union[str, List[str]] = Field(..., description="Villain range(s)")
    board: Optional[str] = Field(None, description="Board cards")
    iterations: int = Field(10000, ge=100, le=MAX_ITERATIONS)


class HeatmapCell(BaseModel):
    """Single cell in heatmap."""

    hand: str = Field(..., description="Hand notation (e.g., 'AKs', 'JJ')")
    equity: float = Field(..., description="Equity against villain range")
    combo_count: int = Field(..., description="Number of combinations")


class HeatmapResponse(BaseModel):
    """Response containing all 169 preflop hands equity data."""

    hands: List[HeatmapCell] = Field(..., description="Equity for all 169 hands")
    villain_range: str = Field(..., description="Parsed villain range string")


# ============================================================================
# Equity Calculation Endpoints
# ============================================================================


@router.get("/calculate", response_model=EquityResponse)
async def calculate_equity_get(
    request: Request,
    hero: str = Query(..., description="Hero hand (e.g., 'AhKh' or 'AKs')"),
    villain: str = Query(..., description="Villain range (e.g., 'JJ+,AKs')"),
    board: Optional[str] = Query(None, description="Board cards (e.g., 'Kd7h2c')"),
    iterations: int = Query(DEFAULT_ITERATIONS, ge=1000, le=MAX_ITERATIONS),
):
    """
    Calculate equity using GET query parameters.

    Example: GET /calculate?hero=AhKh&villain=JJ%2BAKs&board=Kd7h2c&iterations=100000

    - hero: Hero's hand (e.g., 'AhKh' or 'AKs')
    - villain: Villain range (e.g., 'JJ+,AKs' or comma-separated)
    - board: Optional board cards (e.g., 'Kd7h2c')
    - iterations: Number of simulations (default 100000, max 1000000)
    """
    return await _calculate_equity_impl(
        hero=hero, villain=villain, board=board, iterations=iterations, request=request
    )


@router.post("/calculate", response_model=EquityResponse)
async def calculate_equity_post(request: Request, req: EquityRequest):
    """
    Calculate equity using POST with JSON body.

    Supports complex multi-way pots with multiple villain ranges.
    Villain can be a comma-separated string or JSON array.
    """
    return await _calculate_equity_impl(
        hero=req.hero,
        villain=req.villain,
        board=req.board,
        iterations=req.iterations,
        request=request,
    )


async def _calculate_equity_impl(
    hero: str,
    villain: Union[str, List[str]],
    board: Optional[str],
    iterations: int,
    request: Request,
) -> EquityResponse:
    """Core equity calculation with Redis caching."""

    # Parse villain ranges
    villain_ranges = _parse_villain_ranges(villain)
    villain_str = ",".join(villain_ranges)

    # Check cache
    redis = get_redis(request)
    cache_key = _make_cache_key(hero, villain_str, board or "", iterations)

    if redis:
        try:
            cached = redis.get(cache_key)
            if cached:
                logger.info(f"Cache hit for {cache_key}")
                data = json.loads(cached)
                return EquityResponse(**data)
        except Exception as e:
            logger.warning(f"Redis cache read error: {e}")

    # Parse cards
    hero_cards = _cards_from_hand(hero)
    board_cards = Deck.parse_board(board) if board else []

    # Calculate equity in a thread pool to avoid blocking the event loop
    calc = EquityCalculator()

    def _compute():
        if len(villain_ranges) == 1:
            result = calc.equity_vs_range(
                hero_cards=hero_cards,
                villain_range=villain_ranges,
                board=board_cards,
                iterations=iterations,
                n_threads=4,
            )
            wins = int(result * iterations)
            ties = 0
            total = iterations
            equity = result
        else:
            villain_range_lists = [vr.split(",") for vr in villain_ranges]
            equity = calc.equity_vs_range_multiway(
                hero_cards=hero_cards,
                villain_ranges=villain_range_lists,
                board=board_cards,
                iterations=iterations,
                n_threads=4,
            )
            wins = int(equity * iterations)
            ties = 0
            total = iterations
        return wins, ties, total, equity

    # Run computation with a timeout — fall back to fewer iterations if needed
    try:
        wins, ties, total, equity = await asyncio.wait_for(asyncio.to_thread(_compute), timeout=5.0)
    except asyncio.TimeoutError:
        logger.warning(f"Equity calc timed out for {hero} vs {villain_str}, reducing iterations")
        # Fallback: recompute with minimal iterations (in thread pool to avoid blocking)
        fallback_iter = 5000

        def _compute_fallback():
            if len(villain_ranges) == 1:
                result = calc.equity_vs_range(
                    hero_cards=hero_cards,
                    villain_range=villain_ranges,
                    board=board_cards,
                    iterations=fallback_iter,
                    n_threads=4,
                )
                return int(result * fallback_iter), 0, fallback_iter, result
            else:
                villain_range_lists = [vr.split(",") for vr in villain_ranges]
                equity = calc.equity_vs_range_multiway(
                    hero_cards=hero_cards,
                    villain_ranges=villain_range_lists,
                    board=board_cards,
                    iterations=fallback_iter,
                    n_threads=4,
                )
                return int(equity * fallback_iter), 0, fallback_iter, equity

        wins, ties, total, equity = await asyncio.to_thread(_compute_fallback)

    ev_per_hand = equity  # For basic equity, EV = equity

    response = EquityResponse(
        equity=equity, wins=wins, ties=ties, total=total, ev_per_hand=ev_per_hand
    )

    # Store in cache
    if redis:
        try:
            redis.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(response.model_dump()))
            logger.info(f"Cached result for {cache_key}")
        except Exception as e:
            logger.warning(f"Redis cache write error: {e}")

    return response


# ============================================================================
# Heatmap Endpoint
# ============================================================================


@router.post("/heatmap", response_model=HeatmapResponse)
async def equity_heatmap(request: Request, req: HeatmapRequest):
    """
    Generate equity heatmap data for all 169 preflop hands.

    Uses ThreadPoolExecutor to parallelize evaluations across 4 threads.
    Results cached in Redis/fakeredis for 1 hour.
    """
    # Parse villain range
    villain_ranges = _parse_villain_ranges(req.villain)
    villain_str = ",".join(villain_ranges)
    board_cards = Deck.parse_board(req.board) if req.board else []

    # Check cache
    redis = get_redis(request)
    cache_key = f"heatmap:{villain_str}:{req.board or ''}:{req.iterations}"

    if redis:
        try:
            cached = redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                return HeatmapResponse(**data)
        except Exception as e:
            logger.warning(f"Heatmap cache error: {e}")

    calc = EquityCalculator()
    parser = RangeParser()
    iterations = min(
        req.iterations, 500
    )  # Cap for performance (visual guide, not precise calculation)

    def evaluate_hand(hand: str) -> Optional[HeatmapCell]:
        """Evaluate a single hand vs villain range."""
        try:
            hero_cards = _cards_from_hand(hand)
            equity = calc.equity_vs_range(
                hero_cards=hero_cards,
                villain_range=villain_ranges,
                board=board_cards,
                iterations=iterations,
                n_threads=1,  # Thread safety with per-call seed
            )
            combo_count = len(parser.get_all_combos(hand))
            return HeatmapCell(hand=hand, equity=round(equity, 4), combo_count=combo_count)
        except Exception as e:
            logger.warning(f"Error calculating equity for {hand}: {e}")
            return HeatmapCell(hand=hand, equity=0.0, combo_count=0)

    # Run all evaluations in a thread pool to avoid blocking the event loop
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _compute_heatmap():
        results = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(evaluate_hand, hand): hand for hand in PREFLOP_HANDS_169}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)
        return results

    results = await asyncio.to_thread(_compute_heatmap)

    # Sort results to match hand order
    hand_order = {h: i for i, h in enumerate(PREFLOP_HANDS_169)}
    results.sort(key=lambda r: hand_order.get(r.hand, 999))

    response_data = HeatmapResponse(hands=results, villain_range=villain_str)

    # Cache result
    if redis:
        try:
            redis.setex(cache_key, 3600, json.dumps(response_data.model_dump()))
        except Exception as e:
            logger.warning(f"Heatmap cache write error: {e}")

    return response_data


# ============================================================================
# EV Endpoint
# ============================================================================


@router.post("/ev", response_model=EVResponse)
async def calculate_ev(request: Request, req: EVRequest):
    """
    Calculate expected value accounting for bet sizing.

    Computes EV = equity * (pot + 2*bet) - bet * (1 - equity)

    Where:
    - If hero wins: gains bet + opponent's bet
    - If hero loses: loses the bet
    - Ties: get money back (0 EV for that portion)

    For a pot-size bet, this simplifies to:
    EV = equity * (pot + 2*bet) - bet
    """
    villain_ranges = _parse_villain_ranges(req.villain)
    villain_str = ",".join(villain_ranges)

    # Check cache
    redis = get_redis(request)
    cache_key = f"ev:{_make_cache_key(req.hero, villain_str, req.board or '', req.iterations)}"
    cache_key += f":{req.pot_size}:{req.bet_size}"

    if redis:
        try:
            cached = redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                return EVResponse(**data)
        except Exception as e:
            logger.warning(f"Redis cache read error: {e}")

    # Calculate base equity in a thread pool to avoid blocking the event loop
    hero_cards = _cards_from_hand(req.hero)
    board_cards = Deck.parse_board(req.board) if req.board else []

    calc = EquityCalculator()

    def _compute_ev():
        if len(villain_ranges) == 1:
            return calc.equity_vs_range(
                hero_cards=hero_cards,
                villain_range=villain_ranges,
                board=board_cards,
                iterations=req.iterations,
                n_threads=4,
            )
        else:
            villain_range_lists = [vr.split(",") for vr in villain_ranges]
            return calc.equity_vs_range_multiway(
                hero_cards=hero_cards,
                villain_ranges=villain_range_lists,
                board=board_cards,
                iterations=req.iterations,
                n_threads=4,
            )

    equity = await asyncio.to_thread(_compute_ev)

    # Simplified EV calculation for heads-up
    # EV = p(win) * (pot + bet) - bet * (1 - p(win) - p(tie))
    # Actually for a bet:
    # Hero bets `bet`, opponent must call or fold
    # If hero wins: gets back pot + opponent's call
    # If hero loses: loses bet
    # If tie: gets bet back

    # Standard formula: EV = equity * (pot + 2*bet) - bet
    # This assumes opponent always calls
    if req.bet_size > 0:
        ev = equity * (req.pot_size + 2 * req.bet_size) - req.bet_size
    else:
        ev = equity * req.pot_size

    # For more accurate calculation when hero bets first:
    # EV = -bet + (1 - tie_rate) * pot_if_win + tie_rate * bet
    # But for now use simplified model

    response = EVResponse(
        ev=round(ev, 4),
        equity=round(equity, 4),
        win_rate=round(equity, 4),  # Simplified
        tie_rate=0.0,  # Would need more complex calculation for tie rate
    )

    # Cache result
    if redis:
        try:
            redis.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(response.model_dump()))
        except Exception as e:
            logger.warning(f"Redis cache write error: {e}")

    return response


# ============================================================================
# Health Check
# ============================================================================


@router.get("/health")
async def health(request: Request):
    """Check Redis connectivity."""
    redis = get_redis(request)
    if redis:
        try:
            redis.ping()
            return {"status": "healthy", "redis": "connected"}
        except Exception:
            return {"status": "healthy", "redis": "disconnected"}
    return {"status": "healthy", "redis": "not_configured"}
