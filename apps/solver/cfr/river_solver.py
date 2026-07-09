"""
River Solver for 2-6 player Texas Hold'em.

Implements specialized river solving with:
- Configurable bet sizes
- Multi-way pot support (2-6 players)
- Efficient terminal state handling
- Strategy extraction for all players
"""

from typing import List, Dict, Tuple, Optional, Callable
import numpy as np
import os
import sys

# path removed — gto-poker is pip-installed
from gto_poker.deck import Deck, Card
from gto_poker.hand import Hand, HandEvaluator

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from games.texas_hold_em import TexasHoldEm, GameState, Action, ActionType, create_river_state, create_multiway_river_state
from games.infosets import InfoSetManager, InfoSet
from cfr.engine import CFREngine


def create_river_state_from_params(
    p0_cards: List[str],
    p1_cards: List[str],
    board: List[str],
    pot: float,
    stacks: List[float] = None,
    current_player: int = 0,
    bet_to_call: float = 0.0,
    action_history: List[Action] = None
) -> GameState:
    """
    Create a river game state with all cards known.
    
    This is a convenience wrapper around create_river_state.
    
    Args:
        p0_cards: Player 0 hole cards
        p1_cards: Player 1 hole cards
        board: 5 board cards
        pot: Current pot size
        stacks: Stack sizes in big blinds
        current_player: Player to act (0 or 1)
        bet_to_call: Amount needed to call (0 if no bet)
        action_history: Optional prior action history
        
    Returns:
        GameState at river street (street=3)
    """
    stacks = stacks or [100.0, 100.0]
    return create_river_state(
        p0_cards=p0_cards,
        p1_cards=p1_cards,
        board=board,
        pot=pot,
        stacks=stacks,
        current_player=current_player,
        bet_to_call=bet_to_call,
        action_history=action_history
    )


def solve_river_spot(
    p0_cards: List[str],
    p1_cards: List[str],
    board: List[str],
    pot: float,
    stacks: List[float] = None,
    iterations: int = 1000,
    bet_sizes: List[float] = None,
    callback: Callable[[int, InfoSetManager], None] = None
) -> Tuple[Dict[str, np.ndarray], TexasHoldEm, GameState]:
    """
    Solve a river situation with configurable bet sizes.
    
    Args:
        p0_cards: Player 0 hole cards like ["Ac", "Kd"]
        p1_cards: Player 1 hole cards like ["Qs", "Js"]
        board: 5 board cards like ["Kh", "8c", "3d", "2s", "Ks"]
        pot: Current pot size
        stacks: Stack sizes in big blinds, default [100, 100]
        iterations: Number of CFR iterations
        bet_sizes: Available bet sizes as pot multipliers
        callback: Optional callback after each iteration
        
    Returns:
        Tuple of (strategies dict, game, final_state)
    """
    stacks = stacks or [100.0, 100.0]
    bet_sizes = bet_sizes or [0.5, 1.0]
    
    # Create game with specified bet sizes
    game = TexasHoldEm(stack_sizes=stacks, bet_sizes=bet_sizes)
    
    # Create initial river state
    state = create_river_state(
        p0_cards=p0_cards,
        p1_cards=p1_cards,
        board=board,
        pot=pot,
        stacks=stacks
    )
    
    # Create CFR engine
    engine = CFREngine(game)
    
    # Solve (no chance sampling needed - all cards known at river)
    strategies = engine.solve(state, iterations=iterations, sample_chance=False, callback=callback)
    
    return strategies, game, state


def solve_multiway_river(
    all_hole_cards: List[str],
    board: List[str],
    pot: float,
    stacks: List[float] = None,
    iterations: int = 1000,
    bet_sizes: List[float] = None,
    callback: Callable[[int, InfoSetManager], None] = None
) -> Tuple[Dict[str, np.ndarray], TexasHoldEm, GameState]:
    """
    Solve a multi-way river situation (3-6 players).
    
    Args:
        all_hole_cards: All hole cards in order [p0c1, p0c2, p1c1, p1c2, ...]
        board: 5 board cards
        pot: Current pot size
        stacks: Stack sizes for each player
        iterations: Number of CFR iterations
        bet_sizes: Available bet sizes as pot multipliers
        callback: Optional callback after each iteration
        
    Returns:
        Tuple of (strategies dict, game, final_state)
    """
    n_players = len(all_hole_cards) // 2
    stacks = stacks or [100.0] * n_players
    bet_sizes = bet_sizes or [0.5, 1.0]
    
    # Create game with specified bet sizes and player count
    game = TexasHoldEm(stack_sizes=stacks, bet_sizes=bet_sizes, n_players=n_players)
    
    # Create multi-way river state
    state = create_multiway_river_state(
        all_hole_cards=all_hole_cards,
        board=board,
        pot=pot,
        stacks=stacks
    )
    
    # Create CFR engine
    engine = CFREngine(game)
    
    # Solve
    strategies = engine.solve(state, iterations=iterations, sample_chance=False, callback=callback)
    
    return strategies, game, state


