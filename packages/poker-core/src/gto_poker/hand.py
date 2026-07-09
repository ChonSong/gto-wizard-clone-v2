"""Hand evaluation — find the best 5-card poker hand from 5-7 cards"""

from typing import List, Tuple
from .deck import Card

# Hand rankings (lower is better)
HAND_NAMES = {
    9: "Straight Flush",
    8: "Four of a Kind",
    7: "Full House",
    6: "Flush",
    5: "Straight",
    4: "Three of a Kind",
    3: "Two Pair",
    2: "One Pair",
    1: "High Card",
    0: "Invalid"
}

HAND_RANK = 9  # Straight Flush


def hand_rank_key(rank_list: List[int], kickers: List[int] = None) -> Tuple:
    """
    Create a comparable key for hand ranking.
    Returns (hand_type, rank_list, kickers)
    Higher values win.
    """
    if kickers is None:
        kickers = []
    return (rank_list[0] if rank_list else 0, 
            tuple(rank_list[1:] if len(rank_list) > 1 else []),
            tuple(kickers))


class Hand:
    """Represents a 5-card poker hand with evaluation"""
    
    def __init__(self, cards: List[Card]):
        if len(cards) < 5:
            raise ValueError(f"Need at least 5 cards, got {len(cards)}")
        if len(cards) > 7:
            raise ValueError(f"Cannot use more than 7 cards, got {len(cards)}")
        
        # Store all cards
        self.all_cards = list(cards)
        # Best 5-card hand
        self.best_5 = self._find_best_5()
        # Hand type and ranking
        self.hand_type, self.rank_list, self.kickers = self._evaluate(self.best_5)
    
    def _find_best_5(self) -> List[Card]:
        """Find the best 5-card combination from all cards"""
        from itertools import combinations
        
        best_hand = None
        best_key = None
        
        for combo in combinations(self.all_cards, 5):
            hand_type, rank_list, kickers = self._evaluate(list(combo))
            key = hand_rank_key(rank_list, kickers)
            
            if best_key is None or key > best_key:
                best_key = key
                best_hand = list(combo)
        
        return best_hand
    
    @staticmethod
    def _evaluate(cards: List[Card]) -> Tuple[int, List[int], List[int]]:
        """
        Evaluate a 5-card hand.
        Returns: (hand_type, rank_list, kickers)
        
        rank_list encodes the hand:
        - Straight Flush: [9, high_rank]
        - Four of a Kind: [8, quad_rank, kicker]
        - Full House: [7, trips_rank, pair_rank]
        - Flush: [6, sorted_rank_list]
        - Straight: [5, high_rank]
        - Three of a Kind: [4, trips_rank, kickers]
        - Two Pair: [3, high_pair, low_pair, kicker]
        - One Pair: [2, pair_rank, kickers]
        - High Card: [1, sorted_ranks]
        """
        ranks = [c.rank_index for c in cards]
        suits = [c.suit for c in cards]
        
        # Count ranks
        from collections import Counter
        rank_counts = Counter(ranks)
        
        # Sort ranks by (count desc, rank desc)
        sorted_ranks = sorted(ranks, key=lambda r: (-rank_counts[r], -r))
        unique_ranks = []
        for r in sorted_ranks:
            if r not in unique_ranks:
                unique_ranks.append(r)
        
        # Check flush
        is_flush = all(s == suits[0] for s in suits)
        
        # Check straight
        # Sort ranks descending so we can check consecutive descending
        unique_sorted_desc = sorted(set(ranks), reverse=True)
        is_straight = False
        straight_high = None

        # Normal straight — consecutive ranks descending (e.g., 11,10,9,8,7 = K,Q,J,T,9)
        if len(unique_sorted_desc) >= 5:
            for i in range(len(unique_sorted_desc) - 4):
                # Check if each consecutive pair differs by 1 (descending order: 11→10→9→8→7)
                consecutive = all(
                    unique_sorted_desc[j] - unique_sorted_desc[j + 1] == 1
                    for j in range(i, i + 4)
                )
                if consecutive:
                    is_straight = True
                    straight_high = unique_sorted_desc[i]  # highest card in the straight
                    break

        # Ace-low straight (A-2-3-4-5): ranks 12, 0, 1, 2, 3
        if 12 in unique_sorted_desc and 0 in unique_sorted_desc:
            wheel_cards = {12, 0, 1, 2, 3}
            if wheel_cards.issubset(set(unique_sorted_desc)):
                is_straight = True
                straight_high = 3  # 5-high straight (Ace plays low)
        
        # Determine hand type
        if is_flush and is_straight:
            return (9, [9, straight_high], [])
        elif rank_counts.most_common(1)[0][1] == 4:
            # Four of a kind
            quad_rank = rank_counts.most_common(1)[0][0]
            kicker = [r for r in sorted_ranks if r != quad_rank][0]
            return (8, [8, quad_rank], [kicker])
        elif len(unique_ranks) >= 2:
            counts = [c for r, c in rank_counts.most_common(2)]
            if counts[0] == 3 and counts[1] == 2:
                # Full house
                trips = rank_counts.most_common(1)[0][0]
                pair = [r for r, c in rank_counts.most_common(2) if c == 2][0]
                return (7, [7, trips, pair], [])
            elif is_flush:
                return (6, [6] + sorted(ranks, reverse=True), [])
            elif is_straight:
                return (5, [5, straight_high], [])
            elif counts[0] == 3:
                # Three of a kind
                trips = rank_counts.most_common(1)[0][0]
                kickers = [r for r in sorted_ranks if r != trips][:2]
                return (4, [4, trips], kickers)
            elif counts[0] == 2 and counts[1] == 2:
                # Two pair
                pairs = [r for r, c in rank_counts.most_common(2) if c == 2]
                high_pair = max(pairs)
                low_pair = min(pairs)
                kicker = [r for r in sorted_ranks if r not in pairs][0]
                return (3, [3, high_pair, low_pair], [kicker])
            elif counts[0] == 2:
                # One pair
                pair_rank = rank_counts.most_common(1)[0][0]
                kickers = [r for r in sorted_ranks if r != pair_rank][:3]
                return (2, [2, pair_rank], kickers)
        
        # High card
        return (1, [1] + sorted(ranks, reverse=True), [])
    
    @property
    def name(self) -> str:
        return HAND_NAMES.get(self.hand_type, "Unknown")
    
    def __str__(self):
        cards_str = " ".join(str(c) for c in self.best_5)
        return f"{self.name}: {cards_str}"
    
    def __repr__(self):
        return f"Hand({[str(c) for c in self.all_cards]})"
    
    def __lt__(self, other):
        return self.compare_to(other) < 0
    
    def __gt__(self, other):
        return self.compare_to(other) > 0
    
    def __eq__(self, other):
        return self.compare_to(other) == 0
    
    def compare_to(self, other: "Hand") -> int:
        """Compare hands: returns -1, 0, or 1"""
        self_key = hand_rank_key(self.rank_list, self.kickers)
        other_key = hand_rank_key(other.rank_list, other.kickers)
        
        if self_key > other_key:
            return 1
        elif self_key < other_key:
            return -1
        return 0


class HandEvaluator:
    """Utilities for hand comparison and equity"""
    
    @staticmethod
    def best_hand(cards: List[Card]) -> Hand:
        """Find best 5-card hand from cards"""
        return Hand(cards)
    
    @staticmethod
    def compare(cards1: List[Card], cards2: List[Card]) -> int:
        """Compare two hands: -1 if p1 wins, 0 if tie, 1 if p2 wins"""
        return Hand(cards1).compare_to(Hand(cards2))