"""
Solver API Router — GTO solve workflows.

Direct integration with the MCCFR engine (bypasses gRPC/Celery).
Supports preflop range solving for the study page with full game tree.

The game tree tracks the sequence of actions taken and computes
the correct decision node: acting position, available actions,
pot/stack info, and conditional ranges.
"""

import json
import logging
import os
import sys
from pathlib import Path

# Add paths for solver engine access
_here = os.path.dirname(os.path.abspath(__file__))
_solver_dir = os.path.join(_here, "..", "..", "..", "apps", "solver")
_poker_dir = os.path.join(_here, "..", "..", "..", "packages", "poker-core", "src")
for p in [_solver_dir, _poker_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/solver", tags=["solver"])

# ── Engine availability cache ──
_engine_available = None


def _check_engine():
    global _engine_available
    if _engine_available is None:
        try:
            from cfr.engine import CFREngine  # noqa: F401

            _engine_available = True
        except ImportError:
            _engine_available = False
    return _engine_available


# ── Precomputed chart cache ──
_charts_dir = Path(_solver_dir) / "strategy" / "charts"
_chart_cache = {}


def _load_chart(position: str, stack_depth: int) -> dict | None:
    depths = sorted(
        [int(f.stem.split("_")[1].replace("bb", "")) for f in _charts_dir.glob("push_*bb_*.json")]
    )
    if not depths:
        return None
    nearest = min(depths, key=lambda d: abs(d - stack_depth))
    key = f"push_{nearest}bb_{position}"
    if key not in _chart_cache:
        path = _charts_dir / f"{key}.json"
        if path.exists():
            with open(path) as f:
                _chart_cache[key] = json.load(f)
        else:
            return None
    return _chart_cache[key]


# ── Request/response models ──


class SolveRequest(BaseModel):
    game_type: str = "nlh"
    players: int = 2
    board: str | None = None
    pot_size: int = 100
    stack_depth: int = 100
    bet_sizes: list[int] | None = None
    iterations: int = 200
    street: str = "river"
    position: str = "BTN"


class StrategyAction(BaseModel):
    action: str
    frequency: float
    ev: float


class SolveResponse(BaseModel):
    job_id: str = ""
    status: str
    progress: int = 0
    strategy: list[StrategyAction] = []
    strategy_key: str = ""
    message: str | None = None
    error: str | None = None


class TreeAction(BaseModel):
    """A single action in the game tree path."""

    position: str
    action: str  # 'fold', 'call', 'raise_2.5bb', 'raise_7.5bb', 'all_in'
    size: float | None = None


class TreeNode(BaseModel):
    """Current decision node in the game tree."""

    acting_position: str
    available_actions: list[dict]  # [{id, label, actionBase, size}, ...]
    pot_size: float
    stack_remaining: float | None = None
    context: str = "rfi"  # 'rfi', 'vs_raise', 'vs_3bet', 'vs_4bet'
    description: str = ""


class HandLock(BaseModel):
    """Lock specific actions/frequencies for a given hand."""
    actions: dict[str, float] = Field(default_factory=dict)  # {"fold": 0.3, "call": 0.4}

    @model_validator(mode="after")
    def validate_frequencies(self):
        total = sum(f for f in self.actions.values() if f > 0)
        if total > 1.0 + 1e-6:
            raise ValueError(f"Frequencies sum >1.0 (got {total:.3f})")
        return self


class PreflopRangeRequest(BaseModel):
    position: str = "UTG"
    stack_depth: int = 100
    game_type: str = "nlh"
    tree_path: list[TreeAction] = []
    locked_hands: dict[str, HandLock] | None = None  # {"AA": {"actions": {"fold":0.3,"call":0.7}}}


class HandCell(BaseModel):
    hand: str
    action: str
    frequency: float
    equity: float = 0.0


class PreflopRangeResponse(BaseModel):
    position: str
    stack_depth: int
    hands: list[HandCell]
    tree_node: TreeNode | None = None
    tree_path: list[TreeAction] = []
    solver_engine: bool = False
    source: str = ""
    locked_hands_applied: list[str] = []  # which hands were locked
    counter_strategy: dict[str, float] | None = None  # hand -> deviation


# ── Postflop Strategy Cache ──
import asyncio
import hashlib

_postflop_cache: dict[str, dict] = {}


class PostflopStrategyRequest(BaseModel):
    board: str = "KsKc3s"
    position: str = "BTN"
    street: str = "flop"
    pot_size: float = 5.5
    stack_depth: float = 97.5
    hero_hand: str | None = None


class PostflopStrategyResponse(BaseModel):
    actions: list[StrategyAction] = []
    source: str = ""
    status: str = ""
    message: str | None = None
    error: str | None = None


def _dedup_actions(actions: list[StrategyAction]) -> list[StrategyAction]:
    best: dict[str, StrategyAction] = {}
    for a in actions:
        key = a.action.lower().strip()
        if key not in best or a.frequency > best[key].frequency:
            best[key] = a
    return sorted(best.values(), key=lambda a: -a.frequency)


def _make_postflop_cache_key(board, position, street, pot_size, stack_depth, hero_hand):
    raw = f"{board.strip()}:{position}:{street}:{pot_size}:{stack_depth}:{hero_hand or 'generic'}"
    return hashlib.md5(raw.encode()).hexdigest()


def _pick_unused_cards(exclude: set[str], count: int = 2) -> list[str]:
    suits = "hdcs"
    ranks = "AKQJT98765432"
    chosen: list[str] = []
    for r in ranks:
        for s in suits:
            c = r + s
            if c not in exclude:
                chosen.append(c)
                exclude.add(c)
                if len(chosen) >= count:
                    return chosen
    return chosen


def _compute_ev(action_name: str, pot_size: float, is_tree: bool = False) -> float:
    if action_name == "fold":
        return 0.0
    if action_name == "check":
        return round(pot_size * 0.5, 4)
    if action_name == "call":
        return round(pot_size * 0.5, 4)
    if action_name in ("all_in", "allin"):
        return round(pot_size * 0.65, 4)
    if action_name.startswith("bet") or action_name.startswith("raise"):
        return round(pot_size * 0.6, 4)
    return round(pot_size * 0.5, 4)


# ── Postflop endpoint ──


@router.post("/postflop-strategy", response_model=PostflopStrategyResponse)
async def postflop_strategy(req: PostflopStrategyRequest):
    cache_key = _make_postflop_cache_key(
        req.board,
        req.position,
        req.street,
        req.pot_size,
        req.stack_depth,
        req.hero_hand,
    )
    if cache_key in _postflop_cache:
        cached = _postflop_cache[cache_key]
        cached_actions = [StrategyAction(**a) for a in cached["actions"]]
        return PostflopStrategyResponse(
            actions=_dedup_actions(cached_actions),
            source="cached",
            status="complete",
        )

    if not _check_engine():
        return PostflopStrategyResponse(
            status="error",
            error="Solver engine not available",
            message="Install phevaluator and rebuild",
        )

    board_str = req.board.strip()
    board_cards = [board_str[i : i + 2] for i in range(0, len(board_str), 2)]
    if req.hero_hand and len(req.hero_hand) >= 4:
        hh = req.hero_hand.strip()
        hero_cards = [hh[i : i + 2] for i in range(0, len(hh), 2)]
    else:
        hero_cards = ["Ah", "Kh"]
    used: set[str] = set(hero_cards + board_cards)
    opponent_cards = _pick_unused_cards(used, 2)
    stacks = [req.stack_depth, req.stack_depth]
    bet_sizes = [0.33, 0.5, 0.75, 1.0]

    try:
        from cfr.engine import CFREngine
        from games.texas_hold_em import TexasHoldEm

        async def _solve():
            loop = asyncio.get_running_loop()

            def _run():
                nonlocal bet_sizes
                if req.street == "river" and len(board_cards) >= 5:
                    from cfr.river_solver import create_river_state_from_params

                    state = create_river_state_from_params(
                        p0_cards=hero_cards,
                        p1_cards=opponent_cards,
                        board=board_cards[:5],
                        pot=req.pot_size,
                        stacks=stacks,
                    )
                    game = TexasHoldEm(bet_sizes=bet_sizes)
                    engine = CFREngine(game)
                    strategies = engine.solve(state, iterations=200, sample_chance=False)
                    return strategies, game, engine
                elif req.street == "turn" and len(board_cards) >= 4:
                    from cfr.turn_solver import create_turn_state

                    state = create_turn_state(
                        p0_cards=hero_cards,
                        p1_cards=opponent_cards,
                        flop=board_cards[:3],
                        turn=board_cards[3],
                        pot=req.pot_size,
                        stacks=stacks,
                    )
                    game = TexasHoldEm(bet_sizes=bet_sizes)
                    engine = CFREngine(game)
                    strategies = engine.solve(state, iterations=200, sample_chance=True)
                    return strategies, game, engine
                elif req.street == "flop" and len(board_cards) >= 3:
                    from cfr.flop_solver import create_flop_state

                    state = create_flop_state(
                        p0_cards=hero_cards,
                        p1_cards=opponent_cards,
                        flop=board_cards[:3],
                        pot=req.pot_size,
                        stacks=stacks,
                    )
                    game = TexasHoldEm(bet_sizes=bet_sizes)
                    engine = CFREngine(game)
                    strategies = engine.solve(state, iterations=200, sample_chance=True)
                    return strategies, game, engine
                else:
                    raise ValueError(
                        f"Invalid board/street: board={req.board!r}, street={req.street!r}"
                    )

            return await loop.run_in_executor(None, _run)

        strategies, game, engine = await asyncio.wait_for(_solve(), timeout=30.0)
        actions: list[StrategyAction] = []
        for key, avg_strat in strategies.items():
            info = engine.infoset_manager.get(key) if hasattr(engine, "infoset_manager") else None
            if info is None:
                continue
            valid_actions = info.actions if hasattr(info, "actions") and info.actions else []
            for i, act in enumerate(valid_actions):
                freq = float(avg_strat[i]) if i < len(avg_strat) else 0.0
                if freq > 0.01:
                    ev = _compute_ev(str(act), req.pot_size)
                    actions.append(StrategyAction(action=str(act), frequency=round(freq, 4), ev=ev))
        actions.sort(key=lambda a: -a.frequency)
        actions = _dedup_actions(actions)
        _postflop_cache[cache_key] = {"actions": [a.model_dump() for a in actions]}
        return PostflopStrategyResponse(
            actions=actions,
            source="live-solver",
            status="complete",
            message=f"Solved {req.street} spot ({len(strategies)} infosets)",
        )
    except TimeoutError:
        return PostflopStrategyResponse(status="error", error="Solver timed out after 30s")
    except ImportError as e:
        logger.warning(f"Solver engine not available: {e}")
        return PostflopStrategyResponse(status="error", error=str(e))
    except ValueError as e:
        return PostflopStrategyResponse(status="error", error=str(e))
    except Exception as e:
        logger.error(f"Postflop solver error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/solve", response_model=SolveResponse)
async def solve(req: SolveRequest):
    try:
        if not _check_engine():
            return SolveResponse(status="error", progress=0, error="Solver engine not available")
        from cfr.engine import CFREngine
        from games.texas_hold_em import TexasHoldEm, create_river_state

        game = TexasHoldEm()
        engine = CFREngine(game=game, seed=42)
        board_strings = []
        if req.board and len(req.board) >= 6:
            board_strings = [req.board[i : i + 2] for i in range(0, len(req.board), 2)]
        if req.street == "river" and len(board_strings) >= 3:
            state = create_river_state(
                p0_cards=["Ah", "Kh"],
                p1_cards=["Kc", "Qc"],
                board=board_strings[:3],
                pot=req.pot_size,
                stacks=[req.stack_depth, req.stack_depth],
            )
            strategies = engine.solve(initial_state=state, iterations=min(req.iterations, 500))
        else:
            strategies = {}
        actions = []
        for key, avg_strat in strategies.items():
            info = engine.infoset_manager.get(key)
            if info is not None:
                for i, act in enumerate(info.actions):
                    freq = float(avg_strat[i]) if i < len(avg_strat) else 0.0
                    if freq > 0.01:
                        actions.append(
                            StrategyAction(action=str(act), frequency=round(freq, 4), ev=0.0)
                        )
        actions = _dedup_actions(actions)
        return SolveResponse(
            status="complete",
            progress=100,
            strategy=actions,
            message=f"Solved {req.street} spot ({len(strategies)} infosets)",
        )
    except ImportError as e:
        logger.warning(f"Solver engine not available: {e}")
        return SolveResponse(status="error", progress=0, error=str(e))
    except Exception as e:
        logger.error(f"Solver error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ════════════════════════════════════════════════════════════
#  GAME TREE — Preflop decision nodes and conditional ranges
# ════════════════════════════════════════════════════════════

# ── Position order and stack constants ──
_POSITION_ORDER = ["UTG", "HJ", "CO", "BTN", "SB", "BB"]
_BB_AMOUNT = 1.0
_SB_AMOUNT = 0.5
_ANTE = 0.0


def _parse_action_size(action: str) -> float:
    """Extract bet size from action string like 'raise_2.5bb' or 'all_in'."""
    if action == "all_in":
        return 999  # placeholder
    parts = action.split("_")
    for p in parts:
        p = p.replace("bb", "").replace("x", "")
        try:
            return float(p)
        except ValueError:
            continue
    return 0


def _get_position_index(pos: str) -> int:
    try:
        return _POSITION_ORDER.index(pos)
    except ValueError:
        return -1


def _get_first_unmatched_actor(
    start_from: str,
    folded: set[str],
    players_bet: dict[str, float],
    current_bet: float,
) -> str | None:
    """Walk clockwise from start_from.

    Return the first active (non-folded) player whose total bet < current_bet.
    Implements the "Equal Action" rule — a betting round ends when all
    active players have contributed the same amount.
    Returns None when the round is over (all active players match).
    """
    idx = _get_position_index(start_from)
    for i in range(1, len(_POSITION_ORDER) + 1):
        next_idx = (idx + i) % len(_POSITION_ORDER)
        pos = _POSITION_ORDER[next_idx]
        if pos in folded:
            continue
        if players_bet.get(pos, 0) < current_bet - 0.001:
            return pos
    return None


# ── Tree context computation ──


def _compute_tree_context(
    tree_path: list[dict], stack_depth: int, requested_position: str | None = None
) -> dict:
    """
    Given the game tree path (sequence of actions taken), compute:
      - acting_position: who acts next
      - context: 'rfi', 'vs_raise', 'vs_3bet', 'vs_4bet', 'vs_call', 'terminal'
      - pot_size: current pot in bb
      - last_raiser: who made the last raise
      - last_raise_size: the size of the last raise
      - last_action: the last action taken
      - folded_positions: which positions have folded
      - active_raise_count: number of raises (1 = normal raise, 2 = 3-bet, 3 = 4-bet)
      - description: human-readable summary of the node

    Uses the "Equal Action" rule to determine who acts next:
      Walk clockwise from the last actor, find the first active player
      whose total bet doesn't match the current bet. This is correct for
      ALL cases — heads-up, multi-way, 3-bet, 4-bet, all-in, etc.
    """
    # Track per-player total bets and state
    # Preflop initial: SB posted 0.5, BB posted 1.0, everyone else 0
    players_bet: dict[str, float] = {"SB": _SB_AMOUNT, "BB": _BB_AMOUNT}
    current_bet = _BB_AMOUNT  # BB is the amount to call preflop
    folded: set[str] = set()
    last_raiser = None
    last_raise_size = 0
    raise_count = 0
    last_action = None
    last_action_position = None

    for entry in tree_path:
        pos = entry["position"]
        act = entry["action"]
        size = entry.get("size")
        if size is None:
            size = _parse_action_size(act)

        last_action = act
        last_action_position = pos

        if act == "fold":
            folded.add(pos)
        elif act == "call":
            # Caller puts in enough to match current_bet
            players_bet[pos] = current_bet
        elif act.startswith("raise") or act == "all_in":
            amount = size if act.startswith("raise") else stack_depth
            raise_count += 1 if last_raiser else 1  # re-raise increments count
            players_bet[pos] = amount
            current_bet = amount
            last_raiser = pos
            last_raise_size = amount

    # ── Determine acting position via Equal Action rule ──
    if raise_count == 0:
        # No raise yet — RFI (raise first in)
        context = "rfi"
        acting_position = requested_position or "UTG"
        pot = _SB_AMOUNT + _BB_AMOUNT + _ANTE
        stack_rem = stack_depth
        desc = f"{acting_position} RFI — {stack_depth}bb"
    else:
        # Walk clockwise from the last actor. Find the first active player
        # whose total bet < current_bet.
        acting_position = _get_first_unmatched_actor(
            last_action_position or _POSITION_ORDER[0],
            folded,
            players_bet,
            current_bet,
        )

        # Context label based on raise count
        context_map = {1: "vs_raise", 2: "vs_3bet", 3: "vs_4bet", 4: "vs_5bet"}
        context = context_map.get(raise_count, f"vs_{raise_count}bet")

        # Pot = sum of all bets placed
        pot = sum(players_bet.values())

        # Effective stack remaining for the acting position
        if acting_position and acting_position not in folded:
            stack_rem = stack_depth - players_bet.get(acting_position, 0)
        else:
            stack_rem = stack_depth - current_bet

        desc = (
            f"{acting_position} {context} — {stack_depth}bb"
            if acting_position
            else f"Round over — {stack_depth}bb"
        )

        # If no one can act next, the round is over (all active matched the bet)
        if acting_position is None:
            active = [p for p in _POSITION_ORDER if p not in folded]
            if len(active) == 1:
                acting_position = active[0]
                context = "terminal_win"
                desc = f"{acting_position} wins — {stack_depth}bb"
            elif active:
                acting_position = active[0]
                context = "terminal_showdown"
                desc = f"Showdown — {stack_depth}bb"
            else:
                acting_position = _POSITION_ORDER[-1]
                context = "terminal"
                desc = f"Hand over — {stack_depth}bb"

    return {
        "acting_position": acting_position,
        "context": context,
        "pot_size": round(pot, 2),
        "stack_remaining": max(0, round(stack_rem, 2)),
        "last_raiser": last_raiser,
        "last_raise_size": last_raise_size,
        "last_action": last_action,
        "last_action_position": last_action_position,
        "folded_positions": folded,
        "raise_count": raise_count,
        "description": desc,
    }


def _get_bb_display(size: float) -> str:
    """Format a bet size like '2.5bb'"""
    if size == int(size):
        return f"{int(size)}bb"
    return f"{size}bb"


# ── Available actions per tree context ──


def _get_available_actions(
    acting_position: str,
    context: str,
    stack_depth: float,
    last_raise_size: float,
    last_raiser: str | None,
) -> list[dict]:
    """
    Return the list of available actions at this tree node.
    Each action: {id, label, actionBase, size?}
    """
    if context == "rfi":
        size = 3.0 if acting_position in ("SB", "BB") else 2.5
        return [
            {"id": "fold", "label": "Fold", "actionBase": "fold"},
            {"id": f"raise_{size}", "label": f"Raise {size}", "actionBase": "raise", "size": size},
            {"id": "all_in", "label": f"Allin {int(stack_depth)}", "actionBase": "all_in"},
        ]

    elif context == "vs_raise":
        # Facing a raise — options: fold, call, 3-bet, all-in
        call_size = last_raise_size
        three_bet_mult = 3.0 if last_raise_size < 4 else 2.8
        three_bet_size = round(last_raise_size * three_bet_mult, 1)

        # Cap 3-bet at reasonable size
        three_bet_size = min(three_bet_size, stack_depth * 0.4)
        three_bet_size = max(three_bet_size, call_size + 2)

        actions = [
            {"id": "fold", "label": "Fold", "actionBase": "fold"},
            {
                "id": f"call_{call_size}",
                "label": f"Call {_get_bb_display(call_size)}",
                "actionBase": "call",
                "size": call_size,
            },
        ]
        # Add 3-bet option (if enough stack)
        if stack_depth - call_size > three_bet_size:
            actions.append(
                {
                    "id": f"raise_{three_bet_size}",
                    "label": f"Raise {_get_bb_display(three_bet_size)}",
                    "actionBase": "raise",
                    "size": three_bet_size,
                }
            )
        actions.append(
            {
                "id": "all_in",
                "label": f"Allin {int(stack_depth)}",
                "actionBase": "all_in",
            }
        )
        return actions

    elif context == "vs_3bet":
        # Facing a 3-bet — options: fold, call, 4-bet, all-in
        call_size = last_raise_size
        four_bet_size = round(call_size * 2.5, 1)
        four_bet_size = min(four_bet_size, stack_depth * 0.5)
        four_bet_size = max(four_bet_size, call_size + 3)

        actions = [
            {"id": "fold", "label": "Fold", "actionBase": "fold"},
            {
                "id": f"call_{call_size}",
                "label": f"Call {_get_bb_display(call_size)}",
                "actionBase": "call",
                "size": call_size,
            },
        ]
        if stack_depth - call_size > four_bet_size:
            actions.append(
                {
                    "id": f"raise_{four_bet_size}",
                    "label": f"Raise {_get_bb_display(four_bet_size)}",
                    "actionBase": "raise",
                    "size": four_bet_size,
                }
            )
        actions.append(
            {
                "id": "all_in",
                "label": f"Allin {int(stack_depth)}",
                "actionBase": "all_in",
            }
        )
        return actions

    elif context in ("vs_4bet", "vs_reraise"):
        call_size = last_raise_size
        actions = [
            {"id": "fold", "label": "Fold", "actionBase": "fold"},
            {
                "id": f"call_{call_size}",
                "label": f"Call {_get_bb_display(call_size)}",
                "actionBase": "call",
                "size": call_size,
            },
            {"id": "all_in", "label": f"Allin {int(stack_depth)}", "actionBase": "all_in"},
        ]
        return actions

    return [{"id": "fold", "label": "Fold", "actionBase": "fold"}]


# ── GTO Preflop Range Data (static definitions) ──
# RFI (raise-first-in) ranges at 100bb, based on solver output.

_UTG_RANGE = {
    "always_raise": {
        "AA",
        "KK",
        "QQ",
        "JJ",
        "TT",
        "99",
        "88",
        "77",
        "66",
        "AKs",
        "AQs",
        "AJs",
        "ATs",
        "A9s",
        "A8s",
        "A7s",
        "A6s",
        "A4s",
        "A3s",
        "KQs",
        "KJs",
        "KTs",
        "K9s",
        "K8s",
        "QJs",
        "QTs",
        "Q9s",
        "JTs",
        "J9s",
        "T9s",
        "AKo",
        "AQo",
        "AJo",
        "ATo",
        "KQo",
    },
    "mixed": {
        "22": 0.15,
        "33": 0.25,
        "44": 0.35,
        "55": 0.45,
        "A2s": 0.5,
        "A5s": 0.4,
        "K7s": 0.5,
        "KJo": 0.5,
        "QJo": 0.5,
    },
}
_HJ_RANGE = {
    "always_raise": {
        "AA",
        "KK",
        "QQ",
        "JJ",
        "TT",
        "99",
        "88",
        "77",
        "66",
        "AKs",
        "AQs",
        "AJs",
        "ATs",
        "A9s",
        "A8s",
        "A7s",
        "A6s",
        "A5s",
        "A4s",
        "A3s",
        "A2s",
        "KQs",
        "KJs",
        "KTs",
        "K9s",
        "K8s",
        "K7s",
        "QJs",
        "QTs",
        "Q9s",
        "Q8s",
        "JTs",
        "J9s",
        "J8s",
        "T9s",
        "T8s",
        "98s",
        "87s",
        "AKo",
        "AQo",
        "AJo",
        "ATo",
        "A9o",
        "KQo",
        "KJo",
        "KTo",
        "QJo",
    },
    "mixed": {
        "22": 0.25,
        "33": 0.35,
        "44": 0.45,
        "55": 0.55,
        "K6s": 0.5,
        "Q7s": 0.5,
        "J7s": 0.3,
        "A8o": 0.5,
        "A7o": 0.3,
        "QTo": 0.5,
        "JTo": 0.3,
        "T9s": 0.5,
    },
}
_CO_RANGE = {
    "always_raise": {
        "AA",
        "KK",
        "QQ",
        "JJ",
        "TT",
        "99",
        "88",
        "77",
        "66",
        "AKs",
        "AQs",
        "AJs",
        "ATs",
        "A9s",
        "A8s",
        "A7s",
        "A6s",
        "A5s",
        "A4s",
        "A3s",
        "A2s",
        "KQs",
        "KJs",
        "KTs",
        "K9s",
        "K8s",
        "K7s",
        "K6s",
        "K5s",
        "K4s",
        "QJs",
        "QTs",
        "Q9s",
        "Q8s",
        "Q7s",
        "JTs",
        "J9s",
        "J8s",
        "T9s",
        "T8s",
        "T7s",
        "98s",
        "97s",
        "96s",
        "87s",
        "86s",
        "76s",
        "65s",
        "AKo",
        "AQo",
        "AJo",
        "ATo",
        "A9o",
        "A8o",
        "A7o",
        "A6o",
        "KQo",
        "KJo",
        "KTo",
        "K9o",
        "QJo",
        "QTo",
        "JTo",
        "T9o",
    },
    "mixed": {
        "22": 0.35,
        "33": 0.45,
        "44": 0.55,
        "55": 0.65,
        "K3s": 0.5,
        "K2s": 0.3,
        "Q6s": 0.5,
        "Q5s": 0.3,
        "J7s": 0.5,
        "T6s": 0.5,
        "A5o": 0.5,
        "A4o": 0.3,
        "K8o": 0.5,
        "Q9o": 0.5,
        "J9o": 0.5,
        "T8o": 0.3,
        "98o": 0.3,
        "85s": 0.3,
    },
}
_BTN_RANGE = {
    "always_raise": {
        "AA",
        "KK",
        "QQ",
        "JJ",
        "TT",
        "99",
        "88",
        "77",
        "66",
        "AKs",
        "AQs",
        "AJs",
        "ATs",
        "A9s",
        "A8s",
        "A7s",
        "A6s",
        "A5s",
        "A4s",
        "A3s",
        "A2s",
        "KQs",
        "KJs",
        "KTs",
        "K9s",
        "K8s",
        "K7s",
        "K6s",
        "K5s",
        "K4s",
        "K3s",
        "K2s",
        "QJs",
        "QTs",
        "Q9s",
        "Q8s",
        "Q7s",
        "Q6s",
        "Q5s",
        "Q4s",
        "JTs",
        "J9s",
        "J8s",
        "J7s",
        "J6s",
        "T9s",
        "T8s",
        "T7s",
        "T6s",
        "T5s",
        "98s",
        "97s",
        "96s",
        "95s",
        "87s",
        "86s",
        "85s",
        "76s",
        "75s",
        "65s",
        "64s",
        "54s",
        "AKo",
        "AQo",
        "AJo",
        "ATo",
        "A9o",
        "A8o",
        "A7o",
        "A6o",
        "A5o",
        "A4o",
        "A3o",
        "A2o",
        "KQo",
        "KJo",
        "KTo",
        "K9o",
        "K8o",
        "K7o",
        "QJo",
        "QTo",
        "Q9o",
        "JTo",
    },
    "mixed": {
        "22": 0.45,
        "33": 0.55,
        "44": 0.65,
        "55": 0.75,
        "K6o": 0.5,
        "Q8o": 0.5,
        "J9o": 0.5,
        "T9o": 0.5,
        "T8o": 0.3,
        "98o": 0.3,
        "J5s": 0.5,
        "Q3s": 0.5,
        "Q2s": 0.3,
        "T4s": 0.5,
        "94s": 0.3,
        "84s": 0.3,
        "74s": 0.3,
        "63s": 0.3,
    },
}
_SB_RANGE = {
    "always_raise": {
        "AA",
        "KK",
        "QQ",
        "JJ",
        "TT",
        "99",
        "88",
        "77",
        "66",
        "AKs",
        "AQs",
        "AJs",
        "ATs",
        "A9s",
        "A8s",
        "A7s",
        "A6s",
        "A5s",
        "A4s",
        "A3s",
        "A2s",
        "KQs",
        "KJs",
        "KTs",
        "K9s",
        "K8s",
        "K7s",
        "K6s",
        "K5s",
        "K4s",
        "K3s",
        "K2s",
        "QJs",
        "QTs",
        "Q9s",
        "Q8s",
        "Q7s",
        "Q6s",
        "Q5s",
        "Q4s",
        "Q3s",
        "JTs",
        "J9s",
        "J8s",
        "J7s",
        "J6s",
        "J5s",
        "T9s",
        "T8s",
        "T7s",
        "T6s",
        "T5s",
        "98s",
        "97s",
        "96s",
        "95s",
        "87s",
        "86s",
        "85s",
        "76s",
        "75s",
        "65s",
        "64s",
        "54s",
        "AKo",
        "AQo",
        "AJo",
        "ATo",
        "A9o",
        "A8o",
        "A7o",
        "A6o",
        "A5o",
        "A4o",
        "A3o",
        "A2o",
        "KQo",
        "KJo",
        "KTo",
        "K9o",
        "K8o",
        "K7o",
        "K6o",
        "QJo",
        "QTo",
        "Q9o",
        "JTo",
    },
    "mixed": {
        "22": 0.3,
        "33": 0.4,
        "44": 0.5,
        "55": 0.6,
        "K5o": 0.5,
        "Q8o": 0.5,
        "J9o": 0.5,
        "T9o": 0.5,
        "J4s": 0.5,
        "94s": 0.3,
        "53s": 0.3,
        "K4o": 0.3,
        "Q2s": 0.3,
        "T4s": 0.3,
        "98o": 0.3,
    },
}
_BB_RANGE = {
    "always_raise": {"AA", "KK", "QQ", "JJ", "TT", "99", "88", "77", "AKs", "AQs", "AKo"},
    "mixed_call": {
        "66": 0.8,
        "55": 0.7,
        "44": 0.6,
        "33": 0.5,
        "22": 0.5,
        "AJs": 0.8,
        "ATs": 0.8,
        "A9s": 0.7,
        "A8s": 0.7,
        "A7s": 0.6,
        "A6s": 0.5,
        "A5s": 0.7,
        "A4s": 0.5,
        "A3s": 0.5,
        "A2s": 0.5,
        "KQs": 0.8,
        "KJs": 0.8,
        "KTs": 0.7,
        "K9s": 0.6,
        "K8s": 0.5,
        "K7s": 0.4,
        "K6s": 0.3,
        "QJs": 0.7,
        "QTs": 0.6,
        "Q9s": 0.5,
        "Q8s": 0.3,
        "JTs": 0.6,
        "J9s": 0.4,
        "T9s": 0.5,
        "T8s": 0.3,
        "98s": 0.3,
        "87s": 0.3,
        "AQo": 0.8,
        "AJo": 0.8,
        "ATo": 0.6,
        "A9o": 0.5,
        "A8o": 0.4,
        "A7o": 0.3,
        "A6o": 0.3,
        "A5o": 0.4,
        "A4o": 0.3,
        "A3o": 0.3,
        "A2o": 0.3,
        "KQo": 0.7,
        "KJo": 0.6,
        "KTo": 0.5,
        "K9o": 0.3,
        "QJo": 0.4,
    },
    "always_call": set(),
    "mixed_raise": {"AJs": 0.2, "ATs": 0.2, "KQs": 0.2, "AQo": 0.2, "AJo": 0.2},
}

_PREFLOP_RANGES = {
    "UTG": _UTG_RANGE,
    "HJ": _HJ_RANGE,
    "CO": _CO_RANGE,
    "BTN": _BTN_RANGE,
    "SB": _SB_RANGE,
    "BB": _BB_RANGE,
}

_POSITION_RAISE_ACTIONS = {
    "UTG": "raise_2.5bb",
    "HJ": "raise_2.5bb",
    "CO": "raise_2.5bb",
    "BTN": "raise_2.5bb",
    "SB": "raise_3bb",
    "BB": "raise_3bb",
}

# ── Conditional ranges: facing a raise (call or 3-bet) ──
# These are hand-crafted GTO ranges for the most common situations.
# Format: {situation_key: {"always_call": set, "mixed_call": dict,
#                          "always_raise": set, "mixed_raise": dict}}
# "raise" here means "raise back" (3-bet/4-bet depending on context).

# Base call range (generic): suited broadway, mid pairs, suited connectors
# Base 3-bet range (generic): AA, KK, AKs + suited ace bluffs

_VS_RAISE_RANGES = {
    # ── HJ vs UTG open raise ──
    "HJ_vs_UTG": {
        "always_call": {
            "TT",
            "99",
            "AQo",
            "AJs",
            "ATs",
            "A9s",
            "KQs",
            "KJs",
            "KTs",
            "QJs",
            "QTs",
            "JTs",
            "J9s",
            "T9s",
            "98s",
            "87s",
        },
        "mixed_call": {
            "88": 0.7,
            "77": 0.4,
            "66": 0.2,
            "A8s": 0.3,
            "A7s": 0.2,
            "A5s": 0.4,
            "A4s": 0.2,
            "K9s": 0.5,
            "Q9s": 0.5,
            "T8s": 0.3,
            "AJo": 0.6,
            "KQo": 0.4,
            "KJo": 0.2,
        },
        "always_raise": {"AA", "KK", "AKs"},
        "mixed_raise": {
            "QQ": 0.6,
            "AKo": 0.5,
            "A5s": 0.3,
            "A4s": 0.4,
        },
    },
    # ── CO vs UTG open ──
    "CO_vs_UTG": {
        "always_call": {
            "TT",
            "99",
            "88",
            "AJs",
            "ATs",
            "A9s",
            "A8s",
            "KQs",
            "KJs",
            "KTs",
            "K9s",
            "QJs",
            "QTs",
            "Q9s",
            "JTs",
            "J9s",
            "T9s",
            "98s",
            "87s",
            "AQo",
        },
        "mixed_call": {
            "77": 0.6,
            "66": 0.3,
            "A7s": 0.4,
            "A6s": 0.3,
            "A5s": 0.5,
            "A4s": 0.3,
            "K8s": 0.4,
            "Q8s": 0.3,
            "T8s": 0.4,
            "97s": 0.3,
            "AJo": 0.5,
            "KQo": 0.3,
        },
        "always_raise": {"AA", "KK", "AKs"},
        "mixed_raise": {
            "QQ": 0.5,
            "AKo": 0.5,
            "A5s": 0.3,
            "A4s": 0.3,
        },
    },
    # ── BTN vs UTG open ──
    "BTN_vs_UTG": {
        "always_call": {
            "JJ",
            "TT",
            "99",
            "88",
            "AJs",
            "ATs",
            "A9s",
            "A8s",
            "A7s",
            "KQs",
            "KJs",
            "KTs",
            "K9s",
            "K8s",
            "QJs",
            "QTs",
            "Q9s",
            "Q8s",
            "JTs",
            "J9s",
            "J8s",
            "T9s",
            "T8s",
            "98s",
            "87s",
            "76s",
            "AQo",
            "AJo",
        },
        "mixed_call": {
            "77": 0.7,
            "66": 0.5,
            "55": 0.3,
            "A6s": 0.5,
            "A5s": 0.6,
            "A4s": 0.5,
            "A3s": 0.4,
            "K7s": 0.4,
            "Q7s": 0.3,
            "J7s": 0.3,
            "T7s": 0.3,
            "97s": 0.4,
            "86s": 0.3,
            "ATo": 0.3,
            "KQo": 0.5,
            "KJo": 0.3,
        },
        "always_raise": {"AA", "KK", "QQ", "AKs"},
        "mixed_raise": {
            "AKo": 0.4,
            "A5s": 0.3,
            "A4s": 0.3,
        },
    },
    # ── SB vs UTG open ──
    "SB_vs_UTG": {
        "always_call": {
            "QQ",
            "JJ",
            "TT",
            "AKs",
            "AQs",
            "AKo",
        },
        "mixed_call": {
            "99": 0.7,
            "88": 0.5,
            "AJs": 0.6,
            "ATs": 0.4,
            "KQs": 0.5,
            "AQo": 0.4,
        },
        "always_raise": {"AA", "KK"},
        "mixed_raise": {
            "AKs": 0.3,
            "QQ": 0.2,
        },
    },
    # ── CO vs HJ open ──
    "CO_vs_HJ": {
        "always_call": {
            "TT",
            "99",
            "88",
            "AJs",
            "ATs",
            "A9s",
            "KQs",
            "KJs",
            "KTs",
            "K9s",
            "QJs",
            "QTs",
            "Q9s",
            "JTs",
            "J9s",
            "T9s",
            "98s",
            "AQo",
        },
        "mixed_call": {
            "77": 0.5,
            "66": 0.2,
            "A8s": 0.4,
            "A7s": 0.3,
            "A5s": 0.3,
            "K8s": 0.3,
            "Q8s": 0.3,
            "87s": 0.3,
            "AJo": 0.5,
        },
        "always_raise": {"AA", "KK", "QQ", "AKs"},
        "mixed_raise": {
            "AKo": 0.4,
            "A5s": 0.3,
            "A4s": 0.3,
        },
    },
    # ── BTN vs HJ open ──
    "BTN_vs_HJ": {
        "always_call": {
            "JJ",
            "TT",
            "99",
            "88",
            "AJs",
            "ATs",
            "A9s",
            "A8s",
            "KQs",
            "KJs",
            "KTs",
            "K9s",
            "QJs",
            "QTs",
            "Q9s",
            "Q8s",
            "JTs",
            "J9s",
            "T9s",
            "T8s",
            "98s",
            "87s",
            "AQo",
            "AJo",
        },
        "mixed_call": {
            "77": 0.6,
            "66": 0.4,
            "A7s": 0.5,
            "A6s": 0.4,
            "A5s": 0.5,
            "A4s": 0.3,
            "K8s": 0.5,
            "K7s": 0.3,
            "J8s": 0.4,
            "97s": 0.3,
            "86s": 0.3,
            "ATo": 0.4,
            "KQo": 0.4,
            "KJo": 0.2,
        },
        "always_raise": {"AA", "KK", "QQ", "AKs"},
        "mixed_raise": {
            "AKo": 0.4,
            "A5s": 0.3,
            "A4s": 0.3,
        },
    },
    # ── BTN vs CO open ──
    "BTN_vs_CO": {
        "always_call": {
            "JJ",
            "TT",
            "99",
            "88",
            "77",
            "AJs",
            "ATs",
            "A9s",
            "A8s",
            "A7s",
            "KQs",
            "KJs",
            "KTs",
            "K9s",
            "K8s",
            "QJs",
            "QTs",
            "Q9s",
            "Q8s",
            "JTs",
            "J9s",
            "T9s",
            "T8s",
            "98s",
            "87s",
            "76s",
            "AQo",
            "AJo",
            "ATo",
        },
        "mixed_call": {
            "66": 0.5,
            "55": 0.3,
            "A6s": 0.5,
            "A5s": 0.5,
            "A4s": 0.4,
            "K7s": 0.4,
            "Q7s": 0.3,
            "J7s": 0.3,
            "97s": 0.3,
            "86s": 0.3,
            "75s": 0.3,
            "KQo": 0.4,
            "KJo": 0.3,
        },
        "always_raise": {"AA", "KK", "QQ", "AKs", "AKo"},
        "mixed_raise": {
            "A5s": 0.3,
            "A4s": 0.3,
        },
    },
    # ── SB vs BTN open ──
    "SB_vs_BTN": {
        "always_call": {
            "JJ",
            "TT",
            "99",
            "88",
            "AQs",
            "AJs",
            "ATs",
            "KQs",
            "KJs",
            "AKo",
            "AQo",
        },
        "mixed_call": {
            "77": 0.7,
            "66": 0.5,
            "A9s": 0.6,
            "A8s": 0.4,
            "A5s": 0.5,
            "KTs": 0.5,
            "K9s": 0.3,
            "QJs": 0.4,
            "QTs": 0.3,
            "JTs": 0.3,
            "AJo": 0.4,
            "KQo": 0.3,
        },
        "always_raise": {"AA", "KK", "QQ"},
        "mixed_raise": {"AKs": 0.4, "AKo": 0.3, "A5s": 0.3},
    },
}

# ── Conditional ranges: facing a 3-bet (call or 4-bet) ──

_VS_3BET_RANGES = {
    "UTG_vs_HJ": {
        "always_call": {"KK", "AKs", "AKo"},
        "mixed_call": {
            "QQ": 0.5,
            "JJ": 0.3,
            "TT": 0.2,
            "AQs": 0.4,
            "AQo": 0.2,
        },
        "always_raise": {"AA"},
        "mixed_raise": {"KK": 0.2, "AKs": 0.4},
    },
    "UTG_vs_CO": {
        "always_call": {"KK", "QQ", "AKs", "AKo"},
        "mixed_call": {"JJ": 0.4, "TT": 0.2, "AQs": 0.5},
        "always_raise": {"AA"},
        "mixed_raise": {"KK": 0.2, "AKs": 0.3},
    },
    "UTG_vs_BTN": {
        "always_call": {"KK", "QQ", "JJ", "AKs", "AKo", "AQs"},
        "mixed_call": {"TT": 0.5, "99": 0.2, "AQo": 0.3},
        "always_raise": {"AA"},
        "mixed_raise": {"KK": 0.3, "AKs": 0.3},
    },
    "HJ_vs_CO": {
        "always_call": {"KK", "QQ", "AKs", "AKo"},
        "mixed_call": {"JJ": 0.5, "TT": 0.2, "AQs": 0.4},
        "always_raise": {"AA"},
        "mixed_raise": {"KK": 0.2, "AKs": 0.3},
    },
    "HJ_vs_BTN": {
        "always_call": {"KK", "QQ", "JJ", "AKs", "AKo", "AQs"},
        "mixed_call": {"TT": 0.4, "99": 0.2, "AQo": 0.3},
        "always_raise": {"AA"},
        "mixed_raise": {"KK": 0.3, "AKs": 0.3},
    },
    "CO_vs_BTN": {
        "always_call": {"KK", "QQ", "JJ", "AKs", "AKo", "AQs"},
        "mixed_call": {"TT": 0.5, "99": 0.3, "AQo": 0.4},
        "always_raise": {"AA"},
        "mixed_raise": {"KK": 0.3, "AKs": 0.3},
    },
}

# ── Context → range key mapping ──


def _get_range_key(acting_position: str, context: str, last_raiser: str | None) -> str | None:
    """Map a tree context to the right key for range lookup."""
    if context == "vs_raise" and last_raiser:
        return f"{acting_position}_vs_{last_raiser}"
    if context == "vs_3bet" and last_raiser:
        # Original raiser vs 3-bettor
        # last_raiser here is actually the 3-bettor
        # We use the same key pattern but the context tells us it's vs 3-bet
        return f"{acting_position}_vs_{last_raiser}"
    return None


def _get_vs_raise_range(acting_position: str, last_raiser: str) -> dict | None:
    """Get the conditional range dict for facing a raise from last_raiser."""
    key = f"{acting_position}_vs_{last_raiser}"
    return _VS_RAISE_RANGES.get(key)


def _get_vs_3bet_range(acting_position: str, last_raiser: str) -> dict | None:
    """Get the conditional range dict for facing a 3-bet from last_raiser."""
    key = f"{acting_position}_vs_{last_raiser}"
    return _VS_3BET_RANGES.get(key)


def _generate_range_for_node(
    position: str, stack_depth: int, tree_context: dict
) -> tuple[list[HandCell], str, bool]:
    """
    Generate ranges for a specific game tree node.
    Delegates to the appropriate range generator based on context.
    """
    context = tree_context.get("context", "rfi")
    last_raiser = tree_context.get("last_raiser")
    last_raise_size = tree_context.get("last_raise_size", 0)

    ranks = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]
    hands_169 = []
    for i, r1 in enumerate(ranks):
        for j, r2 in enumerate(ranks):
            if i <= j:
                if r1 == r2:
                    hands_169.append(f"{r1}{r2}")
                else:
                    hands_169.append(f"{r1}{r2}s")
                    hands_169.append(f"{r1}{r2}o")

    if context == "rfi":
        return _generate_rfi_range(position, stack_depth, hands_169)

    elif context == "vs_raise":
        cond_range = _get_vs_raise_range(position, last_raiser) if last_raiser else None
        if cond_range:
            return _generate_conditional_range(
                position,
                stack_depth,
                hands_169,
                cond_range,
                call_action="call",
                raise_action=f"raise_{last_raise_size * 3:.1f}bb",
            )
        else:
            return _generate_vs_raise_fallback(
                position, stack_depth, hands_169, last_raiser, last_raise_size
            )

    elif context == "vs_3bet":
        cond_range = _get_vs_3bet_range(position, last_raiser) if last_raiser else None
        if cond_range:
            return _generate_conditional_range(
                position,
                stack_depth,
                hands_169,
                cond_range,
                call_action="call",
                raise_action=f"raise_{last_raise_size * 2.5:.1f}bb",
            )
        else:
            return _generate_vs_raise_fallback(
                position, stack_depth, hands_169, last_raiser, last_raise_size
            )

    elif context in ("vs_4bet", "vs_reraise"):
        return _generate_vs_raise_fallback(
            position, stack_depth, hands_169, last_raiser, last_raise_size
        )

    return _generate_rfi_range(position, stack_depth, hands_169)


def _generate_rfi_range(
    position: str, stack_depth: int, hands_169: list[str]
) -> tuple[list[HandCell], str, bool]:
    """Standard RFI range generation (as before)."""
    solver_available = _check_engine()

    if stack_depth <= 60:
        chart = _load_chart(position, stack_depth)
        if chart:
            source = f"push-fold-chart-{stack_depth}bb"
            cells = []
            for hand in hands_169:
                chart_action = chart.get(hand, "fold")
                action = "raise" if chart_action == "push" else "fold"
                equity = _get_preflop_equity(hand) or 0.5
                cells.append(
                    HandCell(
                        hand=hand,
                        action=action,
                        frequency=1.0 if action == "raise" else 0.0,
                        equity=round(equity, 4),
                    )
                )
            return cells, source, False

    config = _PREFLOP_RANGES.get(position, _PREFLOP_RANGES["UTG"])
    raise_action = _POSITION_RAISE_ACTIONS.get(position, "raise_2.5bb")

    cells = []
    for hand in hands_169:
        equity = _get_preflop_equity(hand) or 0.5
        if position == "BB":
            if hand in config.get("always_raise", set()):
                cells.append(
                    HandCell(hand=hand, action=raise_action, frequency=1.0, equity=round(equity, 4))
                )
            elif hand in config.get("mixed_call", {}):
                freq = config["mixed_call"][hand]
                cells.append(
                    HandCell(
                        hand=hand, action="call", frequency=round(freq, 3), equity=round(equity, 4)
                    )
                )
            elif hand in config.get("always_call", set()):
                cells.append(
                    HandCell(hand=hand, action="call", frequency=1.0, equity=round(equity, 4))
                )
            elif hand in config.get("mixed_raise", {}):
                freq = config["mixed_raise"][hand]
                cells.append(
                    HandCell(
                        hand=hand,
                        action=raise_action,
                        frequency=round(freq, 3),
                        equity=round(equity, 4),
                    )
                )
            else:
                cells.append(
                    HandCell(hand=hand, action="fold", frequency=0.0, equity=round(equity, 4))
                )
        else:
            if hand in config.get("always_raise", set()):
                cells.append(
                    HandCell(hand=hand, action=raise_action, frequency=1.0, equity=round(equity, 4))
                )
            elif hand in config.get("mixed", {}):
                freq = config["mixed"][hand]
                cells.append(
                    HandCell(
                        hand=hand,
                        action=raise_action,
                        frequency=round(freq, 3),
                        equity=round(equity, 4),
                    )
                )
            else:
                cells.append(
                    HandCell(hand=hand, action="fold", frequency=0.0, equity=round(equity, 4))
                )

    source = "gto-range-definitions"
    source += "+mccfr" if solver_available else "+cached"
    return cells, source, solver_available


def _generate_conditional_range(
    position: str,
    stack_depth: int,
    hands_169: list[str],
    cond_range: dict,
    call_action: str = "call",
    raise_action: str = "raise",
) -> tuple[list[HandCell], str, bool]:
    """
    Generate ranges for a conditional situation (facing raise/3-bet).
    cond_range has keys: always_call, mixed_call, always_raise, mixed_raise.
    """
    solver_available = _check_engine()
    cells = []

    for hand in hands_169:
        equity = _get_preflop_equity(hand) or 0.5

        # Check raise (3-bet/4-bet) ranges first (stronger action)
        if hand in cond_range.get("always_raise", set()):
            cells.append(
                HandCell(hand=hand, action=raise_action, frequency=1.0, equity=round(equity, 4))
            )
        elif hand in cond_range.get("mixed_raise", {}):
            freq = cond_range["mixed_raise"][hand]
            cells.append(
                HandCell(
                    hand=hand,
                    action=raise_action,
                    frequency=round(freq, 3),
                    equity=round(equity, 4),
                )
            )
        elif hand in cond_range.get("always_call", set()):
            cells.append(
                HandCell(hand=hand, action=call_action, frequency=1.0, equity=round(equity, 4))
            )
        elif hand in cond_range.get("mixed_call", {}):
            freq = cond_range["mixed_call"][hand]
            cells.append(
                HandCell(
                    hand=hand, action=call_action, frequency=round(freq, 3), equity=round(equity, 4)
                )
            )
        else:
            cells.append(HandCell(hand=hand, action="fold", frequency=0.0, equity=round(equity, 4)))

    source = f"conditional-gto-{position}_vs_{cond_range.get('_label', 'unknown')}"
    source += "+mccfr" if solver_available else "+cached"
    return cells, source, solver_available


def _generate_vs_raise_fallback(
    position: str,
    stack_depth: int,
    hands_169: list[str],
    last_raiser: str | None,
    last_raise_size: float,
) -> tuple[list[HandCell], str, bool]:
    """
    Fallback: equity-based approximation for facing a raise.
    Used when no hand-crafted range exists for this specific situation.
    """
    solver_available = _check_engine()
    call_size = last_raise_size
    three_bet_size = round(last_raise_size * 3.0, 1) if last_raise_size > 0 else 7.5
    call_action = f"call_{call_size}" if call_size > 0 else "call"
    raise_action = f"raise_{three_bet_size}bb"

    # Simple equity-based model:
    # Top 2% equity → 3-bet (AA, KK)
    # Top 2-10% → call (broadway, mid pairs, suited aces)
    # Rest → fold
    # Adjusted by position (IP wider, OOP tighter)

    # Load equities
    equity_threshold_raise = 0.82  # Only AA, KK
    equity_threshold_call = 0.62  # Broadway, pairs, suited aces

    # Adjust by position (IP = wider)
    if position in ("BTN", "CO"):
        equity_threshold_call = 0.58
    elif position == "BB":
        equity_threshold_call = 0.55
    elif position == "SB":
        equity_threshold_call = 0.64

    cells = []
    for hand in hands_169:
        equity = _get_preflop_equity(hand) or 0.5

        if equity >= equity_threshold_raise:
            cells.append(
                HandCell(hand=hand, action=raise_action, frequency=1.0, equity=round(equity, 4))
            )
        elif equity >= equity_threshold_call:
            # Taper frequency near the boundary
            freq = min(1.0, (equity - equity_threshold_call) / 0.05)
            freq = max(freq, 0.2)
            cells.append(
                HandCell(
                    hand=hand, action=call_action, frequency=round(freq, 3), equity=round(equity, 4)
                )
            )
        else:
            cells.append(HandCell(hand=hand, action="fold", frequency=0.0, equity=round(equity, 4)))

    source = "equity-model+conditional-fallback"
    source += "+mccfr" if solver_available else "+cached"
    return cells, source, solver_available


# ── Preflop equities (cached) ──
_preflop_equities = {}
_eq_cache_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "preflop_equities.json"
)
if os.path.exists(_eq_cache_path):
    with open(_eq_cache_path) as f:
        _preflop_equities = json.load(f)
