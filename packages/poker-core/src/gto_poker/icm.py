"""ICM (Independent Chip Model) calculator with Malmoud-Harville equity and bubble factor."""

from dataclasses import dataclass
from typing import Optional



@dataclass
class ICMResult:
    """Result of ICM calculation for a player."""
    player: str
    equity: float  # Total equity in currency
    chip_equity: float  # Equity based on chip count only
    bubble_factor: float  # Bubble factor multiplier
    ev: float  # Expected value
    street: Optional[str] = None  # Tournament street (e.g., "final", "FT")


def malmoud_harville(
    stacks: list[float],
    prizes: list[float],
    n_simulations: int = 100_000,
    seed: Optional[int] = None,
) -> list[float]:
    """Calculate equities using Malmoud-Harville formula for handling ties.
    
    This computes the probability of each player finishing in each place,
    accounting for the mathematical reality of tie situations in tournaments.
    
    Args:
        stacks: List of chip stacks for each player.
        prizes: List of prize amounts for each place (index = place - 1).
        n_simulations: Number of Monte Carlo simulations to run.
        seed: Optional random seed for reproducibility.
    
    Returns:
        List of expected values, one per player.
    """
    import random
    
    n = len(stacks)
    if n != len(prizes):
        raise ValueError("Number of stacks and prizes must match")
    
    if n == 0 or len(prizes) == 0:
        return []
    
    # Standardize: total chips = 1.0 for easier calculation
    total_chips = sum(stacks)
    if total_chips == 0:
        return [0.0] * n
    
    normalized_stacks = [s / total_chips for s in stacks]
    
    # Initialize equity accumulator
    equities = [0.0] * n
    
    random.seed(seed)
    
    for _ in range(n_simulations):
        # Generate random final stacks using Dirichlet distribution
        # Each player's "performance" is proportional to their stack
        performances = [
            random.gammavariate(s * 1000 + 1, 1) if s > 0 else 0.001
            for s in normalized_stacks
        ]
        
        # Rank players by performance
        ranked = sorted(enumerate(performances), key=lambda x: -x[1])
        
        # Track ties and distribute places
        i = 0
        while i < n:
            current_perf = ranked[i][1]
            tie_group = [(player, perf) for player, perf in ranked[i:] 
                        if abs(perf - current_perf) < 1e-9]
            
            # Calculate average prize for the tie group
            places = [player for player, _ in tie_group]
            n_ties = len(places)
            
            for player_idx in places:
                # Malmoud-Harville: share the average of all places in the tie
                avg_prize = sum(prizes[rank] for rank in range(i, min(i + n_ties, len(prizes)))) / n_ties
                equities[player_idx] += avg_prize
            
            i += n_ties
    
    # Normalize by number of simulations
    return [eq / n_simulations for eq in equities]


def calculate_bubble_factor(
    stacks: list[float],
    prizes: list[float],
    player_idx: int,
    n_simulations: int = 100_000,
    seed: Optional[int] = None,
) -> float:
    """Calculate the bubble factor for a specific player.
    
    The bubble factor represents how much more valuable each chip is
    compared to raw chip equity, due to the nonlinear value of chips
    in a tournament (the "bubble effect").
    
    Args:
        stacks: List of chip stacks for each player.
        prizes: List of prize amounts for each place (index = place - 1).
        player_idx: Index of the player to calculate bubble factor for.
        n_simulations: Number of Monte Carlo simulations.
        seed: Optional random seed.
    
    Returns:
        Bubble factor for the player (>1.0 means chips are more valuable,
        <1.0 means chips are less valuable than their raw value).
    """
    if player_idx < 0 or player_idx >= len(stacks):
        raise ValueError("Invalid player index")
    
    total_chips = sum(stacks)
    if total_chips == 0:
        return 1.0
    
    my_chips = stacks[player_idx]
    my_share = my_chips / total_chips
    
    # Calculate raw chip equity (what 1 chip is worth)
    raw_chip_ev = my_share * sum(prizes)
    
    if raw_chip_ev == 0:
        return 1.0
    
    # Calculate actual ICM equity
    icm_equities = malmoud_harville(stacks, prizes, n_simulations, seed)
    my_icm_ev = icm_equities[player_idx]
    
    # Bubble factor = ICM EV / raw chip EV
    return my_icm_ev / raw_chip_ev if raw_chip_ev > 0 else 1.0


def icm_calculate(
    stacks: list[float],
    prizes: list[float],
    players: list[str],
    n_simulations: int = 100_000,
    seed: Optional[int] = None,
) -> list[ICMResult]:
    """Calculate ICM equity for all players.
    
    Uses the Malmoud-Harville method for equity calculation and
    computes bubble factors for each player.
    
    Args:
        stacks: List of chip stacks (one per player).
        prizes: List of prize amounts for each finishing place.
                Index 0 = 1st place prize, index 1 = 2nd place prize, etc.
        players: List of player names (for identification in results).
        n_simulations: Number of Monte Carlo simulations to run.
        seed: Optional random seed for reproducibility.
    
    Returns:
        List of ICMResult objects, one per player.
    
    Example:
        >>> stacks = [10000, 10000, 5000]  # 3 players
        >>> prizes = [100, 50, 0]  # 1st gets 100, 2nd gets 50
        >>> players = ["Alice", "Bob", "Charlie"]
        >>> results = icm_calculate(stacks, prizes, players)
        >>> for r in results:
        ...     print(f"{r.player}: ${r.equity:.2f} (bubble: {r.bubble_factor:.3f})")
    """
    n = len(stacks)
    
    if n != len(prizes):
        # Extend prizes list if needed
        prizes = list(prizes) + [0.0] * (n - len(prizes))
    
    # Get ICM equities via Malmoud-Harville
    equities = malmoud_harville(stacks, prizes, n_simulations, seed)
    
    # Calculate raw chip equity for comparison
    total_chips = sum(stacks)
    total_prize = sum(prizes)
    
    results = []
    for i, player in enumerate(players):
        stack = stacks[i]
        icm_ev = equities[i]
        
        # Raw chip equity = stack_share * total_prize_pool
        chip_share = (stack / total_chips) if total_chips > 0 else 0.0
        chip_ev = chip_share * total_prize
        
        # Bubble factor
        bubble_factor = calculate_bubble_factor(
            stacks, prizes, i, n_simulations, seed
        )
        
        results.append(ICMResult(
            player=player,
            equity=icm_ev,
            chip_equity=chip_ev,
            bubble_factor=bubble_factor,
            ev=icm_ev,
        ))
    
    return results


