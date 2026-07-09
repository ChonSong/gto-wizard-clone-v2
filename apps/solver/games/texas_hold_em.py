"""
Texas Hold'em game rules and state management for CFR.

Implements:
- Betting rounds (preflop, flop, turn, river)
- Valid actions: fold, call, raise
- Showdown evaluation using HandEvaluator
- River solver focus for 2-player games
"""

from enum import Enum
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass, field
import numpy as np
import sys
import os
# path removed — gto-poker is pip-installed
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from gto_poker.deck import Deck, Card
from gto_poker.hand import Hand, HandEvaluator


class Player(Enum):
    """Player indices."""
    P0 = 0
    P1 = 1
    # Add P2-P5 for multi-way pots


class ActionType(Enum):
    """Action types in poker."""
    FOLD = "fold"
    CALL = "call"
    RAISE = "raise"
    CHECK = "check"
    BET = "bet"
    ALL_IN = "all_in"


@dataclass
class Action:
    """Represents a poker action."""
    action_type: ActionType
    player: int  # 0 or 1
    amount: float = 0.0  # Bet/raise size in chips
    
    def __str__(self):
        if self.action_type == ActionType.FOLD:
            return "fold"
        elif self.action_type == ActionType.CALL:
            return "call"
        elif self.action_type == ActionType.CHECK:
            return "check"
        elif self.action_type == ActionType.RAISE:
            return f"raise:{self.amount}"
        elif self.action_type == ActionType.BET:
            return f"bet:{self.amount}"
        elif self.action_type == ActionType.ALL_IN:
            return f"all_in:{self.amount}"
        return str(self.action_type)


@dataclass
class GameState:
    """
    Complete game state for Texas Hold'em.

    For river solver, we fix:
    - All players' hole cards (2 cards each)
    - Board cards (5 cards on river)
    - Pot size
    - Stack sizes

    Supports 2-6 players for multi-way pots.
    """
    # Player hole cards [p0_card1, p0_card2, p1_card1, p1_card2, ..., pn_card1, pn_card2]
    hole_cards: List[Card] = field(default_factory=list)

    # Board cards (0-5 cards depending on street)
    board: List[Card] = field(default_factory=list)

    # Number of players (2-6)
    n_players: int = 2

    # Pot sizes (main pot, then side pots if any)
    pot: float = 0.0

    # Amount each player has contributed to pot
    contributions: List[float] = field(default_factory=lambda: [0.0, 0.0])

    # Stack sizes (amount each player has left)
    stacks: List[float] = field(default_factory=lambda: [100.0, 100.0])

    # Current player to act (-1 if not applicable)
    current_player: int = 0

    # Action history
    action_history: List[Action] = field(default_factory=list)

    # Street: 0=preflop, 1=flop, 2=turn, 3=river, 4=showdown
    street: int = 3  # Default to river

    # Bet to call (amount needed to stay in)
    bet_to_call: float = 0.0

    # Last player who bet (to track when betting round ends)
    last_bettor: int = -1

    # Amount of the last bet (for showdown detection)
    last_bet_amount: float = 0.0

    # Number of actions taken on the current street (for multi-way betting round detection)
    street_actions: int = 0

    # Whether the hand is over
    terminal: bool = False
    terminal_reason: str = ""

    # Terminal payoffs (set when terminal)
    payoffs: List[float] = field(default_factory=lambda: [0.0, 0.0])
    
    def infoset_key(self, player: int) -> str:
        """
        Generate information set key for a player.

        Format: "player:hole_cards:board:pot:stacks:bet_to_call:action_history"

        For multi-way pots, includes all active players' hole cards relevant to
        the information set.
        """
        board_str = "".join(str(c) for c in self.board)
        # Get this player's hole cards (each player has 2 cards)
        start_idx = player * 2
        hole_str = "".join(str(self.hole_cards[start_idx + i]) for i in range(2) if start_idx + i < len(self.hole_cards))

        # Active players are those with non-zero stacks or that have contributed
        active_players = [i for i in range(self.n_players) if self.stacks[i] > 0 or self.contributions[i] > 0]
        stack_str = ",".join(f"{self.stacks[i]:.0f}" for i in range(self.n_players))

        # Get recent actions (up to last 4)
        actions_str = ",".join(str(a) for a in self.action_history[-4:])

        return f"p{player}:{hole_str}:{board_str}:{self.pot:.0f}:{stack_str}:{self.bet_to_call:.0f}:{actions_str}"
    
    def copy(self) -> "GameState":
        """Create a deep copy of the game state."""
        return GameState(
            hole_cards=list(self.hole_cards),
            board=list(self.board),
            n_players=self.n_players,
            pot=self.pot,
            contributions=list(self.contributions),
            stacks=list(self.stacks),
            current_player=self.current_player,
            action_history=list(self.action_history),
            street=self.street,
            bet_to_call=self.bet_to_call,
            last_bettor=self.last_bettor,
            last_bet_amount=self.last_bet_amount,
            street_actions=self.street_actions,
            terminal=self.terminal,
            terminal_reason=self.terminal_reason
        )


