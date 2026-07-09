"""Shortdeck (6+ hold'em) hand evaluation.

Shortdeck is a variant where cards 2-5 are removed from the deck (36 cards).
Hand rankings are adjusted: flush beats full house, which beats straight.
"""
from typing import List, Tuple, Optional
import random

# Shortdeck ranks: 6, 7, 8, 9, T, J, Q, K, A
SHORTDECK_RANKS = ["6", "7", "8", "9", "T", "J", "Q", "K", "A"]
SHORTDECK_SUITS = ["h", "d", "c", "s"]
SHORTDECK_RANK_ORDER = {r: i for i, r in enumerate(SHORTDECK_RANKS)}  # 6=0, A=8

# Shortdeck hand type indices (for comparison, higher wins)
# Note: These are NOT the same as standard poker hand indices
# Shortdeck: SF > 4K > Flush > FullHouse > Straight > 3K > 2P > 1P > HC
# Convenience function for CI/compatibility
def evaluate_shortdeck(hole_cards, board):
    """Evaluate a Shortdeck hand — convenience wrapper around ShortdeckHand."""
    return ShortdeckHand(hole_cards + board)


SHORTDECK_HAND_NAMES = {
    9: "Straight Flush",
    8: "Four of a Kind",
    7: "Flush",
    6: "Full House",
    5: "Straight",
    4: "Three of a Kind",
    3: "Two Pair",
    2: "One Pair",
    1: "High Card",
    0: "Invalid"
}


def shortdeck_rank_index(rank: str) -> int:
    """Get rank index in shortdeck (6=0, A=8)"""
    return SHORTDECK_RANK_ORDER[rank.upper()]


def hand_rank_key(rank_list: List[int], kickers: Optional[List[int]] = None) -> Tuple:
    """Create a comparable key for hand ranking. Higher values win."""
    if kickers is None:
        kickers = []
    return (
        rank_list[0] if rank_list else 0,
        tuple(rank_list[1:] if len(rank_list) > 1 else []),
        tuple(kickers)
    )


class ShortdeckCard:
    """Single shortdeck playing card"""
    
    def __init__(self, rank: str, suit: str):
        self.rank = rank.upper()
        self.suit = suit.lower()
        if self.rank not in SHORTDECK_RANKS:
            raise ValueError(f"Invalid shortdeck rank: {rank}")
        if self.suit not in SHORTDECK_SUITS:
            raise ValueError(f"Invalid suit: {suit}")
    
    @property
    def rank_index(self) -> int:
        """0-8 rank index (6=0, A=8)"""
        return SHORTDECK_RANK_ORDER[self.rank]
    
    def __str__(self):
        return f"{self.rank}{self.suit}"
    
    def __repr__(self):
        return f"ShortdeckCard('{self.rank}', '{self.suit}')"
    
    def __eq__(self, other):
        return self.rank == other.rank and self.suit == other.suit
    
    def __hash__(self):
        return hash((self.rank, self.suit))


class ShortdeckDeck:
    """Shortdeck 36-card deck (6-A only)"""
    
    def __init__(self):
        self._cards = [ShortdeckCard(r, s) for s in SHORTDECK_SUITS for r in SHORTDECK_RANKS]
    
    def shuffle(self, seed: int = None):
        if seed is not None:
            random.seed(seed)
        random.shuffle(self._cards)
    
    def draw(self, n: int = 1) -> List[ShortdeckCard]:
        if n > len(self._cards):
            raise ValueError(f"Cannot draw {n} cards from deck of {len(self._cards)}")
        cards = self._cards[:n]
        self._cards = self._cards[n:]
        return cards
    
    def draw_one(self) -> ShortdeckCard:
        return self.draw(1)[0]
    
    def reset(self):
        self._cards = [ShortdeckCard(r, s) for s in SHORTDECK_SUITS for r in SHORTDECK_RANKS]
    
    def __len__(self):
        return len(self._cards)
    
    def __iter__(self):
        return iter(self._cards)
    
    @staticmethod
    def parse(card_str: str) -> ShortdeckCard:
        if len(card_str) != 2:
            raise ValueError(f"Invalid card string: {card_str}")
        return ShortdeckCard(card_str[0], card_str[1])


