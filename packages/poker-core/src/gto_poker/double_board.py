"""Double Board PLO — novel poker variant with two independent boards.

Two boards are dealt at showdown. Player scoops if they win BOTH boards.
Chops if they win one, loses both if they lose both.

Scoring: adjusted_equity = (scoop_wins × 1.0 + chop_wins × 0.5) / total_sims

This is a novel variant — no existing open-source reference.
"""
from typing import List, Tuple, Optional
from dataclasses import dataclass
import random
import sys

# Import PLO4 evaluator for board evaluation
sys.path.insert(0, "/tmp/PokerHandEvaluator/python")
from phevaluator.evaluator import evaluate_cards

from .deck import RANKS, SUITS


@dataclass
class ScoopTracker:
    """Tracks scoop/chop results across simulations."""
    total_sims: int = 0
    scoop_wins: int = 0
    chop_wins: int = 0
    scoop_losses: int = 0

    @property
    def adjusted_equity(self) -> float:
        """Calculate adjusted equity using scoop/chop formula."""
        if self.total_sims == 0:
            return 0.0
        return (self.scoop_wins * 1.0 + self.chop_wins * 0.5) / self.total_sims

    def record(self, player1_wins_board1: bool, player1_wins_board2: bool, tie_b1: bool = False, tie_b2: bool = False):
        """Record result of a single simulation."""
        self.total_sims += 1

        # Determine scoop/chop/loss for player1
        if player1_wins_board1 and player1_wins_board2:
            # Won both boards — scoop
            self.scoop_wins += 1
        elif tie_b1 and tie_b2:
            # Tied both boards — chop (both get 0.5)
            self.chop_wins += 1
        elif (player1_wins_board1 and tie_b2) or (tie_b1 and player1_wins_board2):
            # Won one, tied one — chop
            self.chop_wins += 1
        elif player1_wins_board1 == (not player1_wins_board2) and not (tie_b1 or tie_b2):
            # Won one, lost one (no ties) — chop
            self.chop_wins += 1
        else:
            # Lost both boards
            self.scoop_losses += 1


