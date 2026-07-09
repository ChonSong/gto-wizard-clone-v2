"""
GTO Comparison Service for Leak Identification.

Compares user actions against GTO baseline frequencies to identify
strategy leaks and provide actionable feedback.

Uses board texture, position, pot size, and stack depth to determine
the appropriate GTO baseline for comparison.
"""

import logging
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Dict, List, Optional

from apps.api.services.strategy_storage import get_strategy_storage

logger = logging.getLogger(__name__)


class BoardTexture(Enum):
    """Board texture classification for GTO baseline selection."""
    DRY_MONO = "dry_mono"           # Monotone board, no draws
    WET_PAIRS = "wet_pairs"         # Paired board with draws possible
    COORDINATED = "coordinated"     # Cards 8-T with straight possibilities
    HIGH_CARDS = "high_cards"       # Ace-high or Broadway cards
    LOW_CARDS = "low_cards"         # 2-7 range, disconnected
    TWO_PAIRS = "two_pairs"         # Two pair board
    TRIPS_BOARD = "trips_board"     # Three of a kind on board
    ACE_HIGH = "ace_high"           # Ace-high flop


class SpotCategory(Enum):
    """Spot category for GTO baseline mapping."""
    CBET_FLOP = "cbet_flop"                    # Continuation bet on flop
    CHECK_RAISE_FLOP = "check_raise_flop"      # Check-raise spot on flop
    FLOAT_FLOP = "float_flop"                  # Floating with weak hand
    DELAY_CBET = "delay_cbet"                  # Delayed cbet
    BARREL_TURN = "barrel_turn"                # Second barrel
    THIRD_BARREL = "third_barrel"              # Third barrel on river
    CHECK_FOLD = "check_fold"                 # Check-fold
    CHECK_CALL = "check_call"                 # Check-call
    DONK_BET = "donk_bet"                     # Donk bet
    LEAD_RIVER = "lead_river"                 # Lead river
    CHECK_RAISE_TURN = "check_raise_turn"     # Check-raise on turn
    HERO_3BET = "hero_3bet"                   # Hero 3-bet preflop
    HERO_4BET = "hero_4bet"                   # Hero 4-bet preflop
@dataclass
class GTOComparisonResult:
    """Result of comparing user action to GTO baseline."""
    spot_category: str
    ev_loss: float                    # Expected value loss in big blinds
    gto_action: str                  # GTO recommended action
    gto_frequency: float             # GTO action frequency
    user_action: str                 # User's actual action
    user_frequency: float            # User's action frequency (if available)
    recommendation: str              # Actionable feedback
    severity: str                    # "low", "medium", "high"
    board_texture: Optional[str] = None
    position: Optional[str] = None
    pot_size: Optional[float] = None


# GTO Baseline frequencies for common spots
# Maps SpotCategory -> {action: frequency} for 100bb deep, 2-handed play
GTO_BASELINE: Dict[SpotCategory, Dict[str, float]] = {
    # Flop c-bet frequencies by board type (IP OOP split implied)
    SpotCategory.CBET_FLOP: {
        "dry_mono": 0.85,      # Almost always c-bet dry monotone
        "wet_mixed": 0.55,     # Mixed strategy on wet boards
        "coordinated": 0.60,    # Most coordinated boards
        "high_cards": 0.65,    # Ace-high type boards
        "low_cards": 0.70,     # Low disconnected boards
        "pairs": 0.50,         # Paired boards - more mixed
    },
    
    # Check-raise frequencies on flop
    SpotCategory.CHECK_RAISE_FLOP: {
        "value": 0.15,         # Check-raise with value
        "bluff": 0.08,         # Check-raise as bluff
        "protected": 0.12,     # Check-raise with protection
    },
    
    # Floating frequencies on flop
    SpotCategory.FLOAT_FLOP: {
        "with_equity": 0.40,   # Float with equity
        "air": 0.15,           # Float as pure bluff
    },
    
    # Delayed c-bet frequencies
    SpotCategory.DELAY_CBET: {
        "turn_hit": 0.70,      # Delayed cbet when turn helps
        "turn_miss": 0.25,     # Delayed cbet as bluff
    },
    
    # Barrel frequencies by street
    SpotCategory.BARREL_TURN: {
        "safe": 0.65,          # Barrel on safe turn
        "overcard": 0.40,      # Barrel when overcard hits
    },
    
    SpotCategory.THIRD_BARREL: {
        "river_bluff": 0.12,   # Third barrel as bluff
        "river_value": 0.85,   # Third barrel for value
    },
    
    SpotCategory.CHECK_CALL: {
        "thin": 0.40,          # Thin value bet
        "bluff": 0.10,         # Bluff catch
        "inducing": 0.60,      # Check to induce bluffs
    },
    
    SpotCategory.DONK_BET: {
        "value": 0.20,         # Donk for value
        "bluff": 0.05,         # Donk as bluff
    },
    
    SpotCategory.HERO_3BET: {
        "call_3bet": 0.30,     # Call 3bet preflop
        "call_open": 0.45,     # Call open raise
    },
}


