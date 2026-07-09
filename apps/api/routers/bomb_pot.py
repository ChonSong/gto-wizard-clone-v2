"""Bomb Pot game model endpoints"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Set
from enum import Enum
import sys

sys.path.insert(0, "/tmp/PokerHandEvaluator/python")
sys.path.insert(0, "packages/poker-core/src")

from gto_poker.bomb_pot import (
    BombPotGameState,
    BombPotGameModel,
    BombPotAction,
    BombPotEquity,
    Phase,
    ActionType,
)


router = APIRouter(prefix="/bomb-pot", tags=["bomb-pot", "game"])


class PhaseEnum(str, Enum):
    STRADDLE_ROUND = "straddle_round"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    SHOWDOWN = "showdown"


class BombPotActionRequest(BaseModel):
    """Request to submit an action."""
    player: int
    action_type: str  # "straddle", "call", "raise", "check"
    amount: int = 0


class GameStateResponse(BaseModel):
    """Response with game state information."""
    positions: List[str]
    straddle_map: Dict[int, int]
    junk_blinds: List[int]
    betting_order: List[int]
    betting_acted: List[int]
    current_bettor: int
    phase: str
    pot: int
    board: List[str]
    player_count: int


@router.post("/game-state", response_model=GameStateResponse)
async def create_game_state(
    positions: List[str],
    straddle_map: Dict[int, int],
    junk_blinds: List[int] = []
):
    """
    Create a new bomb pot game state.

    Args:
        positions: List of position names (e.g., ["UTG", "UTG+1", "CO", "BTN", "SB", "BB"])
        straddle_map: Dict mapping position index -> straddle amount
        junk_blinds: List of additional antes/blinds
    """
    if len(positions) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 players")

    state = BombPotGameState(
        positions=positions,
        straddle_map=straddle_map,
        junk_blinds=junk_blinds,
        betting_order=list(range(len(positions))),
        phase=Phase.STRADDLE_ROUND,
        pot=0
    )

    model = BombPotGameModel()
    pot = model.calculate_pot(state)
    state.pot = pot

    return GameStateResponse(
        positions=state.positions,
        straddle_map=state.straddle_map,
        junk_blinds=state.junk_blinds,
        betting_order=state.betting_order,
        betting_acted=list(state.betting_acted),
        current_bettor=state.current_bettor,
        phase=state.phase.value,
        pot=state.pot,
        board=state.board,
        player_count=state.player_count
    )


@router.post("/action", response_model=GameStateResponse)
async def submit_action(
    state: GameStateResponse,
    action: BombPotActionRequest
):
    """
    Submit an action in the bomb pot game.

    Note: In straddle round, FOLD is not allowed.
    """
    # Convert back to domain model
    bomb_state = BombPotGameState(
        positions=state.positions,
        straddle_map=state.straddle_map,
        junk_blinds=state.junk_blinds,
        betting_order=state.betting_order,
        betting_acted=set(state.betting_acted),
        current_bettor=state.current_bettor,
        phase=Phase(state.phase),
        pot=state.pot,
        board=state.board
    )

    model = BombPotGameModel()

    # Validate action type
    try:
        action_type = ActionType(action.action_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid action type: {action.action_type}")

    # Check if fold is attempted in straddle round
    if action_type == ActionType.CHECK and action.action_type == "fold":
        raise HTTPException(status_code=400, detail="FOLD not allowed in straddle round")

    # Create action
    bomb_action = BombPotAction(
        action_type=action_type,
        player=action.player,
        amount=action.amount
    )

    # Apply action
    new_state = model.apply_action(bomb_state, bomb_action)

    # Check if betting is complete and transition
    if model.is_betting_complete(new_state) and new_state.phase == Phase.STRADDLE_ROUND:
        new_state, pot = model.resolve_preflop(new_state)

    return GameStateResponse(
        positions=new_state.positions,
        straddle_map=new_state.straddle_map,
        junk_blinds=new_state.junk_blinds,
        betting_order=new_state.betting_order,
        betting_acted=list(new_state.betting_acted),
        current_bettor=new_state.current_bettor,
        phase=new_state.phase.value,
        pot=new_state.pot,
        board=new_state.board,
        player_count=new_state.player_count
    )


@router.post("/resolve-preflop", response_model=GameStateResponse)
async def resolve_preflop(
    state: GameStateResponse
):
    """
    Resolve the straddle round and transition to flop.

    Deals the board and sets phase to FLOP.
    """
    bomb_state = BombPotGameState(
        positions=state.positions,
        straddle_map=state.straddle_map,
        junk_blinds=state.junk_blinds,
        betting_order=state.betting_order,
        betting_acted=set(state.betting_acted),
        current_bettor=state.current_bettor,
        phase=Phase(state.phase),
        pot=state.pot,
        board=state.board
    )

    model = BombPotGameModel()

    if bomb_state.phase != Phase.STRADDLE_ROUND:
        raise HTTPException(status_code=400, detail="Can only resolve preflop in STRADDLE_ROUND phase")

    # Resolve preflop
    new_state, pot = model.resolve_preflop(bomb_state)

    # Deal board (use empty deck simulation)
    new_state.board = []  # Will be dealt by client or via separate endpoint

    return GameStateResponse(
        positions=new_state.positions,
        straddle_map=new_state.straddle_map,
        junk_blinds=new_state.junk_blinds,
        betting_order=new_state.betting_order,
        betting_acted=list(new_state.betting_acted),
        current_bettor=new_state.current_bettor,
        phase=new_state.phase.value,
        pot=new_state.pot,
        board=new_state.board,
        player_count=new_state.player_count
    )


@router.post("/equity", response_model=dict)
async def calculate_bomb_pot_equity(
    hand1: List[str],
    hand2: List[str],
    straddle_map: Dict[int, int],
    junk_blinds: List[int] = [],
    samples: int = 10000
):
    """
    Calculate bomb pot equity for two hands.

    Accounts for straddle dead money in the pot.
    """
    if len(hand1) != 4:
        raise HTTPException(status_code=400, detail="hand1 must have 4 cards")
    if len(hand2) != 4:
        raise HTTPException(status_code=400, detail="hand2 must have 4 cards")

    state = BombPotGameState(
        positions=["Hero", "Villain"],
        straddle_map=straddle_map,
        junk_blinds=junk_blinds,
        phase=Phase.STRADDLE_ROUND,
        pot=0
    )

    model = BombPotGameModel()
    pot = model.calculate_pot(state)
    state.pot = pot

    equity_calc = BombPotEquity()
    eq1, eq2 = equity_calc.calculate(state, hand1, hand2, samples)

    return {
        "hand1": hand1,
        "hand2": hand2,
        "straddle_map": straddle_map,
        "junk_blinds": junk_blinds,
        "pot": pot,
        "equity1": round(eq1, 2),
        "equity2": round(eq2, 2),
        "samples": samples
    }


@router.get("/legal-actions/{phase}", response_model=List[str])
async def get_legal_actions(phase: str, player: int, straddle_map: str = "{}"):
    """
    Get legal actions for a player in a given phase.

    In STRADDLE_ROUND, FOLD is never legal.
    """
    try:
        phase_enum = Phase(phase)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid phase: {phase}")

    import json
    straddle = json.loads(straddle_map) if straddle_map else {}

    state = BombPotGameState(
        positions=["p0", "p1", "p2", "p3", "p4", "p5"][:6],
        straddle_map={int(k): v for k, v in straddle.items()},
        phase=phase_enum
    )

    model = BombPotGameModel()
    actions = model.legal_actions(state, player)

    return [a.value for a in actions]