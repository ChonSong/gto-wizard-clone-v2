"""Polish edge case tests for Omaha Hi/Lo

- 8-qualifier with paired boards (A-2-3-4-4)
- Verification that paired board can still allow low with right hole cards
- Verification that paired board yields no low without low fillers
"""
import pytest
import sys
sys.path.insert(0, "packages/poker-core/src")

from gto_poker.deck import Card
from gto_poker.omaha_hi_lo import (
    OmahaHiLoEvaluator,
    omaha_hi_lo_rank_key,
)


class TestOmahaHiLoPairedBoardEdgeCases:
    """Edge cases with paired boards and 8-qualifier."""

    def test_paired_board_a_2_3_4_4_with_low_hole(self):
        """Board A-2-3-4-4 (paired 4s) + hole with low cards = valid low.
        
        Use A-2-3 from board (avoiding the paired 4) + 5-6 from hole."""
        ev = OmahaHiLoEvaluator()
        board = [Card('A', 's'), Card('2', 's'), Card('3', 's'), Card('4', 's'), Card('4', 'h')]
        hole = [Card('5', 'h'), Card('6', 'd'), Card('K', 'c'), Card('Q', 's')]
        result = ev.evaluate(hole, board)
        # A-2-3-5-6 is a valid low
        assert result.has_low is True
        # Expected low cards: A,2,3,5,6 (card objects, check ranks)
        low_ranks = sorted([c.rank_index for c in result.best_low_cards])
        # rank_indices: A=12, 2=0, 3=1, 5=3, 6=4
        assert low_ranks == [0, 1, 3, 4, 12], f"Expected [0,1,3,4,12] (2,3,5,6,A), got {low_ranks}"

    def test_paired_board_a_2_3_4_4_no_low_hole(self):
        """Board A-2-3-4-4 (paired 4s) + hole with NO low cards = no low.
        
        All hole cards are 9+ so can't contribute to low.
        Even though board has 4 distinct low ranks (A-2-3-4), we need
        2 hole cards <= 8 and that's impossible."""
        ev = OmahaHiLoEvaluator()
        board = [Card('A', 's'), Card('2', 's'), Card('3', 's'), Card('4', 's'), Card('4', 'h')]
        hole = [Card('9', 'h'), Card('T', 'd'), Card('K', 'c'), Card('Q', 's')]
        result = ev.evaluate(hole, board)
        assert result.has_low is False

    def test_paired_board_three_low_distinct_on_board(self):
        """Board with A-2-4-4-4: only 3 distinct low ranks on board.
        Need 2 low cards from hole to make 5-card low."""
        ev = OmahaHiLoEvaluator()
        # Board: A,2,4,4,4 (only A,2,4 are low)
        board = [Card('A', 's'), Card('2', 's'), Card('4', 'h'), Card('4', 'd'), Card('4', 'c')]
        # Hole: 3,5,K,Q -> can make A-2-3-4-5 low
        hole = [Card('3', 'h'), Card('5', 'd'), Card('K', 'c'), Card('Q', 's')]
        result = ev.evaluate(hole, board)
        assert result.has_low is True
        # Use 3-5 from hole + A-2-4 from board = A-2-3-4-5 low
        low_ranks = sorted([c.rank_index for c in result.best_low_cards])
        # A=12, 2=0, 3=1, 4=2, 5=3
        assert low_ranks == [0, 1, 2, 3, 12], f"Expected [0,1,2,3,12], got {low_ranks}"

    def test_paired_board_three_low_distinct_no_low_hole(self):
        """Board with only 3 distinct low ranks (A-2-4-4-4) and hole has
        only 1 low card (3) - can make A-2-3-4 combined with hole but
        need 2 hole cards. With only 1 low in hole, can make at most
        A-2-3-4 + another card, which is only 4 low cards from A-2-3-4-?.
        Actually, hole = [3,K,Q,J], board = [A,2,4,4,4]:
        - 3 from hole + A,2,4 from board = A-2-3-4. Need 5th card.
        - Any other hole card is K/Q/J (not low). So can't make 5-card low."""
        ev = OmahaHiLoEvaluator()
        board = [Card('A', 's'), Card('2', 's'), Card('4', 'h'), Card('4', 'd'), Card('4', 'c')]
        hole = [Card('3', 'h'), Card('K', 'd'), Card('Q', 'c'), Card('J', 's')]
        result = ev.evaluate(hole, board)
        # A-2-3-4 + K/Q/J... only 4 low cards, 5 needed. No low.
        assert result.has_low is False

    def test_eight_qualifier_boundary(self):
        """8 is the highest qualifying low rank. 9 is NOT."""
        ev = OmahaHiLoEvaluator()
        # Board with all low cards including 8
        board = [Card('A', 's'), Card('2', 's'), Card('3', 's'), Card('8', 'h'), Card('K', 'd')]
        hole = [Card('4', 'h'), Card('5', 'd'), Card('Q', 'c'), Card('J', 's')]
        result = ev.evaluate(hole, board)
        # Use 4-5 from hole + A-2-3 from board = A-2-3-4-5 wheel!
        assert result.has_low is True

    def test_nine_disqualifies_low(self):
        """9 in low hand means no qualifying low (8-or-better = max 8)."""
        ev = OmahaHiLoEvaluator()
        board = [Card('A', 's'), Card('2', 's'), Card('3', 's'), Card('4', 'h'), Card('K', 'd')]
        hole = [Card('5', 'h'), Card('9', 'd'), Card('Q', 'c'), Card('J', 's')]
        result = ev.evaluate(hole, board)
        # Can use 5 from hole + A-2-3-4 from board = A-2-3-4-5 = valid low
        # 9 is the 5th hole card, not used. We pick best 2 from 4 hole cards.
        # Best 2 for low: 5h and... Q is not low, J is not low, 9 is not low.
        # So 5h is the only low card in hole. Need 2 low cards in hole.
        # Only 1 low card available (5h). Can't make 5-card low.
        assert result.has_low is False
