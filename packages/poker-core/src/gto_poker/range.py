"""Range parsing — convert poker range strings to hand lists"""

from typing import List, Set
from itertools import combinations
from .deck import Card, RANKS, SUITS

# All 169 pre-flop hand combinations
PREFLOP_HANDS = []
for r1 in RANKS:
    for r2 in RANKS:
        PREFLOP_HANDS.append((r1, r2, r1 == r2))  # (rank1, rank2, suited)

# Broadway ranks (T, J, Q, K, A)
BROADWAY_RANKS = ["T", "J", "Q", "K", "A"]


class RangeParser:
    """
    Parse poker range strings like 'JJ+, AQs+, KJs'
    
    Supports:
    - Single hands: 'AA', 'AKs', 'AhKh'
    - Ranges: 'JJ+' (JJ and any pair above), '55-JJ' (55 through JJ)
    - Suit modifiers: 'AKs' (suited), 'AKo' (offsuit)
    - Combos: 'AA,KK,QQ'
    """
    
    def __init__(self):
        self._combo_cache = {}
    
    def parse(self, range_str: str) -> Set[str]:
        """
        Parse range string into set of hand strings.
        Returns set like {'AA', 'AKs', 'AhKd', 'QQ', ...}
        """
        range_str = range_str.replace(" ", "").upper()
        
        if not range_str:
            return set()
        
        hands = set()
        parts = range_str.split(",")
        
        for part in parts:
            if '+' in part:
                # e.g., 'JJ+' means JJ and any pair above
                hands.update(self._parse_plus_range(part))
            elif '-' in part:
                # e.g., '55-JJ' means 55 through JJ
                hands.update(self._parse_dash_range(part))
            else:
                # Single hand or hand type
                hands.update(self._expand_hand(part))
        
        return hands
    
    def _parse_plus_range(self, part: str) -> Set[str]:
        """Handle JJ+ and AKs+ style ranges"""
        base = part.replace("+", "")
        hands = set()
        
        # Determine if it's a pair range (like JJ+) or a broadway range (like AKs+)
        is_pair_base = len(base) == 2 and base[0] == base[1]
        is_suited = base.endswith('S') if len(base) >= 3 else False
        is_offsuit = base.endswith('O') if len(base) >= 3 else False
        
        if is_pair_base:
            # Pair range: 'TT+' means TT, JJ, QQ, KK, AA
            base_idx = RANKS.index(base[0])
            for rank in RANKS[base_idx:]:
                hands.add(f"{rank}{rank}")
        elif len(base) >= 2:
            r1, r2 = base[0], base[1]
            r1_idx = RANKS.index(r1)
            r2_idx = RANKS.index(r2)
            
            if r1 == r2:
                # e.g., 'AA+' -> AA (only AA since it's the top)
                hands.add(f"{r1}{r2}")
            elif r1 in BROADWAY_RANKS and r2 in BROADWAY_RANKS:
                # Broadway combo ranges:
                # 'AJ+' -> all Broadway combos where both cards >= J (i.e., AJ, AT, AK, KQ, KJ, QJ, etc.)
                # 'AKs+' -> AQs, AJs, ATs...A2s (all suited combos with A as higher card and lower <= K)
                # 'AK+' -> AKs, AKo, and all lower broadway combos
                
                # Determine the minimum rank indices
                if r1_idx > r2_idx:
                    min_higher_idx = r1_idx
                    min_lower_idx = r2_idx
                else:
                    min_higher_idx = r2_idx
                    min_lower_idx = r1_idx
                
                a_idx = RANKS.index('A')
                
                # A-high ranges with explicit suit suffix (AKs+, AQs+, ATs+) mean:
                # "all combos with A as higher card and lower card rank <= the base lower card"
                # AKs+ => AKs, AQs, AJs, ATs, A9s...A2s (lower <= K)
                # AQs+ => AQs, AJs, ATs, A9s...A2s (lower <= Q)
                # ATs+ => ATs, A9s...A2s (lower <= T)
                # A-high ranges without suffix (AK+, AQ+) mean all Broadway combos >= base
                if min_higher_idx == a_idx and '+' in part and (is_suited or is_offsuit):
                    if is_suited:
                        for br2 in RANKS[:a_idx]:  # All ranks below A
                            if RANKS.index(br2) <= min_lower_idx:
                                hands.add(f"A{br2}S")
                    elif is_offsuit:
                        for br2 in RANKS[:a_idx]:
                            if RANKS.index(br2) <= min_lower_idx:
                                hands.add(f"A{br2}O")
                elif is_suited:
                    # 'AJs+' (with s suffix): all suited Broadway combos with higher >= A and lower >= J
                    for br1 in BROADWAY_RANKS:
                        for br2 in BROADWAY_RANKS:
                            if br1 != br2:
                                br1_idx = RANKS.index(br1)
                                br2_idx = RANKS.index(br2)
                                higher_idx = max(br1_idx, br2_idx)
                                lower_idx = min(br1_idx, br2_idx)
                                if higher_idx >= min_higher_idx and lower_idx >= min_lower_idx:
                                    hands.add(f"{RANKS[higher_idx]}{RANKS[lower_idx]}S")
                elif is_offsuit:
                    for br1 in BROADWAY_RANKS:
                        for br2 in BROADWAY_RANKS:
                            if br1 != br2:
                                br1_idx = RANKS.index(br1)
                                br2_idx = RANKS.index(br2)
                                higher_idx = max(br1_idx, br2_idx)
                                lower_idx = min(br1_idx, br2_idx)
                                if higher_idx >= min_higher_idx and lower_idx >= min_lower_idx:
                                    hands.add(f"{RANKS[higher_idx]}{RANKS[lower_idx]}O")
                else:
                    # 'AJ+' or 'AK+' (no suffix): all Broadway combos where lower >= J
                    # For AJ+: any Broadway combo where both cards are at least J
                    # For AK+: any Broadway combo where higher >= A and lower >= K
                    for br1 in BROADWAY_RANKS:
                        for br2 in BROADWAY_RANKS:
                            if br1 != br2:
                                br1_idx = RANKS.index(br1)
                                br2_idx = RANKS.index(br2)
                                higher_idx = max(br1_idx, br2_idx)
                                lower_idx = min(br1_idx, br2_idx)
                                # Broadway combo: both cards are T,J,Q,K,A
                                # AJ+ means: higher >= A (12) OR higher >= K (11) with lower >= Q (10) OR ...
                                # Simplified: for no-suffix Broadway ranges, include if lower >= min_lower_idx
                                if lower_idx >= min_lower_idx:
                                    hands.add(f"{RANKS[higher_idx]}{RANKS[lower_idx]}S")
                                    hands.add(f"{RANKS[higher_idx]}{RANKS[lower_idx]}O")
            else:
                # Non-broadway range (like '87s+')
                r1_idx = RANKS.index(r1)
                r2_idx = RANKS.index(r2)
                
                if r1_idx > r2_idx:
                    # Connected range: add base hand plus all higher connected combos
                    hands.add(f"{r1}{r2}{'S' if is_suited else 'O'}")
                    
                    # Add all combos above the base (same rank difference)
                    rank_diff = r1_idx - r2_idx
                    
                    for higher_r1_idx in range(r1_idx, len(RANKS)):
                        higher_r2_idx = higher_r1_idx - rank_diff
                        if higher_r2_idx >= 0 and higher_r1_idx != higher_r2_idx:
                            higher_r1 = RANKS[higher_r1_idx]
                            higher_r2 = RANKS[higher_r2_idx]
                            suffix = 'S' if is_suited else 'O'
                            hands.add(f"{higher_r1}{higher_r2}{suffix}")
                else:
                    hands.add(f"{r1}{r2}{'S' if is_suited else 'O'}")
        
        return hands
    
    def _parse_dash_range(self, part: str) -> Set[str]:
        """Handle 55-JJ style ranges (pairs only for now)"""
        hands = set()
        
        if '-' not in part:
            return self._expand_hand(part)
        
        parts = part.split('-')
        if len(parts) != 2:
            return set()
        
        low = parts[0].upper()
        high = parts[1].upper()
        
        # Check if both are pairs
        if len(low) == 2 and len(high) == 2 and low[0] == low[1] and high[0] == high[1]:
            low_idx = RANKS.index(low[0])
            high_idx = RANKS.index(high[0])
            
            for rank in RANKS[low_idx:high_idx + 1]:
                hands.add(f"{rank}{rank}")
        elif len(low) == 3 and len(high) == 3:
            # Broadway dash range like 'AJs-ATs' or 'AKo-KQo'
            low_suited = low.endswith('S')
            high_suited = high.endswith('S')
            
            if low_suited == high_suited:
                r1_low, r2_low = low[0], low[1]
                r1_high, r2_high = high[0], high[1]
                
                r1_low_idx = RANKS.index(r1_low)
                r2_low_idx = RANKS.index(r2_low)
                r1_high_idx = RANKS.index(r1_high)
                r2_high_idx = RANKS.index(r2_high)
                
                suffix = 'S' if low_suited else 'O'
                
                for r1_idx in range(r1_low_idx, r1_high_idx + 1):
                    for r2_idx in range(r2_low_idx, r2_high_idx + 1):
                        if r1_idx != r2_idx:
                            hands.add(f"{RANKS[r1_idx]}{RANKS[r2_idx]}{suffix}")
        
        return hands
    
    def _expand_hand(self, hand_str: str) -> Set[str]:
        """Expand a single hand into all suit combinations"""
        hands = set()
        hand_str = hand_str.upper()  # Normalize input

        if len(hand_str) == 2:
            # Pair: 'QQ' -> QhQd, QhQc, QhQs, QdQc, QdQs, QcQs (6 combos)
            rank = hand_str[0]
            for s1, s2 in combinations(SUITS, 2):
                hands.add(f"{rank}{s1}{rank}{s2}")
        elif len(hand_str) == 3:
            # Hand type: 'AKs' or 'AKo'
            r1, r2, suit_type = hand_str[0], hand_str[1], hand_str[2]
            if suit_type == 'S':  # Suited - 4 combos (one per suit)
                for s in SUITS:
                    hands.add(f"{r1}{s}{r2}{s}")
            elif suit_type == 'O':  # Offsuit - 12 combos (4*3 = 12)
                for s1 in SUITS:
                    for s2 in SUITS:
                        if s1 != s2:  # Different suits for offsuit
                            hands.add(f"{r1}{s1}{r2}{s2}")
            else:
                hands.add(hand_str)
        elif len(hand_str) == 4:
            # Specific combo: 'AhKd' or 'AHKH' -> normalize to 'AhKd'
            r1, s1, r2, s2 = hand_str[0], hand_str[1].lower(), hand_str[2], hand_str[3].lower()
            hands.add(f"{r1}{s1}{r2}{s2}")

        return hands
    
    def range_to_combos(self, range_str: str) -> List[List[Card]]:
        """Convert range string to list of Card pairs"""
        hands = self.parse(range_str)
        combos = []
        
        for hand_str in hands:
            try:
                if len(hand_str) == 4:
                    c1 = Card(hand_str[0], hand_str[1])
                    c2 = Card(hand_str[2], hand_str[3])
                    combos.append([c1, c2])
                elif len(hand_str) == 3:
                    r1, r2, st = hand_str[0], hand_str[1], hand_str[2]
                    if st == 'S':
                        for s in SUITS:
                            combos.append([Card(r1, s), Card(r2, s)])
                    elif st == 'O':
                        for s1, s2 in combinations(SUITS, 2):
                            combos.append([Card(r1, s1), Card(r2, s2)])
            except ValueError:
                continue
        
        return combos
    
    def range_to_combo_count(self, range_str: str) -> int:
        """
        Return number of specific combos (like 'AhKh') in a range.
        Pairs: 6 combos each
        Suited hands: 4 combos each
        Offsuit hands: 12 combos each
        """
        hands = self.parse(range_str)
        total = 0
        for h in hands:
            if len(h) == 4:
                total += 1  # Already a specific combo
            elif len(h) == 3:
                total += 4 if h[2] == 'S' else 12
            elif len(h) == 2:
                total += 6  # 6 combos for pairs
        return total
    
    @staticmethod
    def combo_count(range_str: str) -> int:
        """Return number of hand combinations in a range"""
        return RangeParser().range_to_combo_count(range_str)
    
    def get_all_combos(self, range_str: str) -> List[str]:
        """
        Return all 4-character combo strings like 'AhKh', 'AsKs', etc.
        for a given range string.
        """
        hands = self.parse(range_str)
        combos = []
        
        for hand_str in hands:
            if len(hand_str) == 2:
                # Pair: expand to all 6 combos
                rank = hand_str[0]
                for s1, s2 in combinations(SUITS, 2):
                    combos.append(f"{rank}{s1}{rank}{s2}")
            elif len(hand_str) == 3:
                r1, r2, suit_type = hand_str[0], hand_str[1], hand_str[2]
                if suit_type == 'S':
                    # 4 suited combos
                    for s in SUITS:
                        combos.append(f"{r1}{s}{r2}{s}")
                elif suit_type == 'O':
                    # 12 offsuit combos
                    for s1 in SUITS:
                        for s2 in SUITS:
                            if s1 != s2:
                                combos.append(f"{r1}{s1}{r2}{s2}")
            elif len(hand_str) == 4:
                # Already a specific combo
                combos.append(hand_str)
        
        return combos
    
    @staticmethod
    def expand_range(range_str: str) -> Set[str]:
        """Static method to parse a range string"""
        return RangeParser().parse(range_str)