def classify_board_texture(board_str: str) -> BoardTexture:
    """
    Classify board texture based on board cards.
    
    Args:
        board_str: Board cards as string (e.g., 'Kd7h2c' for flop)
        
    Returns:
        BoardTexture enum value
    """
    if not board_str or len(board_str) < 6:
        return BoardTexture.COORDINATED  # Default
    
    # Extract flop cards (first 3 cards)
    flop = board_str[:6]  # e.g., "Kd7h2c"
    cards = [flop[i:i+2] for i in range(0, 6, 2)]
    
    if len(cards) < 3:
        return BoardTexture.COORDINATED
    
    # Parse ranks
    ranks = []
    suits = []
    for card in cards:
        if len(card) == 2:
            ranks.append(card[0])
            suits.append(card[1])
    
    # Check for monotone
    if len(set(suits)) == 1:
        return BoardTexture.DRY_MONO
    
    # Check for pairs
    if len(set(ranks)) < 3:
        return BoardTexture.WET_PAIRS
    
    # Check for high cards (A, K, Q, J, T)
    high_ranks = set('AKQJT')
    high_count = sum(1 for r in ranks if r in high_ranks)
    if high_count >= 2:
        return BoardTexture.HIGH_CARDS
    
    # Check for coordinated (8-T range with connectors)
    coord_ranks = set('89TJQKA')
    coord_count = sum(1 for r in ranks if r in coord_ranks)
    if coord_count >= 2:
        return BoardTexture.COORDINATED
    
    return BoardTexture.LOW_CARDS


def get_position_name(position_idx: int, players: int = 2) -> str:
    """Convert position index to position name."""
    if players == 2:
        positions = {0: "BTN", 1: "BB"}
    elif players == 6:
        positions = {0: "BTN", 1: "SB", 2: "BB", 3: "UTG", 4: "MP", 5: "CO"}
    else:
        positions = {0: "BTN", 1: "SB", 2: "BB", 3: "UTG", 4: "MP", 5: "CO", 6: "UTG+1", 7: "UTG+2"}
    
    return positions.get(position_idx, f"POS{position_idx}")


def determine_spot_category(
    street: str,
    board: str,
    position: str,
    pot_size: float,
    stack_depth: int,
    action_history: List[Dict[str, Any]],
    is_oop: bool,
) -> SpotCategory:
    """
    Determine the spot category based on action sequence.
    
    Args:
        street: Current street (preflop, flop, turn, river)
        board: Board cards
        position: Player position
        pot_size: Current pot size
        stack_depth: Stack depth in big blinds
        action_history: Previous actions in the hand
        is_oop: Whether player is out of position
        
    Returns:
        SpotCategory enum value
    """
    # Simple heuristic based on street and position
    if street == "flop":
        if len(action_history) > 0 and action_history[-1].get("action") == "check":
            if is_oop:
                return SpotCategory.CHECK_RAISE_FLOP
            return SpotCategory.DELAY_CBET
        elif len(action_history) == 0:
            return SpotCategory.CBET_FLOP
        elif len(action_history) > 0 and action_history[-1].get("action") == "donk":
            return SpotCategory.DONK_BET
        return SpotCategory.CBET_FLOP
    
    elif street == "turn":
        if len(action_history) > 0 and action_history[-1].get("action") in ("bet", "cbet"):
            return SpotCategory.BARREL_TURN
        return SpotCategory.CHECK_CALL
    
    elif street == "river":
        if len(action_history) > 0 and action_history[-1].get("action") == "barrel":
            return SpotCategory.THIRD_BARREL
        return SpotCategory.LEAD_RIVER
    
    return SpotCategory.HERO_3BET


