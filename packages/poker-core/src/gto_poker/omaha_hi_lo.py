"""Omaha Hi/Lo (8-or-better) - split pot game mode"""
from typing import List, Tuple, Optional
from itertools import combinations
from .deck import Card, RANKS
from .hand import Hand


class OmahaHiLoResult:
    """Result of Omaha Hi/Lo hand evaluation"""
    
    def __init__(self, high_hand: Optional[Hand], low_hand: Optional[Hand],
                 high_rank_key: Tuple, low_rank_key: Tuple,
                 can_win_low: bool, can_win_high: bool,
                 best_high_cards: List[Card], best_low_cards: List[Card]):
        self.high_hand = high_hand
        self.low_hand = low_hand
        self.high_rank_key = high_rank_key
        self.low_rank_key = low_rank_key
        self.can_win_low = can_win_low
        self.can_win_high = can_win_high
        self.best_high_cards = best_high_cards
        self.best_low_cards = best_low_cards
    
    @property
    def has_low(self) -> bool:
        """Whether a valid low hand exists"""
        return self.low_hand is not None
    
    def __str__(self):
        parts = []
        if self.high_hand:
            parts.append(f"High: {self.high_hand}")
        if self.low_hand:
            parts.append(f"Low: {self.low_hand}")
        if not parts:
            parts.append("No valid hand")
        return ", ".join(parts)