class TexasHoldEm:
    """
    Texas Hold'em game for CFR.

    This class manages:
    - Game rules and valid actions
    - State transitions
    - Hand evaluation at showdown
    - Multi-way pots (2-6 players)
    """

    def __init__(
        self,
        stack_sizes: List[float] = None,  # In big blinds [p0, p1, ...]
        bet_sizes: List[float] = None,    # Multipliers of pot
        big_blind: float = 1.0,
        n_players: int = 2
    ):
        """
        Initialize Texas Hold'em game.

        Args:
            stack_sizes: Stack sizes in big blinds [p0, p1, ...]
            bet_sizes: Available bet sizes as pot multipliers, e.g., [0.5, 1.0]
            big_blind: Size of big blind
            n_players: Number of players (2-6)
        """
        self.n_players = n_players
        self.stack_sizes = stack_sizes or [100.0] * n_players
        self.bet_sizes = bet_sizes or [0.5, 1.0]  # Half-pot, pot-sized
        self.big_blind = big_blind

        # Hand evaluator
        self.evaluator = HandEvaluator()

    def get_valid_actions(self, state: GameState, player: int) -> List[str]:
        """
        Get valid actions for a player at the current state.

        River solver simplified: single bet per betting round.
        - Always: fold (give up), check (if no bet), or bet (initiate new bet)
        - If facing a bet: fold, call, or all-in

        This prevents the tree explosion from multiple re-raises.
        """
        if state.terminal:
            return []

        if player < 0 or player >= state.n_players:
            return []

        amount_to_call = state.bet_to_call - state.contributions[player]
        if amount_to_call < 0:
            amount_to_call = 0  # Clamp negative values

        actions = ["fold"]  # Can always fold

        # If facing a bet, can call or all-in
        if amount_to_call > 0:
            actions.append("call")
            # All-in is always available if player has any chips
            if state.stacks[player] > 0:
                actions.append(f"all_in:{state.stacks[player]}")
        else:
            # No active bet - first action of the betting round
            # Can check or bet (one size only)
            actions.append("check")
            actions.append(f"bet:{self.bet_sizes[0]}" if self.bet_sizes else "bet:0.5")

            # All-in as emergency option
            if state.stacks[player] > 0:
                actions.append(f"all_in:{state.stacks[player]}")

        return actions
    
    def apply_action(self, state: GameState, player: int, action_str: str) -> GameState:
        """
        Apply an action and return new state.

        Args:
            state: Current game state
            player: Player taking action (0 to n_players-1)
            action_str: Action string like "fold", "call", "raise:0.5"

        Returns:
            New game state
        """
        new_state = state.copy()

        # Create and store the action
        from games.texas_hold_em import Action, ActionType
        if action_str == "fold":
            action = Action(ActionType.FOLD, player)
        elif action_str == "call":
            action = Action(ActionType.CALL, player)
        elif action_str.startswith("raise:"):
            amount = float(action_str.split(":")[1])
            action = Action(ActionType.RAISE, player, amount)
        elif action_str.startswith("bet:"):
            # Bet is like raise but without needing to match an existing bet
            amount = float(action_str.split(":")[1])
            action = Action(ActionType.BET, player, amount)
        elif action_str.startswith("all_in:"):
            # All-in action - amount is the player's entire stack
            amount = float(action_str.split(":")[1])
            action = Action(ActionType.ALL_IN, player, amount)
        elif action_str == "check":
            action = Action(ActionType.CHECK, player)
        else:
            action = Action(ActionType(action_str), player)

        new_state.action_history.append(action)

        # Increment street action counter for multi-way betting round detection
        new_state.street_actions += 1

        # Find next active player (not folded, has chips)
        next_player = self._get_next_active_player(state, player)
        new_state.current_player = next_player

        if action_str == "fold":
            new_state.terminal = True
            new_state.terminal_reason = "fold"
            # In multi-way pot, if only one player remains, they win
            remaining = self._get_active_players(new_state)
            if len(remaining) == 1:
                winner = remaining[0]
                new_state.payoffs = [0.0] * new_state.n_players
                new_state.payoffs[winner] = state.pot
            else:
                # Multiple players remain, set payoffs to 0 for now (will be resolved at showdown)
                new_state.payoffs = [0.0] * new_state.n_players
            return new_state

        amount_to_call = state.bet_to_call - state.contributions[player]

        if action_str == "call":
            # Match the bet
            call_amount = min(max(0, amount_to_call), state.stacks[player])
            new_state.contributions[player] += call_amount
            new_state.stacks[player] -= call_amount
            new_state.pot += call_amount

            # If player called a bet (not just checking when no bet), update bet to call
            # for remaining players in multi-way pots
            if amount_to_call > 0:
                # Keep bet_to_call at the highest contribution level so that
                # other players who haven't acted yet still need to call
                # (For 2-player this effectively ends the round; for multi-way
                #  it ensures remaining players can still call/raise)
                new_state.bet_to_call = max(new_state.contributions)
                new_state.last_bettor = -1  # Betting round complete for this player
            # If no active bet (amount_to_call == 0), this is effectively checking
            # last_bettor stays at -1 if it was -1, or stays at last value (meaning round isn't complete)

        elif action_str.startswith("raise:"):
            raise_mult = float(action_str.split(":")[1])
            # If raise_mult < 10, treat as pot multiplier; otherwise as absolute amount
            bet_size = state.pot * raise_mult if raise_mult < 10 else raise_mult

            # Amount needed to call (to match the current bet)
            amount_to_call = max(0, state.bet_to_call - state.contributions[player])

            # Total cost = amount_to_call + bet_size, capped at player's stack
            total_cost = min(amount_to_call + bet_size, state.stacks[player])

            new_state.contributions[player] += total_cost
            new_state.stacks[player] -= total_cost
            new_state.pot += total_cost

            # After this action, what do other players need to call?
            # bet_to_call should be the highest contribution level for others to match
            new_state.bet_to_call = max(new_state.contributions)
            new_state.last_bettor = player

        elif action_str.startswith("all_in:"):
            # All-in is like bet/raise but for the player's entire stack
            player_stack = state.stacks[player]
            amount_to_call = max(0, state.bet_to_call - state.contributions[player])

            total_cost = player_stack

            new_state.contributions[player] += total_cost
            new_state.stacks[player] -= total_cost
            new_state.pot += total_cost

            # After all-in, others need to call the difference
            # bet_to_call should be the highest contribution level for others to match
            new_state.bet_to_call = max(new_state.contributions)
            new_state.last_bettor = player

            # Check if all active players are all-in (trigger showdown)
            active = self._get_active_players(new_state)
            all_all_in = all(new_state.stacks[p] == 0 for p in active)
            if all_all_in and len(active) >= 2:
                new_state.terminal = True
                new_state.terminal_reason = "showdown"
                new_state.last_bettor = -1
                return new_state

        elif action_str.startswith("bet:"):
            bet_mult = float(action_str.split(":")[1])
            bet_size = state.pot * bet_mult if bet_mult < 10 else bet_mult

            # Bet the bet_size, capped at player's stack
            total_cost = min(bet_size, state.stacks[player])

            new_state.contributions[player] += total_cost
            new_state.stacks[player] -= total_cost
            new_state.pot += total_cost

            # After a bet, others need to call to stay in
            # bet_to_call should be the highest contribution level for others to match
            new_state.bet_to_call = max(new_state.contributions)
            new_state.last_bettor = player

        elif action_str == "check":
            # Check doesn't change pot or stacks, but if there's no bet to call
            # and this is the first action, the betting round is now complete (both checked)
            if state.bet_to_call == 0 and state.last_bettor == -1:
                # Both players have checked - round is done, showdown on river
                pass  # new_state.last_bettor stays -1
            elif state.bet_to_call > 0:
                # This shouldn't happen (can't check when facing a bet)
                # But if it does, treat as call
                pass

        # Showdown detection for river street only
        # On the river (street 3), showdown happens when betting round ends
        if not new_state.terminal and new_state.street >= 3:
            if self._betting_round_complete(new_state):
                new_state.terminal = True
                new_state.terminal_reason = "showdown"
                new_state.last_bettor = -1

        return new_state

    def _get_next_active_player(self, state: GameState, current_player: int) -> int:
        """Get the next active player after current_player."""
        n = state.n_players
        for offset in range(1, n + 1):
            next_p = (current_player + offset) % n
            if state.stacks[next_p] > 0:
                # Check if this player has folded
                folded = False
                for action in state.action_history:
                    if action.player == next_p and action.action_type == ActionType.FOLD:
                        folded = True
                        break
                if not folded:
                    return next_p
        return -1  # No active players

    def _get_active_players(self, state: GameState) -> List[int]:
        """Get list of active players (not folded, have chips)."""
        active = []
        for i in range(state.n_players):
            if state.stacks[i] > 0:
                # Check if player has folded
                folded = False
                for action in state.action_history:
                    if action.player == i and action.action_type == ActionType.FOLD:
                        folded = True
                        break
                if not folded:
                    active.append(i)
        return active

    def _betting_round_complete(self, state: GameState) -> bool:
        """
        Check if betting round is complete.

        A betting round is complete when:
        - All active (non-folded) players have acted in the current betting round
        - All active players have contributed equal amounts (no outstanding bet to call)
        - In multi-way pots, this correctly handles sequential action across 3+ players
        """
        if len(state.action_history) == 0:
            return False

        # Must have at least 2 actions for a complete betting round
        if len(state.action_history) < 2:
            return False

        # Get active (non-folded) players
        active = self._get_active_players(state)
        if len(active) <= 1:
            return True

        # Find the last bet/raise/all_in action that set the current bet level
        last_aggressive = -1
        for i in range(len(state.action_history) - 1, -1, -1):
            if state.action_history[i].action_type in (ActionType.BET, ActionType.RAISE, ActionType.ALL_IN):
                last_aggressive = i
                break

        # Get actions since the last aggressive action (or all actions if none)
        round_actions = state.action_history[last_aggressive:] if last_aggressive >= 0 else state.action_history

        # Count distinct active players who have acted (non-folding) in this round
        acted = set()
        for action in round_actions:
            if action.action_type != ActionType.FOLD and action.player in active:
                acted.add(action.player)

        # All active players must have acted in the current betting round
        if len(acted) < len(active):
            return False

        # Check that all active players have matched the current bet level
        # (no outstanding bet to call — bet_to_call = max(contributions) after a call)
        active_contributions = [state.contributions[p] for p in active]
        if max(active_contributions) != min(active_contributions):
            return False

        return True
    
    def is_terminal(self, state: GameState) -> bool:
        """Check if state is terminal."""
        return state.terminal or state.street == 4
    
    def get_payoffs(self, state: GameState) -> List[float]:
        """Get payoffs at terminal state for multi-way showdown."""
        if state.terminal_reason == "fold":
            # Return payoffs as already set (could be multi-way if others folded)
            return state.payoffs if state.payoffs else [0.0] * state.n_players

        # Showdown: evaluate all hands and split pot among winners
        n_players = state.n_players

        # Collect each player's best 5-card hand
        player_hands = []
        for i in range(n_players):
            start_idx = i * 2
            hole = [state.hole_cards[start_idx + j] for j in range(2) if start_idx + j < len(state.hole_cards)]
            full_hand = hole + state.board
            player_hands.append(full_hand)

        # Find the winning hand(s)
        best_hand_index = -1
        winners = []

        for i in range(n_players):
            if best_hand_index == -1:
                best_hand_index = i
                winners = [i]
            else:
                result = self.evaluator.compare(player_hands[i], player_hands[best_hand_index])
                if result == 1:  # Current player beats best
                    best_hand_index = i
                    winners = [i]
                elif result == 0:  # Tie with best
                    if best_hand_index not in winners:
                        winners.append(best_hand_index)
                    winners.append(i)
            # result == -1: current loses to best, no action needed

        if not winners:
            winners = [best_hand_index]

        # Payoffs: winners get their share of the pot
        payoffs = [0.0] * n_players
        win_amount = state.pot / len(winners)
        for w in winners:
            payoffs[w] = win_amount

        # Losers get 0 — their contribution is already reflected in their reduced stack
        # (payoffs are initialized to 0.0 above; no additional adjustment needed)
        return payoffs

    def resolve(self, state: GameState) -> List[float]:
        """Resolve the hand and return payoffs."""
        if state.terminal_reason == "fold":
            # Return payoffs as already set
            return state.payoffs if state.payoffs else [0.0] * state.n_players
        return self.get_payoffs(state)