def normalize_action(action: str) -> str:
    """Normalize action strings to standard format."""
    action = action.lower().strip()
    
    if action in ("bet", "c bet", "c-bet", "continuation"):
        return "bet"
    elif action in ("raise", "re-raise", "reraise"):
        return "raise"
    elif action in ("call", "cold call", "flat"):
        return "call"
    elif action in ("check", "x", "ch"):
        return "check"
    elif action in ("fold", "f", "fd"):
        return "fold"
    elif action in ("allin", "all-in", "shove", "jam"):
        return "allin"
    
    return action


def calculate_ev_loss(
    user_action: str,
    gto_action: str,
    gto_frequency: float,
    pot_size: float,
    stack_depth: int,
) -> float:
    """
    Calculate EV loss from deviating from GTO.
    
    Args:
        user_action: User's actual action
        gto_action: GTO recommended action
        gto_frequency: GTO action frequency for this spot
        pot_size: Current pot size in chips
        stack_depth: Stack depth in big blinds
        
    Returns:
        Estimated EV loss in big blinds
    """
    if user_action == gto_action:
        return 0.0
    
    # Simple EV estimation based on action frequency deviation
    # Assuming pot-sized bets for simplicity
    bet_size = pot_size * 0.67  # 2/3 pot typical bet size
    
    # Calculate frequency deviation
    # If GTO bets 70% and user bets 30%, major leak
    if gto_action == "bet" and user_action == "check":
        # Missing a c-bet opportunity
        freq_diff = gto_frequency - 0.0  # User never bets
        ev_loss = freq_diff * bet_size / stack_depth * 0.5  # Rough estimate
        return round(ev_loss, 3)
    
    elif gto_action == "check" and user_action == "bet":
        # Betting when GTO checks
        freq_diff = (1.0 - gto_frequency) - gto_frequency  # How much over GTO
        ev_loss = freq_diff * bet_size / stack_depth * 0.3
        return round(ev_loss, 3)
    
    elif gto_action == "raise" and user_action == "call":
        # Calling instead of raising with value
        ev_loss = 0.5 * bet_size / stack_depth
        return round(ev_loss, 3)
    
    elif gto_action == "call" and user_action == "fold":
        # Folding when GTO calls (missing equity)
        ev_loss = 0.3 * bet_size / stack_depth
        return round(ev_loss, 3)
    
    elif gto_action == "fold" and user_action == "call":
        # Calling with weak hand GTO would fold
        ev_loss = 0.4 * bet_size / stack_depth
        return round(ev_loss, 3)
    
    # Generic deviation cost
    return 0.1