class OmahaHiLoEvaluator:
    """Evaluate Omaha Hi/Lo (8-or-better) hands
    
    Omaha Hi/Lo (8-or-better) rules:
    - 4 hole cards, 5 board
    - Must use exactly 2 hole + 3 board for BOTH high and low
    - High hand: standard poker rankings
    - Low hand: must be 8-or-better (8,7,6,5,4,3,2,A where A=1)
    - A-2-3-4-5 is the nut low (the "wheel")
    - If no low qualifies, high hand takes entire pot
    - Split pot: 50% to high, 50% to low
    """
    
    def __init__(self):
        pass
    
    def evaluate(self, hole_cards: List[Card], board: List[Card]) -> OmahaHiLoResult:
        """
        Evaluate Omaha Hi/Lo hand.
        
        Args:
            hole_cards: 4 hole cards (must use exactly 2)
            board: 5 board cards (must use exactly 3)
            
        Returns:
            OmahaHiLoResult with high and low hands
        """
        if len(hole_cards) != 4:
            raise ValueError(f"Need exactly 4 hole cards, got {len(hole_cards)}")
        if len(board) != 5:
            raise ValueError(f"Need exactly 5 board cards, got {len(board)}")
        
        # Evaluate high hand
        high_hand, high_cards = self.evaluate_high(hole_cards, board)
        
        # Evaluate low hand
        low_result = self.evaluate_low(hole_cards, board)
        
        if low_result is not None:
            low_cards, low_rank_key = low_result
            low_hand = Hand(low_cards)
            can_win_low = True
            can_win_high = True
        else:
            low_hand = None
            low_cards = []
            low_rank_key = None
            can_win_low = False
            can_win_high = True  # Takes entire pot
        
        # Build rank keys for comparison
        from .hand import hand_rank_key
        high_rank_key = hand_rank_key(high_hand.rank_list, high_hand.kickers) if high_hand else None
        
        return OmahaHiLoResult(
            high_hand=high_hand,
            low_hand=low_hand,
            high_rank_key=high_rank_key,
            low_rank_key=low_rank_key,
            can_win_low=can_win_low,
            can_win_high=can_win_high,
            best_high_cards=high_cards,
            best_low_cards=low_cards
        )
    
    def evaluate_high(self, hole_cards: List[Card], board: List[Card]) -> Tuple[Hand, List[Card]]:
        """
        Find the best HIGH hand from all 9 cards.
        Must use exactly 2 hole cards + 3 board cards.
        
        Returns:
            Tuple of (best Hand, cards used)
        """
        best_hand = None
        best_cards = []
        best_key = None
        
        for hole_combo in combinations(hole_cards, 2):
            for board_combo in combinations(board, 3):
                hand = Hand(list(hole_combo) + list(board_combo))
                from .hand import hand_rank_key
                key = hand_rank_key(hand.rank_list, hand.kickers)
                
                if best_key is None or key > best_key:
                    best_key = key
                    best_hand = hand
                    best_cards = list(hole_combo) + list(board_combo)
        
        return best_hand, best_cards
    
    def evaluate_low(self, hole_cards: List[Card], board: List[Card]) -> Optional[Tuple[List[Card], Tuple]]:
        """
        Find the best LOW hand (8-or-better).
        Must be exactly 5 cards, all rank 8 or lower.
        A-2-3-4-5 is the nut low (wheel).
        
        Returns:
            Tuple of (cards, rank_key) or None if no low qualifies
        """
        best_low = None
        best_key = None
        best_cards = []
        
        for hole_combo in combinations(hole_cards, 2):
            for board_combo in combinations(board, 3):
                five_cards = list(hole_combo) + list(board_combo)
                
                if self._is_valid_low(five_cards):
                    low_key = omaha_hi_lo_rank_key(five_cards)
                    
                    if best_key is None or low_key < best_key:
                        best_key = low_key
                        best_low = five_cards
                        best_cards = five_cards
        
        if best_low is None:
            return None
        
        return best_cards, best_key
    
    def _is_valid_low(self, cards: List[Card]) -> bool:
        """
        Check if 5 cards make a valid low hand (8-or-better).
        All cards must be 8 or lower in rank (A-2-3-4-5-6-7-8).
        Ace plays as 1 (low).
        Must have 5 unique ranks (no pairs allowed in qualifying low).
        """
        if len(cards) != 5:
            return False
        
        seen_ranks = set()
        for card in cards:
            ri = card.rank_index
            # A (12) is OK for low (plays as 1), 9 (rank_index 7) and above are not
            if ri >= 7 and ri != 12:  # 12 is Ace, ri=7 is 9 (not low-eligible)
                return False
            # Map to low-ace value: A=1, 2=2, 3=3, ..., 8=8
            low_val = 1 if ri == 12 else ri + 2  # ri=0(2)→2, ri=1(3)→3, ..., ri=6(8)→8
            if low_val in seen_ranks:
                return False  # Duplicate rank disqualifies
            seen_ranks.add(low_val)
        
        return True
    
    def can_make_low(self, cards: List[Card]) -> bool:
        """Check if 5 cards can make a valid low hand (8-or-better)"""
        return self._is_valid_low(cards)
    
    def split_pot(self, results: List[OmahaHiLoResult]) -> List[Tuple[float, float]]:
        """
        Split pot among players based on high/low results.
        
        Returns:
            List of (high_share, low_share) for each player
        """
        if not results:
            return []
        
        # Determine if any player can win low
        any_low = any(r.can_win_low for r in results)
        
        # Find best high and best low
        best_high_key = None
        best_low_key = None
        best_high_idx = -1
        best_low_idx = -1
        
        for i, result in enumerate(results):
            if result.high_rank_key and (best_high_key is None or result.high_rank_key > best_high_key):
                best_high_key = result.high_rank_key
                best_high_idx = i
            
            if result.can_win_low and result.low_rank_key and (best_low_key is None or result.low_rank_key < best_low_key):
                best_low_key = result.low_rank_key
                best_low_idx = i
        
        # Build shares
        shares = [(0.0, 0.0) for _ in results]
        
        if any_low and best_low_idx >= 0:
            # Low pot goes to best low
            shares[best_low_idx] = (shares[best_low_idx][0], 0.5)
            high_share = 0.5
        else:
            # No low qualifies, high takes entire pot
            high_share = 1.0
        
        if best_high_idx >= 0:
            # High pot goes to best high
            shares[best_high_idx] = (high_share, shares[best_high_idx][1])
        
        return shares