def create_river_state(
    p0_cards: List[str],
    p1_cards: List[str],
    board: List[str],
    pot: float,
    stacks: List[float],
    current_player: int = 0,
    bet_to_call: float = 0.0,
    action_history: List[Action] = None,
    n_players: int = 2,
    extra_hole_cards: List[str] = None
) -> GameState:
    """
    Create a river game state with known cards.

    For river solver, all 5 board cards are known.

    Args:
        p0_cards: Player 0 hole cards like ["Ac", "Kd"]
        p1_cards: Player 1 hole cards like ["Qs", "Js"]
        board: 5 board cards like ["Kh", "8c", "3d", "2s", "Ks"]
        pot: Current pot size
        stacks: Stack sizes in big blinds [p0, p1, ...]
        current_player: Player to act first
        bet_to_call: Amount needed to call
        action_history: List of previous actions
        n_players: Total number of players (2-6)
        extra_hole_cards: Additional hole cards for 3+ players [[p2_cards], [p3_cards], ...]
    """
    deck = Deck()

    hole_cards = []
    for card_str in p0_cards:
        hole_cards.append(deck.parse(card_str))
    for card_str in p1_cards:
        hole_cards.append(deck.parse(card_str))

    # Add extra hole cards for additional players
    if extra_hole_cards:
        for player_cards in extra_hole_cards:
            for card_str in player_cards:
                hole_cards.append(deck.parse(card_str))

    board_cards = [deck.parse(c) for c in board]

    # Initialize contributions based on number of players
    contributions = [0.0] * n_players

    return GameState(
        hole_cards=hole_cards,
        board=board_cards,
        n_players=n_players,
        pot=pot,
        contributions=contributions,
        stacks=list(stacks),
        current_player=current_player,
        action_history=action_history or [],
        street=3,  # River
        bet_to_call=bet_to_call
    )