def generate_recommendation(
    user_action: str,
    gto_action: str,
    gto_frequency: float,
    spot_category: SpotCategory,
    board_texture: BoardTexture,
    pot_size: float,
) -> str:
    """Generate actionable recommendation text."""
    pot_bb = round(pot_size / 100, 1)  # Convert to BB estimate
    
    if user_action == gto_action:
        return f"Your action aligns with GTO ({gto_frequency:.0%} frequency in this spot)."
    
    user_norm = normalize_action(user_action)
    gto_norm = normalize_action(gto_action)
    
    if gto_norm == "bet" and user_norm == "check":
        bet_size = round(pot_bb * 0.67, 1)
        return (
            f"You checked instead of betting ~{bet_size}BB ({gto_frequency:.0%} GTO c-bet frequency "
            f"on {board_texture.value} boards). Consider betting for value with strong hands "
            f"or as a bluff with air."
        )
    
    elif gto_norm == "check" and user_norm == "bet":
        return (
            f"You bet but GTO checks {gto_frequency:.0%} of the time in this spot. "
            f"Consider checking to realize equity with medium strength hands."
        )
    
    elif gto_norm == "raise" and user_norm == "call":
        return (
            f"You called but GTO raises {gto_frequency:.0%} of the time. "
            f"With strong hands, raising is more profitable for value extraction."
        )
    
    elif gto_norm == "call" and user_norm == "fold":
        return (
            f"You folded but GTO calls {gto_frequency:.0%} of the time. "
            f"Review if you have enough equity to continue - you may be folding too often."
        )
    
    elif gto_norm == "fold" and user_norm == "call":
        return (
            f"You called with a weak hand but GTO folds {gto_frequency:.0%} of the time. "
            f"Consider folding to avoid leaking chips."
        )
    
    return (
        f"Your action ({user_action}) deviates from GTO baseline. "
        f"GTO prefers {gto_action} at {gto_frequency:.0%} frequency in this spot."
    )


def determine_severity(ev_loss: float) -> str:
    """Determine leak severity based on EV loss."""
    if ev_loss >= 0.5:
        return "high"
    elif ev_loss >= 0.2:
        return "medium"
    return "low"


async def compare_to_gto(
    hand_parsed: Any,
    hero_name: Optional[str] = None,
) -> List[GTOComparisonResult]:
    """
    Compare a parsed hand against GTO baselines to identify leaks.
    
    Args:
        hand_parsed: ParsedHand object from hand_history parser
        hero_name: Optional hero name override (uses parsed hero if not provided)
        
    Returns:
        List of GTOComparisonResult with identified leaks and recommendations
    """
    if hero_name is None:
        hero_name = hand_parsed.hero_name()
    
    if hero_name is None:
        logger.warning("No hero name found in hand, cannot compare to GTO")
        return []
    
    results: List[GTOComparisonResult] = []
    
    # Get hero player
    hero_player = None
    for player in hand_parsed.players:
        if player.name == hero_name:
            hero_player = player
            break
    
    if hero_player is None:
        logger.warning(f"Hero player '{hero_name}' not found in hand")
        return []
    
    # Get position index
    position_idx = 0
    position_map = {"BTN": 0, "SB": 1, "BB": 2, "UTG": 3, "CO": 5, "MP": 4}
    position_idx = position_map.get(hero_player.position, 0)
    
    # Determine if hero is OOP
    # For simplicity: BB vs BTN is OOP, BTN vs BB is IP
    is_oop = (position_idx == 2)  # BB is OOP vs BTN
    
    # Build action history for hero
    hero_actions = []
    for action in hand_parsed.actions:
        if action.player == hero_name:
            hero_actions.append({
                "action": normalize_action(action.action_type.value if hasattr(action.action_type, 'value') else str(action.action_type)),
                "street": action.street,
                "amount": action.amount,
            })
    
    # Process each street
    street_actions = {"flop": [], "turn": [], "river": []}
    for action in hero_actions:
        if action["street"] in street_actions:
            street_actions[action["street"]].append(action)
    
    # Get board string
    board_str = ""
    if hand_parsed.board.flop:
        board_str = "".join(hand_parsed.board.flop)
        if hand_parsed.board.turn:
            board_str += hand_parsed.board.turn
        if hand_parsed.board.river:
            board_str += hand_parsed.board.river
    
    # Analyze each street
    for street, actions in street_actions.items():
        if not actions:
            continue
        
        if street == "flop":
            board_texture = classify_board_texture(board_str)
        else:
            # For turn/river, use full board
            board_texture = classify_board_texture(board_str)
        
        for action in actions:
            user_action = action["action"]
            
            # Determine spot category
            action_history = []
            for a in hero_actions:
                if a["street"] == street:
                    action_history.append(a)
            
            spot_cat = determine_spot_category(
                street=street,
                board=board_str,
                position=hero_player.position,
                pot_size=hand_parsed.pot,
                stack_depth=int(hero_player.stack / 100),  # Assuming 100bb = 10000 chips
                action_history=action_history,
                is_oop=is_oop,
            )
            
            # Get GTO baseline
            baseline = GTO_BASELINE.get(spot_cat, {})
            
            if not baseline:
                continue
            
            # Determine GTO recommended action (highest frequency)
            gto_action = max(baseline.keys(), key=lambda k: baseline[k])
            gto_freq = baseline[gto_action]
            
            # Calculate EV loss
            ev_loss = calculate_ev_loss(
                user_action=user_action,
                gto_action=gto_action,
                gto_frequency=gto_freq,
                pot_size=hand_parsed.pot,
                stack_depth=int(hero_player.stack / 100),
            )
            
            # Generate recommendation
            recommendation = generate_recommendation(
                user_action=user_action,
                gto_action=gto_action,
                gto_frequency=gto_freq,
                spot_category=spot_cat,
                board_texture=board_texture,
                pot_size=hand_parsed.pot,
            )
            
            # Only include if there's meaningful deviation
            if ev_loss > 0.01:
                results.append(GTOComparisonResult(
                    spot_category=spot_cat.value,
                    ev_loss=ev_loss,
                    gto_action=gto_action,
                    gto_frequency=gto_freq,
                    user_action=user_action,
                    user_frequency=0.0,  # User frequency not tracked
                    recommendation=recommendation,
                    severity=determine_severity(ev_loss),
                    board_texture=board_texture.value,
                    position=hero_player.position,
                    pot_size=hand_parsed.pot,
                ))
    
    return results


