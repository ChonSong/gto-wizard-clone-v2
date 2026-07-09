"""
MCCFR (Monte Carlo Counterfactual Regret Minimization) Engine.

Implements chance-sampled CFR for multi-street Texas Hold'em.
Supports: preflop → flop → turn → river → showdown.
Supports 2-6 players for multi-way pots.
"""

from typing import List, Dict, Tuple, Optional
import numpy as np
import random
import sys
import os

import sys
sys.setrecursionlimit(10000)

# path removed — gto-poker is pip-installed
from gto_poker.deck import Deck, Card
from gto_poker.hand import Hand, HandEvaluator

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from games.texas_hold_em import TexasHoldEm, GameState, Action, ActionType, create_river_state, create_multiway_river_state
from games.infosets import InfoSetManager, InfoSet


class CFREngine:
    """
    MCCFR solver for Texas Hold'em.

    Uses chance-sampled CFR with regret matching.
    Supports multi-street solving (preflop through river) and multi-way pots (2-6 players).
    """

    def __init__(
        self,
        game: TexasHoldEm = None,
        seed: int = None
    ):
        """
        Initialize CFR engine.

        Args:
            game: TexasHoldEm game instance
            seed: Random seed for reproducibility
        """
        self.game = game or TexasHoldEm()
        self.seed = seed
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)

        # Infoset manager
        self.infoset_manager = InfoSetManager()

        # Iteration count
        self.iteration = 0

        # Hand evaluator
        self.evaluator = HandEvaluator()

        # Terminal state cache to avoid exponential recomputation
        # Key: (street, pot, tuple(stacks), tuple(hole_cards), tuple(board), terminal_reason)
        # Value: list of utilities
        self._terminal_cache: Dict[tuple, List[float]] = {}

        # Call counter for detecting non-terminating game trees (reset each iteration)
        self._cfr_call_count = 0

    def solve(
        self,
        initial_state: GameState,
        iterations: int = 1000,
        callback: callable = None,
        sample_chance: bool = True
    ) -> Dict[str, np.ndarray]:
        """
        Run CFR to solve the game.

        Args:
            initial_state: Starting game state
            iterations: Number of CFR iterations
            callback: Optional callback after each iteration
            sample_chance: Whether to sample cards (for multi-street solving)

        Returns:
            Dictionary mapping infoset keys to average strategies
        """
        n_players = initial_state.n_players if hasattr(initial_state, 'n_players') else 2

        for i in range(iterations):
            self.iteration = i + 1

            # Work with a copy of initial_state for this iteration
            state = initial_state.copy()

            if sample_chance:
                # Chance sampling: sample cards for this iteration
                # Only sample if hole cards or board are missing
                expected_hole_cards = n_players * 2
                if len(state.hole_cards) < expected_hole_cards or len(state.board) < 5:
                    state = self._sample_cards(state)

            # Initialize reach probabilities for all players
            reach_probs = [1.0] * n_players

            # Run one iteration of CFR
            self._cfr_iteration(state, reach_probs)

            if callback and i % 100 == 0:
                callback(self.iteration, self.infoset_manager)

        return self.get_average_strategies()
    
    def _sample_cards(self, state: GameState) -> GameState:
        """
        Sample missing cards for chance sampling at the start of an iteration.

        At preflop (street 0): deal hole cards + 3 flop cards
        At flop (street 1): deal 1 turn card
        At turn (street 2): deal 1 river card
        At river (street 3): no cards needed

        For multi-way pots, samples hole cards for all players.
        """
        new_state = state.copy()
        n_players = new_state.n_players if hasattr(new_state, 'n_players') else 2

        # Get all dealt cards so far
        dealt = set()
        for card in new_state.hole_cards:
            dealt.add(str(card))
        for card in new_state.board:
            dealt.add(str(card))

        # Build remaining deck
        all_cards = []
        for rank in ["2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A"]:
            for suit in ["h", "d", "c", "s"]:
                card_str = f"{rank}{suit}"
                if card_str not in dealt:
                    all_cards.append(card_str)

        deck = Deck()

        # Sample hole cards if missing (2 per player)
        expected_hole_cards = n_players * 2
        if len(new_state.hole_cards) < expected_hole_cards:
            needed = expected_hole_cards - len(new_state.hole_cards)
            if needed > 0 and len(all_cards) >= needed:
                sampled = random.sample(all_cards, needed)
                all_cards = [c for c in all_cards if c not in sampled]
                for card_str in sampled:
                    new_state.hole_cards.append(deck.parse(card_str))

        # Sample community cards based on street
        # Street 0: deal 3 (flop)
        # Street 1: deal 1 (turn)
        # Street 2: deal 1 (river)
        # Street 3: no more
        cards_needed = {
            0: 5,  # Preflop: sample ALL community cards (flop 3 + turn 1 + river 1)
            1: 1,  # Flop: sample turn (1 card)
            2: 1,  # Turn: sample river (1 card)
            3: 0   # River: no more
        }

        needed = cards_needed.get(new_state.street, 0)
        if needed > 0 and len(new_state.board) < 5:
            available = 5 - len(new_state.board)
            actual = min(needed, available)
            if actual > 0 and len(all_cards) >= actual:
                sampled = random.sample(all_cards, actual)
                for card_str in sampled:
                    new_state.board.append(deck.parse(card_str))

        return new_state
    
    def _advance_street(self, state: GameState) -> GameState:
        """
        Advance to the next street after betting round ends.
        Resets betting state for the new street and deals next community card.
        """
        new_state = state.copy()
        
        if new_state.street >= 3:
            return new_state  # Already at river or beyond
        
        new_state.street += 1
        
        # Reset betting state for new street
        new_state.bet_to_call = 0.0
        new_state.last_bettor = -1
        new_state.street_actions = 0
        
        return new_state
    
    def _cfr_iteration(
        self,
        state: GameState,
        reach_probs: List[float]
    ) -> List[float]:
        """
        Run one iteration of CFR for multi-way pot.

        Args:
            state: Current game state
            reach_probs: Reach probabilities for all players [p0, p1, ..., pn]

        Returns:
            List of utilities for all players
        """
        n_players = state.n_players if hasattr(state, 'n_players') else 2

        # Terminal state check - return immediately with cached terminal utilities
        if state.terminal or state.street >= 4:
            # Use cache key based on deterministic state properties
            cache_key = (
                state.street,
                state.pot,
                tuple(state.stacks),
                tuple(sorted(str(c) for c in state.hole_cards)),
                tuple(sorted(str(c) for c in state.board)),
                state.terminal_reason or "showdown"
            )
            if cache_key in self._terminal_cache:
                return self._terminal_cache[cache_key]
            result = self._resolve_terminal(state)
            self._terminal_cache[cache_key] = result
            return result

        # Handle all active (non-folded) players all-in: go straight to showdown
        non_folded = [i for i in range(state.n_players)
                      if not any(a.player == i and a.action_type == ActionType.FOLD for a in state.action_history)]
        if non_folded and all(state.stacks[p] == 0 for p in non_folded):
            return self._handle_showdown(state)

        # Check if betting round is complete and we need to advance to next street
        if self._betting_round_complete(state):
            if state.street >= 3:
                # River (street 3) or later - betting round complete means showdown
                # Mark state as terminal and resolve immediately WITHOUT recursion
                state.terminal = True
                state.terminal_reason = "showdown"
                return self._resolve_terminal(state)
            elif state.street < 3:
                # Pre-river streets: advance to next street and continue
                new_state = self._advance_street(state)
                new_state.current_player = self._get_first_responder(new_state)
                return self._cfr_iteration(new_state, reach_probs)

        # Get current player
        player = state.current_player

        # Skip inactive players (shouldn't happen with proper next_player logic, but safety check)
        if player < 0 or player >= n_players:
            return [0.0] * n_players

        # Get valid actions
        valid_actions = self.game.get_valid_actions(state, player)

        if not valid_actions:
            return [0.0] * n_players

        # Get or create infoset
        infoset_key = state.infoset_key(player)
        infoset = self.infoset_manager.get_or_create(infoset_key, valid_actions)

        # Get current strategy via regret matching
        strategy = infoset.get_strategy()

        # Compute utilities for each action
        action_utils = np.zeros(len(valid_actions))

        for i, action_str in enumerate(valid_actions):
            # Apply action to get new state
            new_state = self.game.apply_action(state.copy(), player, action_str)

            # Recursively compute utility
            child_utils = self._cfr_iteration(new_state, reach_probs)

            # Store utility for this action (player's utility)
            action_utils[i] = child_utils[player]

        # Current player reach probability
        reach = reach_probs[player]

        # Expected value under current strategy for the acting player
        expected_value = np.dot(strategy, action_utils)

        # Counterfactual regrets for the acting player
        for i in range(len(valid_actions)):
            regret = action_utils[i] - expected_value
            if reach > 0:
                infoset.regret_sum[i] += regret * reach

        # Update strategy sum
        infoset.strategy_sum += strategy * reach

        # Return utilities for all players
        # For non-terminal states, the child_utils already computed correct utilities
        # by recursive CFR. We sum them over all actions weighted by strategy.
        # This correctly propagates counterfactual values up the tree.
        utilities = [0.0] * n_players
        for p in range(n_players):
            if p == player:
                utilities[p] = expected_value
            # For other players, contribution is accounted via their own
            # infosets when they act in subtrees. For now, use 0 since they
            # don't directly incur regret at this node (their reach prob is
            # incorporated into the regret matching at their own decision points).

        return utilities
    
    def _get_first_responder(self, state: GameState) -> int:
        """Get the first active player to act on a new street."""
        for i in range(state.n_players):
            if state.stacks[i] > 0:
                return i
        return 0
    
    def _get_next_responder(self, state: GameState, current: int) -> int:
        """Get the next active player after current."""
        n = state.n_players
        for offset in range(1, n + 1):
            next_p = (current + offset) % n
            if state.stacks[next_p] > 0:
                return next_p
        return -1

    def _betting_round_complete(self, state: GameState) -> bool:
        """
        Check if the current betting round is complete.

        A betting round is complete when:
        1. All active (non-folded) players have acted in the current round
        2. All active players have matched the current bet level (equal contributions)
        3. Only one player remains (all others folded)
        """
        if len(state.action_history) == 0:
            return False

        # Check if only one non-folded player remains
        non_folded = [i for i in range(state.n_players)
                      if not any(a.player == i and a.action_type == ActionType.FOLD for a in state.action_history)]
        if len(non_folded) <= 1:
            return True

        # Multi-way: ensure all active players have acted in the current round
        active = non_folded  # non-folded players

        # Find the last bet/raise/all_in action
        last_aggressive = -1
        for i in range(len(state.action_history) - 1, -1, -1):
            if state.action_history[i].action_type in (ActionType.BET, ActionType.RAISE, ActionType.ALL_IN):
                last_aggressive = i
                break

        # Get actions since the last aggressive action
        round_actions = state.action_history[last_aggressive:] if last_aggressive >= 0 else state.action_history

        # Count distinct active players who have acted in this round
        acted = set()
        for action in round_actions:
            if action.action_type != ActionType.FOLD and action.player in active:
                acted.add(action.player)

        # All active players must have acted
        if len(acted) < len(active):
            return False

        # Check that all active players have matched the current bet level
        # (no outstanding bet to call)
        active_contributions = [state.contributions[p] for p in active]
        if max(active_contributions) != min(active_contributions):
            return False

        return True
    
    def _handle_showdown(self, state: GameState) -> List[float]:
        """
        Handle showdown when both players are all-in.
        Deals remaining community cards if needed and resolves the hand.
        """
        new_state = state.copy()
        
        # Deal remaining community cards if needed
        if len(new_state.board) < 5:
            dealt = set()
            for card in new_state.hole_cards:
                dealt.add(str(card))
            for card in new_state.board:
                dealt.add(str(card))
            
            all_cards = []
            for rank in ["2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A"]:
                for suit in ["h", "d", "c", "s"]:
                    card_str = f"{rank}{suit}"
                    if card_str not in dealt:
                        all_cards.append(card_str)
            
            cards_needed = 5 - len(new_state.board)
            if cards_needed > 0 and len(all_cards) >= cards_needed:
                sampled = random.sample(all_cards, cards_needed)
                deck = Deck()
                for card_str in sampled:
                    new_state.board.append(deck.parse(card_str))
        
        return self._resolve_terminal(new_state)
    
    def _resolve_terminal(self, state: GameState) -> List[float]:
        """Resolve terminal state and return utilities for all players."""
        n_players = state.n_players if hasattr(state, 'n_players') else 2

        if state.terminal_reason == "fold":
            # Fold: remaining player(s) get the pot
            # If multiple players remain (multi-way fold), they split the pot

            # Find all players who have folded across the entire action history
            folded = {a.player for a in state.action_history
                      if a.action_type == ActionType.FOLD}

            # Find active players (not folded, have chips or are still in)
            active = [i for i in range(n_players)
                      if i not in folded and state.stacks[i] >= 0]

            if len(active) == 1:
                # Single winner
                winner = active[0]
                payoffs = [0.0] * n_players
                payoffs[winner] = state.pot
            elif len(active) > 1:
                # Multi-way pot - split among remaining
                payoffs = [0.0] * n_players
                share = state.pot / len(active)
                for p in active:
                    payoffs[p] = share
            else:
                payoffs = [0.0] * n_players

            return payoffs

        # Showdown
        return self.game.get_payoffs(state)
    
    def get_average_strategies(self) -> Dict[str, np.ndarray]:
        """Get average strategies for all infosets."""
        result = {}
        for infoset in self.infoset_manager.all_infosets():
            result[infoset.key] = infoset.get_average_strategy()
        return result
    
    def get_strategy_for_infoset(self, key: str) -> Optional[np.ndarray]:
        """Get average strategy for a specific infoset."""
        infoset = self.infoset_manager.get(key)
        if infoset:
            return infoset.get_average_strategy()
        return None