class DoubleBoardEvaluator:
    """Evaluate a PLO4 hand on two independent boards.

    In PLO4, player must use exactly 2 of their 4 hole cards + 3 board cards.
    We evaluate best 2-of-4 + best 3-of-5 for each board independently.
    """

    def __init__(self, seed: Optional[int] = None):
        self._cache = {}
        self._random = random.Random(seed)

    def _fill_board(self, board: List[str], remaining: List[str]) -> List[str]:
        """Fill a board to 5 cards by drawing from remaining deck."""
        result = board.copy()
        while len(result) < 5 and remaining:
            result.append(remaining.pop())
        return result

    def evaluate(self, hole: List[str], board1: List[str], board2: List[str]) -> Tuple[int, int]:
        """
        Evaluate a hand on two boards.

        Args:
            hole: 4 hole cards
            board1: 0-5 cards for board 1 (uses remaining if <5)
            board2: 0-5 cards for board 2 (uses remaining if <5)

        Returns:
            Tuple of (rank1, rank2) — lower is better
        """
        if len(hole) != 4:
            raise ValueError(f"Need exactly 4 hole cards, got {len(hole)}")

        # Ensure no card overlap between boards
        h1_set = set(board1)
        h2_set = set(board2)
        overlap = h1_set & h2_set
        if overlap:
            raise ValueError(f"Board 1 and Board 2 share cards: {overlap}")

        # Ensure hole cards don't overlap with boards
        hole_set = set(hole)
        b1_intersection = hole_set & h1_set
        b2_intersection = hole_set & h2_set
        if b1_intersection:
            raise ValueError(f"Hole cards overlap with board 1: {b1_intersection}")
        if b2_intersection:
            raise ValueError(f"Hole cards overlap with board 2: {b2_intersection}")

        # Build remaining deck excluding known cards
        used = set(hole + board1 + board2)
        remaining = []
        for r in RANKS:
            for s in SUITS:
                c = r + s
                if c not in used:
                    remaining.append(c)

        self._random.shuffle(remaining)

        b1 = self._fill_board(board1, remaining)
        b2 = self._fill_board(board2, remaining)

        rank1 = self._evaluate_single_board(hole, b1)
        rank2 = self._evaluate_single_board(hole, b2)

        return rank1, rank2

    def _evaluate_single_board(self, hole: List[str], board: List[str]) -> int:
        """Evaluate best 2-hole + 3-board combo. Lower rank = better hand."""
        from itertools import combinations

        best_rank = 999999

        # C(4,2) = 6 ways to choose 2 hole cards
        # C(5,3) = 10 ways to choose 3 board cards
        for hole_combo in combinations(hole, 2):
            for board_combo in combinations(board, 3):
                rank = evaluate_cards(*hole_combo, *board_combo)
                if rank < best_rank:
                    best_rank = rank

        return best_rank

    def evaluate_showdown(
        self,
        hands: List[List[str]],
        board1: List[str],
        board2: List[str]
    ) -> List[float]:
        """
        Evaluate showdown for multiple players on two boards.

        Args:
            hands: List of 4-card hands
            board1: 5-card board 1
            board2: 5-card board 2

        Returns:
            List of adjusted equities (0-1) for each player
        """

        n = len(hands)
        ranks1 = [self._evaluate_single_board(h, board1) for h in hands]
        ranks2 = [self._evaluate_single_board(h, board2) for h in hands]

        # Find best rank on each board
        best_rank1 = min(ranks1)
        best_rank2 = min(ranks2)

        tracker = ScoopTracker(total_sims=1)

        for i in range(n):
            # Determine if player i scooped, chopped, or lost
            p1_wins_b1 = ranks1[i] < best_rank1
            p1_wins_b2 = ranks2[i] < best_rank2
            tie_b1 = ranks1[i] == best_rank1 and sum(1 for r in ranks1 if r == best_rank1) > 1
            tie_b2 = ranks2[i] == best_rank2 and sum(1 for r in ranks2 if r == best_rank2) > 1

            tracker.record(p1_wins_b1, p1_wins_b2, tie_b1, tie_b2)

        # Return each player's share based on scoop/chop
        equities = []
        for i in range(n):
            # Recalculate for each player as "player 1"
            p_wins_b1 = ranks1[i] < best_rank1
            p_wins_b2 = ranks2[i] < best_rank2
            tie_b1 = ranks1[i] == best_rank1 and sum(1 for r in ranks1 if r == best_rank1) > 1
            tie_b2 = ranks2[i] == best_rank2 and sum(1 for r in ranks2 if r == best_rank2) > 1

            # Player's adjusted equity
            if p_wins_b1 and p_wins_b2:
                player_eq = 1.0 / sum(1 for j in range(n) if ranks1[j] < best_rank1 and ranks2[j] < best_rank2)
            elif tie_b1 and tie_b2:
                player_eq = 0.5 / sum(1 for j in range(n) if ranks1[j] == best_rank1 and ranks2[j] == best_rank2)
            elif p_wins_b1 or p_wins_b2:
                player_eq = 0.5
            else:
                player_eq = 0.0

            equities.append(player_eq)

        return equities