def solve_river_with_bets(
    p0_cards: List[str],
    p1_cards: List[str],
    board: List[str],
    pot: float,
    stacks: List[float],
    bet_size: float,
    iterations: int = 1000,
    facing_bet: bool = False,
    bet_to_call: float = 0.0,
    current_player: int = 0
) -> Tuple[Dict[str, np.ndarray], TexasHoldEm, GameState]:
    """
    Solve a river situation with a specific bet size.
    
    This is useful for solving spots where a bet size is already known,
    such as when analyzing a specific line in a hand history.
    
    Args:
        p0_cards: Player 0 hole cards
        p1_cards: Player 1 hole cards
        board: 5 board cards
        pot: Current pot size
        stacks: Stack sizes in big blinds
        bet_size: Bet size as pot multiplier
        iterations: Number of CFR iterations
        facing_bet: True if player is facing a bet
        bet_to_call: Amount needed to call if facing_bet
        current_player: Player to act (0 or 1)
        
    Returns:
        Tuple of (strategies dict, game, final_state)
    """
    # Create game with single bet size
    game = TexasHoldEm(stack_sizes=stacks, bet_sizes=[bet_size])
    
    # Create initial state
    state = create_river_state(
        p0_cards=p0_cards,
        p1_cards=p1_cards,
        board=board,
        pot=pot,
        stacks=stacks,
        current_player=current_player,
        bet_to_call=bet_to_call if facing_bet else 0.0
    )
    
    # Create CFR engine
    engine = CFREngine(game)
    
    # Solve
    strategies = engine.solve(state, iterations=iterations, sample_chance=False)
    
    return strategies, game, state


def get_river_action(
    p0_cards: List[str],
    p1_cards: List[str],
    board: List[str],
    pot: float,
    stacks: List[float],
    strategy: Dict[str, np.ndarray],
    player: int = 0,
    bet_sizes: List[float] = None
) -> str:
    """
    Get the recommended action for a player given a solved strategy.
    
    Args:
        p0_cards: Player 0 hole cards
        p1_cards: Player 1 hole cards
        board: 5 board cards
        pot: Current pot size
        stacks: Stack sizes
        strategy: Solved strategy dictionary
        player: Player index (0 or 1)
        bet_sizes: Bet sizes used in solving
        
    Returns:
        Recommended action string
    """
    bet_sizes = bet_sizes or [0.5, 1.0]
    
    # Create game and state to get valid actions
    game = TexasHoldEm(stack_sizes=stacks, bet_sizes=bet_sizes)
    state = create_river_state(
        p0_cards=p0_cards,
        p1_cards=p1_cards,
        board=board,
        pot=pot,
        stacks=stacks
    )
    
    # Get infoset key
    infoset_key = state.infoset_key(player)
    
    # Get strategy for this infoset
    if infoset_key in strategy:
        strat = strategy[infoset_key]
        valid_actions = game.get_valid_actions(state, player)
        
        if len(strat) == len(valid_actions):
            # Return action with highest probability
            best_idx = np.argmax(strat)
            return valid_actions[best_idx]
    
    return "check"  # Default if not found


# Test function
def test_river_solver():
    """Test the river solver with various scenarios."""
    print("=== River Solver Test ===")
    
    # Scenario 1: Basic heads-up river
    print("\n--- Scenario 1: Heads-up river ---")
    print("P0: AcKd (top pair)")
    print("P1: QsJs (missed draw)")
    print("Board: Kh 8c 3d 2s Ks")
    
    strategies, game, state = solve_river_spot(
        p0_cards=["Ac", "Kd"],
        p1_cards=["Qs", "Js"],
        board=["Kh", "8c", "3d", "2s", "Ks"],
        pot=10.0,
        stacks=[100.0, 100.0],
        iterations=200,
        bet_sizes=[0.5, 1.0]
    )
    
    print(f"Solved {len(strategies)} infosets")
    for key, strat in list(strategies.items())[:3]:
        print(f"  {key[:50]}... -> {strat}")
    
    # Scenario 2: 3-way river
    print("\n--- Scenario 2: 3-way river ---")
    print("P0: AcKd (top pair)")
    print("P1: QsJs (middle pair)")
    print("P2: 2h2d (bottom pair)")
    print("Board: Kh 8c 3d 2s Ks")
    
    strategies, game, state = solve_multiway_river(
        all_hole_cards=["Ac", "Kd", "Qs", "Js", "2h", "2d"],
        board=["Kh", "8c", "3d", "2s", "Ks"],
        pot=30.0,
        stacks=[100.0, 100.0, 100.0],
        iterations=200,
        bet_sizes=[0.5]
    )
    
    print(f"Solved {len(strategies)} infosets")
    
    # Scenario 3: Short stack scenario
    print("\n--- Scenario 3: Short stack (20bb) ---")
    strategies, game, state = solve_river_spot(
        p0_cards=["Ac", "Kd"],
        p1_cards=["Qs", "Js"],
        board=["Kh", "8c", "3d", "2s", "Ks"],
        pot=10.0,
        stacks=[20.0, 20.0],
        iterations=200,
        bet_sizes=[0.5, 1.0]
    )
    
    print(f"Solved {len(strategies)} infosets")
    
    return strategies, game, state


if __name__ == "__main__":
    test_river_solver()