def icm_equity_chips(stacks: list[float], total_chips: float) -> list[float]:
    """Calculate simple chip equity (no tournament model).
    
    This is the baseline equity calculation assuming chips are
    worth their face value (1 chip = 1 unit).
    
    Args:
        stacks: List of chip stacks.
        total_chips: Total chips in play.
    
    Returns:
        List of raw chip equities.
    """
    if total_chips <= 0:
        return [0.0] * len(stacks)
    
    return [stack / total_chips for stack in stacks]


def _normalize_boxes(
    stacks: list[float],
) -> list[tuple[float, float]]:
    """Pair adjacent stacks and normalize to (box, total) tuples.
    
    For bubble factor calculation, we analyze the game as a series
    of heads-up matchups ("boxes").
    """
    result = []
    sorted_stacks = sorted(enumerate(stacks), key=lambda x: -x[1])
    
    for i in range(0, len(sorted_stacks) - 1, 2):
        a_idx, a_stack = sorted_stacks[i]
        b_idx, b_stack = sorted_stacks[i + 1]
        total = a_stack + b_stack
        result.append((a_stack / total, total))
    
    if len(sorted_stacks) % 2 == 1:
        # Odd player out - handled separately
        last_idx, last_stack = sorted_stacks[-1]
        result.append((1.0, last_stack))
    
    return result




def get_standard_prizes(n_players: int, total_prize: float = 1.0) -> list[float]:
    """Get standard tournament prize distribution.
    
    Args:
        n_players: Number of players in tournament.
        total_prize: Total prize pool (default 1.0 for normalized).
    
    Returns:
        List of prize amounts for each place (index 0 = 1st place).
    
    Example:
        >>> get_standard_prizes(10)
        [0.5, 0.3, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    """
    if n_players <= 0:
        return []
    
    # Standard payout structure: ~50%/30%/20% for top 3
    if n_players <= 3:
        # 1st: 50%, 2nd: 30%, 3rd: 20%
        prizes = [0.5, 0.3, 0.2][:n_players]
    elif n_players <= 10:
        # Top 3 get paid: 50%/30%/20%
        prizes = [0.5, 0.3, 0.2] + [0.0] * (n_players - 3)
    elif n_players <= 30:
        # Top 4 get paid: 40%/25%/20%/15%
        prizes = [0.4, 0.25, 0.20, 0.15] + [0.0] * (n_players - 4)
    else:
        # Typical big field: Top 9 paid - 30%/20%/15%/10%/7%/5%/3%/2%/1%
        top_prizes = [0.30, 0.20, 0.15, 0.10, 0.07, 0.05, 0.03, 0.02, 0.01]
        prizes = top_prizes + [0.0] * (n_players - len(top_prizes))
    
    # Normalize to total_prize
    total = sum(prizes)
    if total > 0:
        prizes = [p * total_prize / total for p in prizes]
    
    return prizes


def icm_for_push_fold(
    stacks: list[float],
    prizes: list[float],
    n_simulations: int = 100_000,
    seed: Optional[int] = None,
) -> dict:
    """Calculate ICM data specifically for push/fold analysis.
    
    Args:
        stacks: List of chip stacks for each player.
        prizes: List of prize amounts for each place.
        n_simulations: Number of Monte Carlo simulations.
        seed: Optional random seed for reproducibility.
    
    Returns:
        Dict with keys:
            - equities: List of ICM equities for each player
            - chip_equities: List of raw chip equities
            - bubble_factors: List of bubble factors
    """
    n = len(stacks)
    
    if n != len(prizes):
        prizes = list(prizes) + [0.0] * (n - len(prizes))
    
    # Calculate ICM equities
    icm_equities = malmoud_harville(stacks, prizes, n_simulations, seed)
    
    # Calculate chip equities (simple proportional)
    total_chips = sum(stacks) if sum(stacks) > 0 else 1
    total_prize = sum(prizes)
    chip_equities = [s / total_chips * total_prize for s in stacks]
    
    # Calculate bubble factors
    bubble_factors = []
    for i in range(n):
        if chip_equities[i] > 0:
            bf = icm_equities[i] / chip_equities[i]
        else:
            bf = 1.0
        bubble_factors.append(bf)
    
    return {
        "equities": icm_equities,
        "chip_equities": chip_equities,
        "bubble_factors": bubble_factors,
    }


__all__ = [
    "ICMResult",
    "malmoud_harville",
    "calculate_bubble_factor",
    "icm_calculate",
    "icm_equity_chips",
    "get_standard_prizes",
    "icm_for_push_fold",
]