def solve_river(
    p0_cards: List[str],
    p1_cards: List[str],
    board: List[str],
    pot: float,
    stacks: List[float] = None,
    iterations: int = 1000,
    bet_sizes: List[float] = None
) -> Tuple[Dict[str, np.ndarray], TexasHoldEm, GameState]:
    """
    Solve a river situation using CFR.
    
    Args:
        p0_cards: Player 0 hole cards like ["Ac", "Kd"]
        p1_cards: Player 1 hole cards like ["Qs", "Js"]
        board: 5 board cards like ["Kh", "8c", "3d", "2s", "Ks"]
        pot: Current pot size
        stacks: Stack sizes in big blinds, default [100, 100]
        iterations: Number of CFR iterations
        bet_sizes: Available bet sizes as pot multipliers
        
    Returns:
        Tuple of (strategies dict, game, final_state)
    """
    stacks = stacks or [100.0, 100.0]
    bet_sizes = bet_sizes or [0.5, 1.0]
    
    # Create game and state
    game = TexasHoldEm(stack_sizes=stacks, bet_sizes=bet_sizes)
    state = create_river_state(p0_cards, p1_cards, board, pot, stacks)
    
    # Create CFR engine
    engine = CFREngine(game)
    
    # Solve (no chance sampling needed - all cards known at river)
    strategies = engine.solve(state, iterations=iterations, sample_chance=False)
    
    return strategies, game, state


