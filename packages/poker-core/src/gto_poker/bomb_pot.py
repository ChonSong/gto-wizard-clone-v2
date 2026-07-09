"""Bomb Pot — novel poker variant with action-first betting.

In a bomb pot, pre-flop action happens BEFORE the board is dealt.
Key twist: No fold option for players who posted straddle.
Straddle round is a mandatory action round.

Game model: straddle_map + junk_blinds + betting order

This is a novel variant — no existing open-source reference.
"""
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import random
import sys

sys.path.insert(0, "/tmp/PokerHandEvaluator/python")
from phevaluator.evaluator import evaluate_cards

from .deck import RANKS, SUITS


class Phase(Enum):
    """Game phases for bomb pot."""
    STRADDLE_ROUND = "straddle_round"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    SHOWDOWN = "showdown"


class ActionType(Enum):
    """Legal actions in bomb pot."""
    STRADDLE = "straddle"
    CALL = "call"
    RAISE = "raise"
    CHECK = "check"
    FOLD = "fold"  # Only available post-flop (not in straddle round)


@dataclass
class Position:
    """Represents a player's position."""
    index: int
    name: str  # e.g., "UTG", "CO", "BTN"


@dataclass
class BombPotAction:
    """An action taken by a player."""
    action_type: ActionType
    player: int  # position index
    amount: int = 0  # for straddle/raise/call


@dataclass
class BombPotGameState:
    """Current state of a bomb pot game."""
    # Core config
    positions: List[str] = field(default_factory=list)  # position names

    # Straddle configuration
    straddle_map: Dict[int, int] = field(default_factory=dict)  # pos -> amount
    junk_blinds: List[int] = field(default_factory=list)  # extra antes

    # Betting state
    betting_order: List[int] = field(default_factory=list)  # who acts next
    betting_acted: Set[int] = field(default_factory=set)  # who has acted
    current_bettor: int = 0
    phase: Phase = Phase.STRADDLE_ROUND

    # Pot state
    pot: int = 0

    # Board (dealt after straddle round)
    board: List[str] = field(default_factory=list)

    # Convenience
    @property
    def player_count(self) -> int:
        return len(self.positions)

    def get_action_space(self) -> List[ActionType]:
        """
        Returns the list of legal actions for the current street/phase.
        
        - STRADDLE_ROUND: straddle, call, raise, check (no fold)
        - FLOP/TURN/RIVER: call, raise, check, fold (standard post-flop)
        - SHOWDOWN: no actions
        
        Returns:
            List of ActionType values valid for the current phase
        """
        if self.phase == Phase.STRADDLE_ROUND:
            return [ActionType.STRADDLE, ActionType.CALL, ActionType.RAISE, ActionType.CHECK]
        elif self.phase in (Phase.FLOP, Phase.TURN, Phase.RIVER):
            return [ActionType.CALL, ActionType.RAISE, ActionType.CHECK, ActionType.FOLD]
        else:
            return []