class ShortdeckHand:
    """Represents a 5-card Shortdeck hand with evaluation.
    
    Shortdeck uses a 36-card deck (6-A) and has different hand rankings:
    - Straight Flush (9)
    - Four of a Kind (8)
    - Flush (7) — beats Full House
    - Full House (6) — beats Straight
    - Straight (5)
    - Three of a Kind (4)
    - Two Pair (3)
    - One Pair (2)
    - High Card (1)
    """
    
    def __init__(self, cards: List):
        if len(cards) < 5:
            raise ValueError(f"Need at least 5 cards, got {len(cards)}")
        if len(cards) > 7:
            raise ValueError(f"Cannot use more than 7 cards, got {len(cards)}")
        
        # Accept both ShortdeckCard and regular Card objects
        self.all_cards = []
        for c in cards:
            if isinstance(c, ShortdeckCard):
                self.all_cards.append(c)
            elif isinstance(c, str):
                self.all_cards.append(ShortdeckDeck.parse(c))
            else:
                # Assume it's a Card object with rank_index
                self.all_cards.append(c)
        
        self.best_5 = self._find_best_5()
        self.hand_type, self.rank_list, self.kickers = self._evaluate(self.best_5)
    
    def _find_best_5(self) -> List:
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
    def _evaluate(cards: List) -> Tuple[int, List[int], List[int]]:
        """
        Evaluate a 5-card Shortdeck hand.
        Returns: (hand_type, rank_list, kickers)

        Shortdeck hand types:
        - Straight Flush: [9, high_rank]
        - Four of a Kind: [8, quad_rank, kicker]
        - Flush: [7, sorted_rank_list]
        - Full House: [6, trips_rank, pair_rank]
        - Straight: [5, high_rank]
        - Three of a Kind: [4, trips_rank, kickers]
        - Two Pair: [3, high_pair, low_pair, kicker]
        - One Pair: [2, pair_rank, kickers]
        - High Card: [1, sorted_ranks]
        """
        # Convert standard Card rank_index (0-12, 2=A) to shortdeck rank_index (0-8, 6=A)
        # This allows both ShortdeckCard and regular Card objects to work
        ranks = []
        for c in cards:
            ri = c.rank_index
            if isinstance(c, ShortdeckCard):
                # ShortdeckCard already returns 0-8 indices
                ranks.append(ri)
            elif 4 <= ri <= 11:  # 6-K in standard (rank_index 4-11)
                ranks.append(ri - 4)  # 6→0, 7→1, ..., K→7
            elif ri == 12:  # Ace in standard
                ranks.append(8)  # A→8
            else:
                # 2-5 shouldn't appear in valid shortdeck, but handle gracefully
                ranks.append(ri)

        suits = [c.suit for c in cards]

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
        # Shortdeck has 6-7-8-9-10-J-Q-K-A, no 2-3-4-5
        # So straights are: 6-7-8-9-10, 7-8-9-10-J, 8-9-10-J-Q, 9-10-J-Q-K, 10-J-Q-K-A
        unique_sorted_desc = sorted(set(ranks), reverse=True)
        is_straight = False
        straight_high = None
        
        # Check for standard straights (descending consecutive)
        if len(unique_sorted_desc) >= 5:
            for i in range(len(unique_sorted_desc) - 4):
                consecutive = all(
                    unique_sorted_desc[j] - unique_sorted_desc[j + 1] == 1
                    for j in range(i, i + 4)
                )
                if consecutive:
                    is_straight = True
                    straight_high = unique_sorted_desc[i]
                    break
        
        # Check for wheel (A-6-7-8-9) - ace plays low in shortdeck
        # A has index 8, 6 has index 0. A-6-7-8-9 = indices 8,0,1,2,3
        if 8 in unique_sorted_desc and 0 in unique_sorted_desc:
            wheel_cards = {8, 0, 1, 2, 3}
            if wheel_cards.issubset(set(unique_sorted_desc)):
                is_straight = True
                straight_high = 3  # 9-high straight (A-6-7-8-9 plays as 9-high)
        
        # Determine hand type using Shortdeck rankings
        # Key difference from NLHE: Flush > Full House > Straight
        if is_flush and is_straight:
            return (9, [9, straight_high], [])
        elif rank_counts.most_common(1)[0][1] == 4:
            # Four of a kind
            quad_rank = rank_counts.most_common(1)[0][0]
            kicker = [r for r in sorted_ranks if r != quad_rank][0]
            return (8, [8, quad_rank], [kicker])
        elif is_flush:
            # Flush beats Full House in Shortdeck
            return (7, [7] + sorted(ranks, reverse=True), [])
        elif len(unique_ranks) >= 2:
            counts = [c for r, c in rank_counts.most_common(2)]
            if counts[0] == 3 and counts[1] == 2:
                # Full House beats Straight in Shortdeck
                trips = rank_counts.most_common(1)[0][0]
                pair = [r for r, c in rank_counts.most_common(2) if c == 2][0]
                return (6, [6, trips, pair], [])
            elif is_straight:
                # Straight is weaker than Full House and Flush in Shortdeck
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
        return SHORTDECK_HAND_NAMES.get(self.hand_type, "Unknown")
    
    def __str__(self):
        cards_str = " ".join(str(c) for c in self.best_5)
        return f"{self.name}: {cards_str}"
    
    def __repr__(self):
        return f"ShortdeckHand({[str(c) for c in self.all_cards]})"
    
    def __lt__(self, other):
        return self.compare_to(other) < 0
    
    def __gt__(self, other):
        return self.compare_to(other) > 0
    
    def __eq__(self, other):
        return self.compare_to(other) == 0
    
    def compare_to(self, other: "ShortdeckHand") -> int:
        """Compare hands: returns -1, 0, or 1"""
        self_key = hand_rank_key(self.rank_list, self.kickers)
        other_key = hand_rank_key(other.rank_list, other.kickers)
        
        if self_key > other_key:
            return 1
        elif self_key < other_key:
            return -1
        return 0


