"""
Flop Solver for 2-player Texas Hold'em.

Implements MCCFR solving at the flop street with chance sampling
for the remaining turn and river cards.
"""

from typing import List, Dict, Tuple, Optional, Callable
import numpy as np
import random
import os
import sys

# path removed — gto-poker is pip-installed
from gto_poker.deck import Deck, Card
from gto_poker.hand import Hand, HandEvaluator

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from games.texas_hold_em import TexasHoldEm, GameState, Action, ActionType
from games.infosets import InfoSetManager, InfoSet
from cfr.engine import CFREngine


def create_flop_state(
    p0_cards: List[str],
    p1_cards: List[str],
    flop: List[str],
    pot: float,
    stacks: List[float],
    current_player: int = 0,
    bet_to_call: float = 0.0,
    action_history: List[Action] = None
) -> GameState:
    """
    Create a flop game state with known hole cards and flop cards.
    
    Args:
        p0_cards: Player 0 hole cards like ["Ac", "Kd"]
        p1_cards: Player 1 hole cards like ["Qs", "Js"]
        flop: 3 flop cards like ["Kh", "8c", "3d"]
        pot: Current pot size
        stacks: Stack sizes in big blinds
        current_player: Player to act (0 or 1)
        bet_to_call: Amount needed to call (0 if no bet)
        action_history: Optional prior action history
        
    Returns:
        GameState at flop street
    """
    deck = Deck()
    
    hole_cards = []
    for card_str in p0_cards:
        hole_cards.append(deck.parse(card_str))
    for card_str in p1_cards:
        hole_cards.append(deck.parse(card_str))
    
    flop_cards = [deck.parse(c) for c in flop]
    
    return GameState(
        hole_cards=hole_cards,
        board=flop_cards,
        pot=pot,
        stacks=list(stacks),
        current_player=current_player,
        action_history=list(action_history) if action_history else [],
        street=1,  # Flop street
        bet_to_call=bet_to_call,
        last_bettor=-1
    )


def solve_flop(
    p0_cards: List[str],
    p1_cards: List[str],
    flop: List[str],
    pot: float,
    stacks: List[float] = None,
    iterations: int = 1000,
    bet_sizes: List[float] = None,
    callback: Callable = None
) -> Tuple[Dict[str, np.ndarray], TexasHoldEm, GameState]:
    """
    Solve a flop situation using CFR with chance sampling.
    
    The flop solver handles betting on the flop street, then samples
    turn and river cards via chance sampling to resolve the hand.
    
    Args:
        p0_cards: Player 0 hole cards like ["Ac", "Kd"]
        p1_cards: Player 1 hole cards like ["Qs", "Js"]
        flop: 3 flop cards like ["Kh", "8c", "3d"]
        pot: Current pot size
        stacks: Stack sizes in big blinds, default [100, 100]
        iterations: Number of CFR iterations
        bet_sizes: Available bet sizes as pot multipliers
        callback: Optional callback after each iteration
        
    Returns:
        Tuple of (strategies dict, game, initial_flop_state)
    """
    stacks = stacks or [100.0, 100.0]
    bet_sizes = bet_sizes or [0.5, 1.0]
    
    # Create game
    game = TexasHoldEm(stack_sizes=stacks, bet_sizes=bet_sizes)
    
    # Create initial flop state with known hole cards and flop
    state = create_flop_state(p0_cards, p1_cards, flop, pot, stacks)
    
    # Create CFR engine
    engine = CFREngine(game)
    
    # Solve with chance sampling (needed to sample turn/river cards)
    strategies = engine.solve(state, iterations=iterations, sample_chance=True, callback=callback)
    
    return strategies, game, state


def solve_flop_basic(
    p0_cards: List[str],
    p1_cards: List[str],
    flop: List[str],
    pot: float,
    stacks: List[float] = None,
    iterations: int = 1000,
    bet_sizes: List[float] = None
) -> Dict[str, np.ndarray]:
    """
    Simple flop solver - just returns strategies dict.
    
    Args:
        p0_cards: Player 0 hole cards like ["Ac", "Kd"]
        p1_cards: Player 1 hole cards like ["Qs", "Js"]
        flop: 3 flop cards like ["Kh", "8c", "3d"]
        pot: Current pot size
        stacks: Stack sizes in big blinds
        iterations: Number of CFR iterations
        bet_sizes: Available bet sizes as pot multipliers
        
    Returns:
        Dictionary mapping infoset keys to average strategies
    """
    strategies, _, _ = solve_flop(
        p0_cards=p0_cards,
        p1_cards=p1_cards,
        flop=flop,
        pot=pot,
        stacks=stacks,
        iterations=iterations,
        bet_sizes=bet_sizes
    )
    return strategies


# Test function
def test_flop_solve():
    """
    Test the flop solver with a simple scenario.
    
    Scenario:
    - P0: AcKd (top pair + Ace kicker)
    - P1: QsJs (open-ended straight draw)
    - Flop: Kh 8c 3d (pairs Kings, both players have straight draws)
    """
    print("=== Flop Solver Test ===")
    print("\nScenario:")
    print("\n  P0: AcKd (top pair)")
    print("  P1: QsJs (straight draw)")
    print("  Flop: Kh 8c 3d")
    print()
    
    strategies, game, state = solve_flop(
        p0_cards=["Ac", "Kd"],
        p1_cards=["Qs", "Js"],
        flop=["Kh", "8c", "3d"],
        pot=10.0,
        stacks=[100.0, 100.0],
        iterations=500,
        bet_sizes=[0.5, 1.0]
    )
    
    print(f"Solved in {len(strategies)} infosets")
    
    # Show some sample strategies
    count = 0
    for key, strat in strategies.items():
        if count < 10:  # Show first 10
            print(f"\n{key}")
            # Get actions for this infoset
            player = 0 if "p0:" in key else 1 if "p1:" in key else -1
            if player >= 0:
                actions = game.get_valid_actions(state, player)
                for i, (a, p) in enumerate(zip(actions, strat)):
                    if i < len(actions):
                        print(f"  {actions[i]}: {p:.3f}")
        count += 1
    
    print(f"\n... and {len(strategies) - 10} more infosets")
    
    return strategies, game, state


def test_flop_convergence():
    """
    Test flop solver convergence by running multiple iterations.
    """
    print("=== Flop Solver Convergence Test ===")
    
    def progress_callback(iter_num, infoset_manager):
        if iter_num % 200 == 0:
            print(f"  Iteration {iter_num}: {len(infoset_manager)} infosets")
    
    print("\nRunning 800 iterations...")
    strategies, game, state = solve_flop(
        p0_cards=["Ac", "Kd"],
        p1_cards=["Qs", "Js"],
        flop=["Kh", "8c", "3d"],
        pot=10.0,
        stacks=[100.0, 100.0],
        iterations=800,
        bet_sizes=[0.5, 1.0],
        callback=progress_callback
    )
    
    print(f"\nConverged with {len(strategies)} infosets")
    
    # Analyze strategy convergence
    print("\nStrategy summary:")
    for key, strat in list(strategies.items())[:5]:
        print(f"  {key[:50]}: {strat}")
    
    return strategies, game, state


if __name__ == "__main__":
    # Run test
    test_flop_solve()