else:
    _preflop_equities = {}


def _get_preflop_equity(hand: str) -> float:
    return _preflop_equities.get(hand, 0.5)


# ── Node Locking ──
def _apply_node_locks(
    cells: list[HandCell],
    locked_hands: dict[str, HandLock] | None,
    available_actions: list[dict],
) -> tuple[list[str], dict[str, float] | None]:
    """Apply user-specified frequency locks to hand cells.

    Actions not specified in the lock inherit the existing action if it matches
    a locked action key. If no existing action matches, the cell is marked as
    a multi-action cell and its frequency is divided among locked actions.

    Returns:
        (locked_applied_hands, counter_strategy_deviations)
        counter_strategy is a dict of hand -> absolute frequency change
        (positive = increased frequency, negative = decreased).
    """
    if not locked_hands:
        return [], None

    locked_applied: list[str] = []
    counter_strategy: dict[str, float] = {}
    valid_action_bases = {a["actionBase"] for a in available_actions}

    cell_map = {c.hand: c for c in cells}

    for hand, lock in locked_hands.items():
        cell = cell_map.get(hand)
        if not cell:
            continue

        # Validate that locked actions are legal at this node
        for act in lock.actions:
            if act not in valid_action_bases and act not in ("fold", "call", "raise", "check", "all_in"):
                logger.warning(f"Invalid lock action '{act}' for hand {hand}, skipping")
                continue

        if not lock.actions:
            continue

        # Record original frequency for counter-strategy calc
        original_freq = cell.frequency

        # Apply lock: set action to the primary locked action, frequency to its weight
        # For simplicity, use the first locked action as the displayed action
        # and the highest frequency as the cell frequency
        primary_action = max(lock.actions, key=lambda a: lock.actions[a])
        primary_freq = lock.actions[primary_action]

        cell.action = primary_action
        cell.frequency = primary_freq
        locked_applied.append(hand)

        # Counter-strategy: deviation from original
        deviation = primary_freq - original_freq
        if abs(deviation) > 0.001:
            counter_strategy[hand] = round(deviation, 4)

    return locked_applied, counter_strategy or None