def create_multiway_river_state(
    all_hole_cards: List[str],  # Flat list of hole cards: [p0c1, p0c2, p1c1, p1c2, ...]
    board: List[str],
    pot: float,
    stacks: List[float],
    current_player: int = 0,
    bet_to_call: float = 0.0,
    action_history: List[Action] = None
) -> GameState:
    """
    Create a river game state with multiple players using flat hole card list.

    Args:
        all_hole_cards: Flat list of hole card strings [p0c1, p0c2, p1c1, p1c2, ...]
        board: 5 board cards
        pot: Current pot size
        stacks: Stack sizes in big blinds
        current_player: Player to act first
        bet_to_call: Amount needed to call
        action_history: List of previous actions
    """
    deck = Deck()
    n_players = len(all_hole_cards) // 2
    hole_cards = [deck.parse(c) for c in all_hole_cards]
    board_cards = [deck.parse(c) for c in board]
    contributions = [0.0] * n_players

    return GameState(
        hole_cards=hole_cards,
        board=board_cards,
        n_players=n_players,
        pot=pot,
        contributions=contributions,
        stacks=list(stacks),
        current_player=current_player,
        action_history=action_history or [],
        street=3,
        bet_to_call=bet_to_call
    )


# Simple test
if __name__ == "__main__":
    game = TexasHoldEm()
    
    # River scenario: AcKd vs QsJs on Kh
    state = create_river_state(
        p0_cards=["Ac", "Kd"],
        p1_cards=["Qs", "Js"],
        board=["Kh", "8c", "3d", "2s", "Ks"],  # Board has Kh and Ks
        pot=10.0,
        stacks=[100.0, 100.0],
        current_player=0
    )
    
    print(f"State: P0 has Ac Kd, P1 has Qs Js")
    print(f"Board: Kh 8c 3d 2s Ks")
    print(f"Valid actions for P0: {game.get_valid_actions(state, 0)}")
    
    # Test hand evaluation
    p0_cards = [state.hole_cards[0], state.hole_cards[1]] + state.board
    p1_cards = [state.hole_cards[2], state.hole_cards[3]] + state.board
    
    print(f"\nP0 best hand: {Hand(p0_cards)}")
    print(f"P1 best hand: {Hand(p1_cards)}")
    
    result = HandEvaluator.compare(p0_cards, p1_cards)
    print(f"Result: {'P0 wins' if result == -1 else 'P1 wins' if result == 1 else 'Tie'}")