class ShortdeckEquity:
    """Shortdeck equity calculator"""
    
    def __init__(self, seed: Optional[int] = None):
        self._random = random.Random(seed)
    
    def calculate(
        self,
        hand1: List[str],
        hand2: List[str],
        board: List[str],
        samples: int = 10000,
    ) -> Tuple[float, float]:
        """
        Calculate equity for two Shortdeck hands.
        Uses ShortdeckHand for evaluation.
        """
        if len(board) == 0:
            return self._monte_carlo(hand1, hand2, samples)
        
        if len(board) == 5:
            return self._exact_equity(hand1, hand2, board)
        
        return self._partial_board_equity(hand1, hand2, board, samples)
    
    def _exact_equity(
        self,
        hand1: List[str],
        hand2: List[str],
        board: List[str],
    ) -> Tuple[float, float]:
        """Exact equity when 5 board cards are known."""
        h1 = ShortdeckHand(hand1 + board)
        h2 = ShortdeckHand(hand2 + board)
        
        if h1 > h2:
            return 100.0, 0.0
        elif h2 > h1:
            return 0.0, 100.0
        return 50.0, 50.0
    
    def _monte_carlo(
        self,
        hand1: List[str],
        hand2: List[str],
        samples: int,
    ) -> Tuple[float, float]:
        """Monte Carlo equity estimation."""
        used_cards = set(hand1 + hand2)
        deck = []
        for rank in SHORTDECK_RANKS:
            for suit in SHORTDECK_SUITS:
                card = rank + suit
                if card not in used_cards:
                    deck.append(card)
        
        wins1 = 0
        wins2 = 0
        ties = 0
        
        for _ in range(samples):
            self._random.shuffle(deck)
            board = deck[:5]
            
            h1 = ShortdeckHand(hand1 + board)
            h2 = ShortdeckHand(hand2 + board)
            
            if h1 > h2:
                wins1 += 1
            elif h2 > h1:
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
        """Monte Carlo for partial board."""
        used_cards = set(hand1 + hand2 + board)
        deck = []
        for rank in SHORTDECK_RANKS:
            for suit in SHORTDECK_SUITS:
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
            
            h1 = ShortdeckHand(hand1 + board_sample)
            h2 = ShortdeckHand(hand2 + board_sample)
            
            if h1 > h2:
                wins1 += 1
            elif h2 > h1:
                wins2 += 1
            else:
                ties += 1
        
        total = wins1 + wins2 + ties
        if total == 0:
            return 50.0, 50.0
        
        return (wins1 / total) * 100, (wins2 / total) * 100


__all__ = [
    "ShortdeckCard", "ShortdeckDeck", "ShortdeckHand", "ShortdeckEquity",
    "shortdeck_rank_index", "SHORTDECK_RANKS", "SHORTDECK_HAND_NAMES"
]
