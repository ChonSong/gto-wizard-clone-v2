"""
CFR module for Monte Carlo Counterfactual Regret Minimization.

Exports:
- CFREngine: Main MCCFR solver engine
- solve_river: Convenience function for river solving
- solve_preflop: Convenience function for preflop solving
"""

from .engine import CFREngine, solve_river, solve_preflop
from .flop_solver import solve_flop, solve_flop_basic, create_flop_state
from .turn_solver import solve_turn, solve_turn_basic, create_turn_state
from .river_solver import (
    solve_river_spot,
    solve_multiway_river,
    solve_river_with_bets,
    get_river_action,
    create_river_state_from_params,
)

__all__ = [
    "CFREngine",
    "solve_river",
    "solve_preflop",
    "solve_flop",
    "solve_flop_basic",
    "create_flop_state",
    "solve_turn",
    "solve_turn_basic",
    "create_turn_state",
    "solve_river_spot",
    "solve_multiway_river",
    "solve_river_with_bets",
    "get_river_action",
    "create_river_state_from_params",
]