def omaha_hi_lo_rank_key(cards: List[Card]) -> Tuple:
    """
    Create a comparable key for low hand ranking.
    For low hands, LOWER is better (A-2-3-4-5 is best).
    Ace counts as 1 in low (not 14).
    
    Returns a tuple where lower = better low hand.
    The tuple is (card1_rank_as_low, card2_rank_as_low, ..., card5_rank_as_low)
    where Ace = 1, 2 = 2, ..., 8 = 8
    """
    # Convert to low ranks: A=1, 2=2, ..., 8=8, others ignored
    # Sort ascending for comparison
    low_ranks = []
    for card in cards:
        ri = card.rank_index
        if ri == 12:  # Ace
            low_ranks.append(1)
        elif ri <= 6:  # 2-8 (ri=6 is 8, ri=7 is 9 which is not low-eligible)
            low_ranks.append(ri + 2)  # 2→2, 3→3, ..., 8→8
        # 9,T,J,Q,K (ri > 7 and != 12) should not be included in valid low
    
    # Sort ascending (best low has lowest cards)
    low_ranks.sort()
    
    # Pad or truncate to 5
    while len(low_ranks) < 5:
        low_ranks.append(0)  # Pad with 0 for comparison
    
    return tuple(low_ranks[:5])


class OmahaHiLoEquity:
    """Calculate Omaha Hi/Lo equity between two hands"""
    
    def __init__(self, seed: Optional[int] = None):
        import random
        self._random = random.Random(seed)
        self._eval = OmahaHiLoEvaluator()
    
    def calculate(
        self,
        hand1: List[str],  # 4 hole cards
        hand2: List[str],  # 4 hole cards
        board: List[str],   # Known board (0-5)
        samples: int = 10000,
    ) -> Tuple[float, float, float, float]:
        """
        Calculate Omaha Hi/Lo equity.
        
        Returns:
            Tuple of (h1_high_equity, h2_high_equity, h1_low_equity, h2_low_equity)
            Note: When there's no low, the high hand gets the whole pot
        """
        
        if len(board) == 0:
            return self._monte_carlo(hand1, hand2, samples)
        
        if len(board) == 5:
            return self._exact(hand1, hand2, board)
        
        return self._partial_board(hand1, hand2, board, samples)
    
    def _exact(
        self,
        hand1: List[str],
        hand2: List[str],
        board: List[str],
    ) -> Tuple[float, float, float, float]:
        """Exact equity when 5 board cards are known."""
        from .deck import Deck
        
        h1_cards = [Deck.parse(c) for c in hand1]
        h2_cards = [Deck.parse(c) for c in hand2]
        board_cards = [Deck.parse(c) for c in board]
        
        result1 = self._eval.evaluate(h1_cards, board_cards)
        result2 = self._eval.evaluate(h2_cards, board_cards)
        
        # Compare high hands
        from .hand import hand_rank_key
        h1_high_key = hand_rank_key(result1.high_hand.rank_list, result1.high_hand.kickers)
        h2_high_key = hand_rank_key(result2.high_hand.rank_list, result2.high_hand.kickers)
        
        if h1_high_key > h2_high_key:
            h1_high_share = 1.0
            h2_high_share = 0.0
        elif h2_high_key > h1_high_key:
            h1_high_share = 0.0
            h2_high_share = 1.0
        else:
            h1_high_share = 0.5
            h2_high_share = 0.5
        
        # Compare low hands
        if result1.can_win_low and result2.can_win_low:
            if result1.low_rank_key < result2.low_rank_key:
                h1_low_share = 1.0
                h2_low_share = 0.0
            elif result2.low_rank_key < result1.low_rank_key:
                h1_low_share = 0.0
                h2_low_share = 1.0
            else:
                h1_low_share = 0.5
                h2_low_share = 0.5
        elif result1.can_win_low:
            h1_low_share = 1.0
            h2_low_share = 0.0
        elif result2.can_win_low:
            h1_low_share = 0.0
            h2_low_share = 1.0
        else:
            # No low, high takes all
            h1_low_share = 0.0
            h2_low_share = 0.0
        
        return (h1_high_share * 100, h2_high_share * 100,
                h1_low_share * 100, h2_low_share * 100)
    
    def _monte_carlo(
        self,
        hand1: List[str],
        hand2: List[str],
        samples: int,
    ) -> Tuple[float, float, float, float]:
        """Monte Carlo when no board is known."""
        from .deck import Deck, SUITS
        
        used_cards = set(hand1 + hand2)
        deck = []
        for rank in RANKS:
            for suit in SUITS:
                card = rank + suit
                if card not in used_cards:
                    deck.append(card)
        
        h1_high_wins = 0
        h2_high_wins = 0
        h1_low_wins = 0
        h2_low_wins = 0
        ties_high = 0
        ties_low = 0
        
        for _ in range(samples):
            self._random.shuffle(deck)
            board = deck[:5]
            
            h1_cards = [Deck.parse(c) for c in hand1]
            h2_cards = [Deck.parse(c) for c in hand2]
            board_cards = [Deck.parse(c) for c in board]
            
            result1 = self._eval.evaluate(h1_cards, board_cards)
            result2 = self._eval.evaluate(h2_cards, board_cards)
            
            from .hand import hand_rank_key
            h1_high_key = hand_rank_key(result1.high_hand.rank_list, result1.high_hand.kickers)
            h2_high_key = hand_rank_key(result2.high_hand.rank_list, result2.high_hand.kickers)
            
            if h1_high_key > h2_high_key:
                h1_high_wins += 1
            elif h2_high_key > h1_high_key:
                h2_high_wins += 1
            else:
                ties_high += 1
            
            if result1.can_win_low and result2.can_win_low:
                if result1.low_rank_key < result2.low_rank_key:
                    h1_low_wins += 1
                elif result2.low_rank_key < result1.low_rank_key:
                    h2_low_wins += 1
                else:
                    ties_low += 1
            elif result1.can_win_low:
                h1_low_wins += 1
            elif result2.can_win_low:
                h2_low_wins += 1
        
        total = samples
        return (
            (h1_high_wins / total) * 100,
            (h2_high_wins / total) * 100,
            (h1_low_wins / total) * 100,
            (h2_low_wins / total) * 100,
        )
    
    def _partial_board(
        self,
        hand1: List[str],
        hand2: List[str],
        board: List[str],
        samples: int,
    ) -> Tuple[float, float, float, float]:
        """Monte Carlo for partial board."""
        from .deck import Deck, SUITS
        
        used_cards = set(hand1 + hand2 + board)
        deck = []
        for rank in RANKS:
            for suit in SUITS:
                card = rank + suit
                if card not in used_cards:
                    deck.append(card)
        
        board_missing = 5 - len(board)
        
        h1_high_wins = 0
        h2_high_wins = 0
        h1_low_wins = 0
        h2_low_wins = 0
        
        for _ in range(samples):
            self._random.shuffle(deck)
            full_board = board + deck[:board_missing]
            
            h1_cards = [Deck.parse(c) for c in hand1]
            h2_cards = [Deck.parse(c) for c in hand2]
            board_cards = [Deck.parse(c) for c in full_board]
            
            result1 = self._eval.evaluate(h1_cards, board_cards)
            result2 = self._eval.evaluate(h2_cards, board_cards)
            
            from .hand import hand_rank_key
            h1_high_key = hand_rank_key(result1.high_hand.rank_list, result1.high_hand.kickers)
            h2_high_key = hand_rank_key(result2.high_hand.rank_list, result2.high_hand.kickers)
            
            if h1_high_key > h2_high_key:
                h1_high_wins += 1
            elif h2_high_key > h1_high_key:
                h2_high_wins += 1
            
            if result1.can_win_low and result2.can_win_low:
                if result1.low_rank_key < result2.low_rank_key:
                    h1_low_wins += 1
                elif result2.low_rank_key < result1.low_rank_key:
                    h2_low_wins += 1
            elif result1.can_win_low:
                h1_low_wins += 1
            elif result2.can_win_low:
                h2_low_wins += 1
        
        total = samples
        return (
            (h1_high_wins / total) * 100,
            (h2_high_wins / total) * 100,
            (h1_low_wins / total) * 100,
            (h2_low_wins / total) * 100,
        )


__all__ = [
    "OmahaHiLoResult", "OmahaHiLoEvaluator", "OmahaHiLoEquity",
    "omaha_hi_lo_rank_key", "evaluate_omaha_hi_lo"
]


# Convenience function for CI/compatibility
def evaluate_omaha_hi_lo(hole_cards, board):
    """Evaluate Omaha Hi/Lo — convenience wrapper around OmahaHiLoEvaluator."""
    return OmahaHiLoEvaluator().evaluate(hole_cards, board)
