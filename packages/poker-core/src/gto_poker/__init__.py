"""
GTO Wizard Clone — Poker Core Library
Core poker mathematics: deck, hand evaluation, equity calculation, hand history parsing
"""

from .deck import Deck
from .hand import Hand, HandEvaluator
from .equity import EquityCalculator
from .range import RangeParser
from .hand_history import parse_winamax_hh, ParsedHand, PlayerInfo, Action, detect_format
from .icm import (
    ICMResult,
    icm_calculate,
    icm_equity_chips,
    malmoud_harville,
    calculate_bubble_factor,
)
from .plo4 import PLO4Evaluator, PLO4Equity, plo4_hand_rank_to_percentage
from .plo4_range import PLO4RangeParser, expand_range_to_hands
from .bomb_pot import (
    Phase,
    ActionType,
    Position,
    BombPotAction,
    BombPotGameState,
    BombPotGameModel,
    BombPotEquity,
)
from .double_board import (
    DoubleBoardEvaluator,
    DoubleBoardEquity,
    ScoopTracker,
)

__all__ = [
    "Deck", "Hand", "HandEvaluator", "EquityCalculator", "RangeParser",
    "parse_winamax_hh", "ParsedHand", "PlayerInfo", "Action", "detect_format",
    # ICM
    "ICMResult",
    "icm_calculate",
    "icm_equity_chips",
    "malmoud_harville",
    "calculate_bubble_factor",
    # PLO4
    "PLO4Evaluator",
    "PLO4Equity", 
    "plo4_hand_rank_to_percentage",
    "PLO4RangeParser",
    "expand_range_to_hands",
    # Bomb Pot
    "Phase",
    "ActionType",
    "Position",
    "BombPotAction",
    "BombPotGameState",
    "BombPotGameModel",
    "BombPotEquity",
    # Double Board
    "DoubleBoardEvaluator",
    "DoubleBoardEquity",
    "ScoopTracker",
]
