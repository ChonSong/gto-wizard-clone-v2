"""PLO4 (Pot-Limit Omaha 4-card) hand evaluation module

Uses HenryRLee/PokerHandEvaluator under the hood. In PLO4, players receive
4 hole cards and must use exactly 2 of them combined with exactly 3 board
cards to make the best 5-card poker hand.
"""
from typing import List, Tuple, Optional
from itertools import combinations

# phevaluator: HenryRLee/PokerHandEvaluator (pure Python implementation)
from phevaluator.evaluator import evaluate_cards

from .deck import RANKS, SUITS


def plo4_hand_rank_to_percentage(rank: int, total: int = 7462) -> float:
    """
    Convert a hand rank to a percentage (0-100).
    
    In 7-card poker there are 7462 distinct hand ranks (Cactus Kev's system).
    A rank of 1 is the best (royal flush), 7462 is the worst (high card).
    
    Args:
        rank: Hand rank from evaluate_cards (lower is better)
        total: Total possible hand ranks (7462 for 7-card)
    
    Returns:
        Percentage from 0 (best) to 100 (worst)
    """
    return (rank / total) * 100


class PLO4Evaluator:
    """
    Wrapper for evaluating PLO4 (4-card Omaha) hands.
    
    In PLO4:
    - Each player receives 4 hole cards
    - Board has 5 cards
    - Player must use exactly 2 hole cards + 3 board cards
    - There are 60 combinations (C(4,2) * C(5,3)) to evaluate
    """
    
    def __init__(self):
        self._cache = {}
    
    def evaluate(self, *cards) -> int:
        """
        Evaluate a PLO4 hand.
        
        Args:
            *cards: 9 cards total as separate arguments OR 
                    a single string like "AhKhQhJhTc9c8c7c6c"
                    OR hole cards as first arg + board as second (both lists/strings)
        
        Returns:
            Hand rank (lower is better, 1 = best)
        """
        # Handle string input
        if len(cards) == 1 and isinstance(cards[0], str):
            cards = self._parse_hand_string(cards[0])
            if len(cards) == 9:
                hole = cards[:4]
                board = cards[4:]
                return self._evaluate(hole, board)
        
        # Handle case where args are all card strings
        if all(isinstance(c, str) for c in cards):
            parsed = []
            for c in cards:
                if len(c) == 2:
                    parsed.append(c.upper())
                elif len(c) > 2:
                    # It's a combined string like 'AhAsKsKc'
                    parsed.extend(self._parse_hand_string(c))
                else:
                    parsed.append(c.upper())
            cards = parsed
        
        if len(cards) != 9:
            raise ValueError(f"PLO4 requires exactly 9 cards (4 hole + 5 board), got {len(cards)}")
        
        hole = list(cards[:4])
        board = list(cards[4:])
        
        return self._evaluate(hole, board)
    
    def _evaluate(self, hole: List[str], board: List[str]) -> int:
        """Internal evaluation with separated hole and board cards."""
        best = 999999  # High sentinel value for rank (lower is better)
        
        # C(4,2) = 6 combinations of hole cards to use
        for hole_combo in combinations(hole, 2):
            # C(5,3) = 10 combinations of board cards to use
            for board_combo in combinations(board, 3):
                rank = evaluate_cards(*hole_combo, *board_combo)
                if rank < best:
                    best = rank
        
        return best
    
    def _parse_hand_string(self, hand_str: str) -> List[str]:
        """Parse a hand string like 'AhKhQhJhTc9c8c7c6c' into card list."""
        cards = []
        hand_str = hand_str.lower()
        i = 0
        while i < len(hand_str):
            if i + 1 < len(hand_str):
                rank = hand_str[i].upper()  # Convert rank to uppercase
                suit = hand_str[i + 1]
                card = rank + suit
                if rank in RANKS and suit in SUITS:
                    cards.append(card)
                    i += 2
                else:
                    i += 1
            else:
                break
        return cards
    
    def evaluate_cards(self, hole: List[str], board: List[str]) -> int:
        """
        Evaluate with explicit hole and board lists.
        
        Args:
            hole: List of 4 hole card strings
            board: List of 5 board card strings
        
        Returns:
            Hand rank (lower is better)
        """
        return self._evaluate(hole, board)