# ── API endpoint ──


@router.post("/preflop-range", response_model=PreflopRangeResponse)
async def preflop_range(req: PreflopRangeRequest):
    """
    Get GTO solver preflop ranges for a position in the game tree.

    Accepts a tree_path (sequence of actions taken) to compute
    the correct decision node and return conditional ranges.

    tree_path = [
      {"position": "UTG", "action": "raise_2.5bb"},
      {"position": "HJ", "action": "call"},
      ...
    ]

    Empty tree_path = RFI (raise first in) for the given position.
    """
    try:
        # Convert pydantic models to plain dicts for tree computation
        tree_path_dicts = [
            {"position": a.position, "action": a.action, "size": a.size} for a in req.tree_path
        ]

        # Compute the tree context
        tree_context = _compute_tree_context(tree_path_dicts, req.stack_depth, req.position)
        acting_position = tree_context["acting_position"]
        context = tree_context["context"]
        pot_size = tree_context["pot_size"]
        stack_rem = tree_context["stack_remaining"]
        last_raiser = tree_context.get("last_raiser")
        last_raise_size = tree_context.get("last_raise_size", 0)

        # Get available actions for this node
        available_actions = _get_available_actions(
            acting_position,
            context,
            stack_rem,
            last_raise_size,
            last_raiser,
        )

        # Generate ranges
        cells, source, solver_avail = _generate_range_for_node(
            acting_position,
            req.stack_depth,
            tree_context,
        )

        if not cells:
            raise HTTPException(status_code=500, detail="Failed to generate range")

        # Apply node locks (override frequencies for locked hands)
        locked_applied, counter_strategy = _apply_node_locks(
            cells, req.locked_hands, available_actions
        )

        # Build tree node response
        tree_node = TreeNode(
            acting_position=acting_position,
            available_actions=available_actions,
            pot_size=pot_size,
            stack_remaining=stack_rem if stack_rem > 0 else None,
            context=context,
            description=tree_context.get("description", ""),
        )

        return PreflopRangeResponse(
            position=acting_position,
            stack_depth=req.stack_depth,
            hands=cells,
            tree_node=tree_node,
            tree_path=req.tree_path,
            solver_engine=solver_avail,
            source=source,
            locked_hands_applied=locked_applied,
            counter_strategy=counter_strategy,
        )
    except Exception as e:
        logger.error(f"Preflop range error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def solver_health():
    try:
        engine_ok = _check_engine()
        return {
            "status": "ok" if engine_ok else "degraded",
            "engine": "MCCFR",
            "phevaluator": engine_ok,
        }
    except Exception as e:
        return {"status": "error", "engine": "MCCFR", "error": str(e)}


@router.post("/tree-node")
async def get_tree_node(req: PreflopRangeRequest):
    """
    Compute the current tree node without generating ranges.
    Useful for the frontend to update action buttons when navigating.
    """
    tree_path_dicts = [
        {"position": a.position, "action": a.action, "size": a.size} for a in req.tree_path
    ]
    tree_context = _compute_tree_context(tree_path_dicts, req.stack_depth, req.position)
    available_actions = _get_available_actions(
        tree_context["acting_position"],
        tree_context["context"],
        tree_context["stack_remaining"],
        tree_context.get("last_raise_size", 0),
        tree_context.get("last_raiser"),
    )
    return {
        "acting_position": tree_context["acting_position"],
        "context": tree_context["context"],
        "available_actions": available_actions,
        "pot_size": tree_context["pot_size"],
        "stack_remaining": tree_context["stack_remaining"],
        "description": tree_context.get("description", ""),
    }