async def get_gto_strategy_for_spot(
    street: str,
    board_hash: str,
    bet_size: float,
    stack_depth: int,
) -> Optional[Dict[str, Any]]:
    """
    Retrieve stored GTO strategy for a specific spot from database.
    
    Args:
        street: Street (preflop, flop, turn, river)
        board_hash: Board hash or empty for preflop
        bet_size: Bet size as fraction of pot
        stack_depth: Stack depth in big blinds
        
    Returns:
        Strategy data dict or None if not found
    """
    try:
        storage = await get_strategy_storage()
        strategy = await storage.get_strategy_by_params(
            street=street,
            board_hash=board_hash,
            bet_size=bet_size,
            stack_depth=stack_depth,
            game_type="nlh",
            players=2,
        )
        
        if strategy:
            return strategy.strategy_data
        
        return None
    except Exception as e:
        logger.warning(f"Could not retrieve GTO strategy: {e}")
        return None


def summarize_leaks(leaks: List[GTOComparisonResult]) -> Dict[str, Any]:
    """
    Summarize identified leaks for an entire hand.
    
    Args:
        leaks: List of GTOComparisonResult from compare_to_gto
        
    Returns:
        Summary dict with total EV loss and categorized leaks
    """
    if not leaks:
        return {
            "total_ev_loss": 0.0,
            "leak_count": 0,
            "high_severity": [],
            "medium_severity": [],
            "low_severity": [],
            "summary": "No significant GTO leaks detected.",
        }
    
    total_ev_loss = sum(l.ev_loss for l in leaks)
    
    high = [l for l in leaks if l.severity == "high"]
    medium = [l for l in leaks if l.severity == "medium"]
    low = [l for l in leaks if l.severity == "low"]
    
    return {
        "total_ev_loss": round(total_ev_loss, 3),
        "leak_count": len(leaks),
        "high_severity": high,
        "medium_severity": medium,
        "low_severity": low,
        "summary": f"Found {len(leaks)} leaks with total EV loss of {total_ev_loss:.3f} BB. "
                   f"{len(high)} high, {len(medium)} medium, {len(low)} low severity.",
    }