class DoubleBoardEquity:
    """Calculate double board PLO equity using Monte Carlo or exact enumeration."""

    def __init__(self, seed: Optional[int] = None):
        self._eval = DoubleBoardEvaluator()
        self._random = random.Random(seed)

    def calculate(
        self,
        hand1: List[str],
        hand2: List[str],
        board1: List[str],
        board2: List[str],
        samples: int = 10000,
    ) -> Tuple[float, float, ScoopTracker]:
        """
        Calculate adjusted equity for two players.

        Args:
            hand1: Player 1's 4 hole cards
            hand2: Player 2's 4 hole cards
            board1: Known board1 cards (0-5)
            board2: Known board2 cards (0-5)
            samples: Monte Carlo samples (0 = exact if both boards complete)

        Returns:
            Tuple of (equity1, equity2, scoop_tracker)
        """
        if len(board1) == 5 and len(board2) == 5 and samples == 0:
            return self._exact_equity(hand1, hand2, board1, board2)

        return self._monte_carlo(hand1, hand2, board1, board2, samples)

    def _exact_equity(
        self,
        hand1: List[str],
        hand2: List[str],
        board1: List[str],
        board2: List[str],
    ) -> Tuple[float, float, ScoopTracker]:
        """Exact equity when both boards are complete (5 cards each)."""

        # Each player has C(4,2)*C(5,3) = 60 combos per board
        # For showdown, we need the best combo for each player on each board

        tracker = ScoopTracker(total_sims=1)

        # Evaluate best hand on each board for each player
        rank1_p1 = self._eval._evaluate_single_board(hand1, board1)
        rank1_p2 = self._eval._evaluate_single_board(hand2, board1)
        rank2_p1 = self._eval._evaluate_single_board(hand1, board2)
        rank2_p2 = self._eval._evaluate_single_board(hand2, board2)

        # Determine scoop/chop
        p1_wins_b1 = rank1_p1 < rank1_p2
        p1_wins_b2 = rank2_p1 < rank2_p2
        tie_b1 = rank1_p1 == rank1_p2
        tie_b2 = rank2_p1 == rank2_p2

        tracker.record(p1_wins_b1, p1_wins_b2, tie_b1, tie_b2)

        eq1 = tracker.adjusted_equity
        eq2 = 1.0 - eq1 if tracker.scoop_losses == 0 else 0.5 - tracker.adjusted_equity * 0.5 + tracker.scoop_losses / tracker.total_sims * 0.5

        # Recalculate properly
        if p1_wins_b1 and p1_wins_b2:
            eq1 = 1.0
            eq2 = 0.0
        elif tie_b1 and tie_b2:
            eq1 = 0.5
            eq2 = 0.5
        elif p1_wins_b1 or p1_wins_b2:
            eq1 = 0.5
            eq2 = 0.5
        else:
            eq1 = 0.0
            eq2 = 1.0

        return eq1, eq2, tracker

    def _monte_carlo(
        self,
        hand1: List[str],
        hand2: List[str],
        board1: List[str],
        board2: List[str],
        samples: int,
    ) -> Tuple[float, float, ScoopTracker]:
        """Monte Carlo simulation for equity estimation."""
        tracker = ScoopTracker()

        # Build remaining deck
        used = set(hand1 + hand2 + board1 + board2)
        deck = [r + s for r in RANKS for s in SUITS if r + s not in used]

        for _ in range(samples):
            self._random.shuffle(deck)

            # Complete boards
            b1 = board1 + deck[:5 - len(board1)]
            b2 = board2 + deck[5 - len(board1):5 - len(board1) + (5 - len(board2))]

            # Evaluate
            rank1_p1 = self._eval._evaluate_single_board(hand1, b1)
            rank1_p2 = self._eval._evaluate_single_board(hand2, b1)
            rank2_p1 = self._eval._evaluate_single_board(hand1, b2)
            rank2_p2 = self._eval._evaluate_single_board(hand2, b2)

            # Check ties
            tie_b1 = rank1_p1 == rank1_p2
            tie_b2 = rank2_p1 == rank2_p2

            # Player 1 perspective
            p1_wins_b1 = rank1_p1 < rank1_p2
            p1_wins_b2 = rank2_p1 < rank2_p2

            tracker.record(p1_wins_b1, p1_wins_b2, tie_b1, tie_b2)

        eq1 = tracker.adjusted_equity
        eq2 = 1.0 - eq1

        return eq1, eq2, tracker


__all__ = ["DoubleBoardEvaluator", "DoubleBoardEquity", "ScoopTracker"]


# Convenience function for CI/compatibility
def simulate_double_board(hand1, hand2, board1, board2, samples=10000, seed=None):
    """Simulate double board equity — convenience wrapper around DoubleBoardEquity."""
    dbe = DoubleBoardEquity(seed=seed)
    eq1, eq2, tracker = dbe.calculate(hand1, hand2, board1, board2, samples)
    return eq1, eq2, tracker