class PLO4Equity:
    """
    PLO4 equity calculator using Monte Carlo simulation.
    
    Calculates winning probability for one hand vs another by
    enumerating all possible board combinations.
    """
    
    def __init__(self, seed: Optional[int] = None):
        self._eval = PLO4Evaluator()
        self._cache = {}
        # Import random for monte carlo
        import random
        self._random = random.Random(seed)
    
    def calculate(
        self,
        hand1: List[str],
        hand2: List[str],
        board: List[str],
        samples: int = 10000,
    ) -> Tuple[float, float]:
        """
        Calculate equity for two PLO4 hands.
        
        Args:
            hand1: First player's 4 hole cards
            hand2: Second player's 4 hole cards
            board: Known board cards (0-5), empty list for monte carlo
            samples: Number of simulations for monte carlo
        
        Returns:
            Tuple of (equity1, equity2) as percentages
        """
        if len(board) == 0:
            return self._monte_carlo(hand1, hand2, samples)
        
        if len(board) == 5:
            return self._exact_equity(hand1, hand2, board)
        
        # Partial board - need to complete and simulate
        return self._partial_board_equity(hand1, hand2, board, samples)
    
    def _exact_equity(
        self,
        hand1: List[str],
        hand2: List[str],
        board: List[str],
    ) -> Tuple[float, float]:
        """Exact equity when 5 board cards are known.
        
        In PLO4, each player uses exactly 2 hole cards + 3 board cards.
        We enumerate all C(4,2)*C(5,3) combos for each hand and find the best.
        """
        wins1 = 0
        wins2 = 0
        ties = 0
        
        # Evaluate each player's best 2-card + 3-board combo
        for h1_combo in combinations(hand1, 2):
            best_rank1 = 999999
            for board_combo in combinations(board, 3):
                rank = evaluate_cards(*h1_combo, *board_combo)
                if rank < best_rank1:
                    best_rank1 = rank
            
            for h2_combo in combinations(hand2, 2):
                best_rank2 = 999999
                for board_combo in combinations(board, 3):
                    rank = evaluate_cards(*h2_combo, *board_combo)
                    if rank < best_rank2:
                        best_rank2 = rank
                
                if best_rank1 < best_rank2:
                    wins1 += 1
                elif best_rank2 < best_rank1:
                    wins2 += 1
                else:
                    ties += 1
        
        total = wins1 + wins2 + ties
        if total == 0:
            return 50.0, 50.0
        
        return (wins1 / total) * 100, (wins2 / total) * 100
    
    def _monte_carlo(
        self,
        hand1: List[str],
        hand2: List[str],
        samples: int,
    ) -> Tuple[float, float]:
        """Monte Carlo equity estimation."""
        # Build deck from remaining cards
        used_cards = set(hand1 + hand2)
        deck = []
        for rank in RANKS:
            for suit in SUITS:
                card = rank + suit
                if card not in used_cards:
                    deck.append(card)
        
        wins1 = 0
        wins2 = 0
        ties = 0
        
        for _ in range(samples):
            self._random.shuffle(deck)
            board = deck[:5]
            
            rank1 = self._eval._evaluate(hand1, board)
            rank2 = self._eval._evaluate(hand2, board)
            
            if rank1 < rank2:
                wins1 += 1
            elif rank2 < rank1:
                wins2 += 1
            else:
                ties += 1
        
        total = wins1 + wins2 + ties
        if total == 0:
            return 50.0, 50.0
        
        return (wins1 / total) * 100, (wins2 / total) * 100
    
    def _partial_board_equity(
        self,
        hand1: List[str],
        hand2: List[str],
        board: List[str],
        samples: int,
    ) -> Tuple[float, float]:
        """Monte Carlo for partial board (1-4 known cards)."""
        # Known cards that can't be in the simulation deck
        used_cards = set(hand1 + hand2 + board)
        deck = []
        for rank in RANKS:
            for suit in SUITS:
                card = rank + suit
                if card not in used_cards:
                    deck.append(card)
        
        wins1 = 0
        wins2 = 0
        ties = 0
        board_missing = 5 - len(board)
        
        for _ in range(samples):
            self._random.shuffle(deck)
            board_sample = board + deck[:board_missing]
            
            rank1 = self._eval._evaluate(hand1, board_sample)
            rank2 = self._eval._evaluate(hand2, board_sample)
            
            if rank1 < rank2:
                wins1 += 1
            elif rank2 < rank1:
                wins2 += 1
            else:
                ties += 1
        
        total = wins1 + wins2 + ties
        if total == 0:
            return 50.0, 50.0
        
        return (wins1 / total) * 100, (wins2 / total) * 100


# Alias for backwards compatibility
PLO4HandEvaluator = PLO4Evaluator

__all__ = ["PLO4Evaluator", "PLO4Equity", "PLO4HandEvaluator", "plo4_hand_rank_to_percentage"]