class BombPotGameModel:
    """Game model for bomb pot logic.

    Key differences from standard poker:
    - Round 0 = straddle round (no fold option)
    - Players who straddle are automatically in the hand
    - Straddle is a raise option, not mandatory (unless "mandatory straddle" rule)
    """

    def create_straddle_map(
        self,
        positions: List[int],
        amounts: Dict[int, int]
    ) -> Dict[int, int]:
        """
        Build straddle map from position indices and amounts.

        Args:
            positions: List of position indices (0-based)
            amounts: Dict mapping position index -> straddle amount

        Returns:
            Dict mapping position index -> straddle amount
        """
        straddle_map = {}
        for pos in positions:
            if pos in amounts:
                straddle_map[pos] = amounts[pos]
        return straddle_map

    def calculate_pot(self, state: BombPotGameState) -> int:
        """Calculate total pot including antes and straddles."""
        # Base antes (junk_blinds are per-player)
        total = sum(state.junk_blinds) * state.player_count

        # Add all straddle amounts
        for pos, amount in state.straddle_map.items():
            total += amount

        return total

    def next_bettor(self, state: BombPotGameState) -> Optional[int]:
        """Get next player to act in betting order."""
        if not state.betting_order:
            return None

        for pos in state.betting_order:
            if pos not in state.betting_acted:
                return pos

        return None  # All have acted

    def is_betting_complete(self, state: BombPotGameState) -> bool:
        """Check if current betting round is complete."""
        return self.next_bettor(state) is None

    def legal_actions(
        self,
        state: BombPotGameState,
        player: int
    ) -> List[ActionType]:
        """
        Get legal actions for a player in current state.

        In straddle round, NO FOLD option exists.
        Post-flop, all standard actions including fold are available.
        """
        if state.phase == Phase.STRADDLE_ROUND:
            # In straddle round, only straddle/call/raise/check allowed
            actions = [ActionType.CALL, ActionType.RAISE, ActionType.CHECK]

            # Player can only straddle if not already in straddle_map
            if player not in state.straddle_map:
                actions.append(ActionType.STRADDLE)

            return actions

        # Post-flop: standard actions including fold
        return [ActionType.CALL, ActionType.RAISE, ActionType.CHECK, ActionType.FOLD]

    def resolve_preflop(
        self,
        state: BombPotGameState
    ) -> Tuple[BombPotGameState, int]:
        """
        Resolve straddle round and transition to flop.

        Returns:
            Tuple of (new_state, final_pot)
        """
        if state.phase != Phase.STRADDLE_ROUND:
            raise ValueError("Can only resolve preflop in STRADDLE_ROUND phase")

        # Calculate final pot
        pot = self.calculate_pot(state)

        # Transition to flop phase
        new_state = BombPotGameState(
            positions=state.positions,
            straddle_map=state.straddle_map,
            junk_blinds=state.junk_blinds,
            betting_order=[],  # Reset for flop
            betting_acted=set(),
            current_bettor=0,
            phase=Phase.FLOP,
            pot=pot,
            board=[]
        )

        return new_state, pot

    def apply_action(
        self,
        state: BombPotGameState,
        action: BombPotAction
    ) -> BombPotGameState:
        """Apply an action and return updated state."""
        new_state = BombPotGameState(
            positions=state.positions,
            straddle_map=state.straddle_map.copy(),
            junk_blinds=state.junk_blinds.copy(),
            betting_order=state.betting_order.copy(),
            betting_acted=state.betting_acted.copy(),
            current_bettor=state.current_bettor,
            phase=state.phase,
            pot=state.pot,
            board=state.board.copy()
        )

        if action.action_type == ActionType.STRADDLE:
            new_state.straddle_map[action.player] = action.amount
            new_state.pot += action.amount

        elif action.action_type == ActionType.RAISE:
            new_state.pot += action.amount

        elif action.action_type == ActionType.CALL:
            # Call amount = current bet to match
            new_state.pot += action.amount

        # Mark player as having acted
        new_state.betting_acted.add(action.player)

        # Update current bettor
        next_p = self.next_bettor(new_state)
        if next_p is not None:
            new_state.current_bettor = next_p

        return new_state

    def deal_board(
        self,
        state: BombPotGameState,
        deck_cards: List[str]
    ) -> BombPotGameState:
        """Deal board cards after straddle round completes."""
        new_state = BombPotGameState(
            positions=state.positions,
            straddle_map=state.straddle_map,
            junk_blinds=state.junk_blinds,
            betting_order=[],  # Will be set for flop
            betting_acted=set(),
            current_bettor=0,
            phase=Phase.FLOP,
            pot=state.pot,
            board=deck_cards[:5]  # First 5 cards = flop
        )
        return new_state


class BombPotEquity:
    """Calculate equity in a bomb pot scenario."""

    def __init__(self, seed: Optional[int] = None):
        self._random = random.Random(seed)

    def calculate(
        self,
        state: BombPotGameState,
        hand1: List[str],
        hand2: List[str],
        samples: int = 10000
    ) -> Tuple[float, float]:
        """
        Calculate equity for two players in bomb pot.

        Args:
            state: BombPotGameState with straddle_map and pot info
            hand1: Hero's 4 hole cards
            hand2: Villain's 4 hole cards
            samples: Monte Carlo samples

        Returns:
            Tuple of (equity1, equity2)
        """
        # Build deck excluding known cards
        used = set(hand1 + hand2 + list(state.straddle_map.keys()))
        deck = [r + s for r in RANKS for s in SUITS if r + s not in used]

        wins1 = 0
        wins2 = 0
        chops = 0

        for _ in range(samples):
            self._random.shuffle(deck)
            board = deck[:5]

            # Evaluate PLO4 hands on this board
            rank1 = self._evaluate_plo4(hand1, board)
            rank2 = self._evaluate_plo4(hand2, board)

            if rank1 < rank2:
                wins1 += 1
            elif rank2 < rank1:
                wins2 += 1
            else:
                chops += 1

        total = wins1 + wins2 + chops
        if total == 0:
            return 50.0, 50.0

        eq1 = (wins1 + chops * 0.5) / total * 100
        eq2 = (wins2 + chops * 0.5) / total * 100

        return eq1, eq2

    def _evaluate_plo4(self, hole: List[str], board: List[str]) -> int:
        """Evaluate best 2-of-4 + 3-of-5 PLO4 hand."""
        from itertools import combinations

        best_rank = 999999

        for hole_combo in combinations(hole, 2):
            for board_combo in combinations(board, 3):
                rank = evaluate_cards(*hole_combo, *board_combo)
                if rank < best_rank:
                    best_rank = rank

        return best_rank


__all__ = [
    "Phase",
    "ActionType",
    "Position",
    "BombPotAction",
    "BombPotGameState",
    "BombPotGameModel",
    "BombPotEquity",
    "BombPotState",
]


# Alias for backwards compatibility
BombPotState = BombPotGameState