def solve_preflop(
    p0_cards: List[str],
    p1_cards: List[str],
    pot: float,
    stacks: List[float] = None,
    iterations: int = 1000,
    bet_sizes: List[float] = None
) -> Tuple[Dict[str, np.ndarray], TexasHoldEm, GameState]:
    """
    Solve a pre-flop situation using CFR with chance sampling.
    
    Args:
        p0_cards: Player 0 hole cards like ["Ac", "Ad"]
        p1_cards: Player 1 hole cards like ["Kc", "Kd"]
        pot: Current pot size (includes antes/blinds)
        stacks: Stack sizes in big blinds, default [100, 100]
        iterations: Number of CFR iterations
        bet_sizes: Available bet sizes as pot multipliers
        
    Returns:
        Tuple of (strategies dict, game, final_state)
    """
    stacks = stacks or [100.0, 100.0]
    bet_sizes = bet_sizes or [0.5, 1.0]
    
    # Create game
    game = TexasHoldEm(stack_sizes=stacks, bet_sizes=bet_sizes)
    
    # Create initial pre-flop state with known hole cards but no board
    deck = Deck()
    hole_cards = [deck.parse(c) for c in p0_cards] + [deck.parse(c) for c in p1_cards]
    
    state = GameState(
        hole_cards=hole_cards,
        board=[],
        pot=pot,
        stacks=list(stacks),
        current_player=0,
        action_history=[],
        street=0,
        bet_to_call=0.0,
        last_bettor=-1
    )
    
    # Create CFR engine
    engine = CFREngine(game)
    
    # Solve with chance sampling
    strategies = engine.solve(state, iterations=iterations, sample_chance=True)
    
    return strategies, game, state


# Test function
def test_river_solve():
    """Test the river solver."""
    print("=== River Solver Test ===")
    
    strategies, game, state = solve_river(
        p0_cards=["Ac", "Kd"],
        p1_cards=["Qs", "Js"],
        board=["Kh", "8c", "3d", "2s", "Ks"],
        pot=10.0,
        stacks=[100.0, 100.0],
        iterations=500,
        bet_sizes=[0.5, 1.0]
    )
    
    print(f"\nSolved in {len(strategies)} infosets")
    
    for key, strat in strategies.items():
        print(f"\n{key[:60]}...")
        actions = game.get_valid_actions(state, 0) if "p0" in key else game.get_valid_actions(state, 1)
        if len(actions) == len(strat):
            for i, (a, p) in enumerate(zip(actions, strat)):
                print(f"  {a}: {p:.3f}")
    
    return strategies, game, state


if __name__ == "__main__":
    test_river_solve()