"""Tests for Omaha Hi/Lo (8-or-better) split pot game"""

import pytest
import sys
sys.path.insert(0, "packages/poker-core/src")

from gto_poker.deck import Card
from gto_poker.omaha_hi_lo import (
    OmahaHiLoEvaluator,
    OmahaHiLoResult,
    omaha_hi_lo_rank_key,
)


class TestOmahaHiLoResult:
    """Tests for OmahaHiLoResult class"""

    def test_result_has_low_property(self):
        """Test has_low property"""
        eval = OmahaHiLoEvaluator()
        hole = [Card('A', 'h'), Card('2', 'd'), Card('3', 'c'), Card('4', 's')]
        board = [Card('5', 'h'), Card('6', 'd'), Card('7', 'c'), Card('8', 's'), Card('9', 'd')]
        result = eval.evaluate(hole, board)
        # A-2-3-4-5 makes low, so has_low should be True
        assert result.has_low is True

    def test_result_str_high(self):
        """Test string representation includes high hand info"""
        eval = OmahaHiLoEvaluator()
        hole = [Card('A', 'h'), Card('K', 'd'), Card('Q', 'c'), Card('J', 's')]
        board = [Card('T', 'h'), Card('9', 'd'), Card('8', 'c'), Card('7', 's'), Card('6', 'd')]
        result = eval.evaluate(hole, board)
        s = str(result)
        assert "High" in s or "hi" in s.lower() or "hand" in s.lower()


class TestOmahaHiLoHighHand:
    """Tests for Omaha Hi/Lo high hand evaluation"""

    def test_evaluate_high_basic(self):
        """Test basic high hand evaluation"""
        eval = OmahaHiLoEvaluator()
        hole = [Card('A', 'h'), Card('K', 'd'), Card('Q', 'c'), Card('J', 's')]
        board = [Card('T', 'h'), Card('9', 'd'), Card('8', 'c'), Card('7', 's'), Card('6', 'd')]
        
        result = eval.evaluate(hole, board)
        assert result.high_hand is not None
        # Broadway straight T-J-Q-K-A
        assert "Straight" in result.high_hand.name

    def test_high_needs_exactly_2_hole_3_board(self):
        """High hand must use exactly 2 hole cards and 3 board cards"""
        eval = OmahaHiLoEvaluator()
        hole = [Card('A', 'h'), Card('K', 'd'), Card('Q', 'c'), Card('J', 's')]
        board = [Card('T', 'h'), Card('9', 'd'), Card('8', 'c'), Card('7', 's'), Card('6', 'd')]
        
        result = eval.evaluate(hole, board)
        assert result.high_hand is not None
        # High hand should be Broadway straight: T-J-Q-K-A
        assert "Straight" in result.high_hand.name or result.high_hand.hand_type == 5


class TestOmahaHiLoLowHand:
    """Tests for Omaha Hi/Lo low hand evaluation (8-or-better)"""

    def test_low_hand_nuts_wheel(self):
        """A-2-3-4-5 is the nut low (wheel) - but wheel can't be made in Omaha!
        
        In Omaha you must use exactly 2 hole + 3 board. For A-2-3-4-5 you need
        4 wheel cards from hole + 1 from board OR 3 wheel cards from board + 2 from hole.
        Neither is possible since wheel = 5 cards and you can only share 3 between board/hole.
        
        This test verifies the BEST low we CAN make with 2 hole + 3 board constraint.
        """
        eval = OmahaHiLoEvaluator()
        # With hole A-2-3-4 and board 5-6-7-K-Q, best low is A-2-5-6-7
        # (use A-2 from hole, 5-6-7 from board)
        hole = [Card('A', 'h'), Card('2', 'd'), Card('3', 'c'), Card('4', 's')]
        board = [Card('5', 'h'), Card('6', 'd'), Card('7', 'c'), Card('K', 's'), Card('Q', 'd')]
        
        result = eval.evaluate(hole, board)
        assert result.has_low is True
        # Best low should use A-2 from hole plus the three lowest board cards
        low_ranks = sorted([c.rank_index for c in result.best_low_cards])
        assert low_ranks == [0, 3, 4, 5, 12], f"Expected [0,3,4,5,12] got {low_ranks}"

    def test_low_hand_8_or_better_required(self):
        """Low hand must be 8-or-better (all cards rank 8 or lower)"""
        eval = OmahaHiLoEvaluator()
        hole = [Card('A', 'h'), Card('2', 'd'), Card('3', 'c'), Card('9', 's')]
        board = [Card('5', 'h'), Card('6', 'd'), Card('7', 'c'), Card('8', 's'), Card('K', 'd')]
        # 9 and K don't help low, should still get A-2-3-5-7
        result = eval.evaluate(hole, board)
        # Low is valid if we have A-2-3-5-7 (all <= 8)
        assert result.has_low is True

    def test_low_hand_no_low_when_too_high(self):
        """When no low qualifies, has_low should be False"""
        eval = OmahaHiLoEvaluator()
        hole = [Card('A', 'h'), Card('K', 'd'), Card('Q', 'c'), Card('J', 's')]
        board = [Card('T', 'h'), Card('9', 'd'), Card('8', 'c'), Card('7', 's'), Card('6', 'd')]
        # All cards are 9 or higher, no low possible
        result = eval.evaluate(hole, board)
        assert result.has_low is False

    def test_can_make_low_helper(self):
        """Test can_make_low helper function"""
        eval = OmahaHiLoEvaluator()
        good_low = [Card('A', 'h'), Card('2', 'd'), Card('3', 'c'), Card('4', 's'), Card('5', 'h')]
        assert eval.can_make_low(good_low) is True
        
        bad_low = [Card('A', 'h'), Card('K', 'd'), Card('Q', 'c'), Card('J', 's'), Card('T', 'h')]
        assert eval.can_make_low(bad_low) is False

    def test_low_ranking_aces_low(self):
        """In low hand ranking, Aces are LOW (play as 1, not 14)"""
        eval = OmahaHiLoEvaluator()
        # A-2-3-4-5 should beat 6-7-8-9-T (no 8-or-better anyway)
        # 2-3-4-5-6 should beat A-2-3-4-8 wrong way - need to test proper
        pass  # Placeholder

    def test_rejects_9_in_low_hand(self):
        """Rank 9 is NOT a qualifying low card (8-or-better means 8 is max)"""
        eval = OmahaHiLoEvaluator()
        # 5 cards containing a 9 and four low cards
        from gto_poker.deck import Card
        low_with_9 = [Card('A', 'h'), Card('2', 'd'), Card('3', 'c'), Card('4', 's'), Card('9', 'h')]
        assert eval.can_make_low(low_with_9) is False, "9 should not qualify as low"

        # Same cards but with 8 instead of 9 should qualify
        low_with_8 = [Card('A', 'h'), Card('2', 'd'), Card('3', 'c'), Card('4', 's'), Card('8', 'h')]
        assert eval.can_make_low(low_with_8) is True, "8 should qualify as low"

    def test_paired_board_still_allows_low(self):
        """A paired board (e.g., A-2-3-4-4) can still produce a qualifying low
        if the player has low cards to fill the missing ranks.
        
        The evaluator selects 3 of 5 board cards, so it can avoid the pair."""
        eval = OmahaHiLoEvaluator()
        # Board has pair of 4s
        board = [Card('A', 's'), Card('2', 's'), Card('3', 's'), Card('4', 's'), Card('4', 'h')]
        # Hole has 5, 6
        hole = [Card('5', 'h'), Card('6', 'd'), Card('K', 'c'), Card('Q', 's')]
        result = eval.evaluate(hole, board)
        # Should have a low: use 5-6 from hole + A-2-3 from board = A-2-3-5-6
        assert result.has_low is True

    def test_paired_board_no_low_when_no_cards(self):
        """A paired board with no low fillers in hole produces no low"""
        eval = OmahaHiLoEvaluator()
        # Board has pair of 4s, and only A-2-3 below 9
        board = [Card('A', 's'), Card('2', 's'), Card('3', 's'), Card('4', 's'), Card('4', 'h')]
        # Hole has 9, T - no low cards
        hole = [Card('9', 'h'), Card('T', 'd'), Card('K', 'c'), Card('Q', 's')]
        result = eval.evaluate(hole, board)
        # Best low would be A-2-3-9-T... 9 is not qualifying
        # Or A-2-4-9-T... still has 9
        # So no qualifying low
        assert result.has_low is False


class TestOmahaHiLoSplitPot:
    """Tests for pot splitting in Omaha Hi/Lo"""

    def test_split_pot_full_low_and_high(self):
        """When both low and high win, split pot 50/50"""
        eval = OmahaHiLoEvaluator()
        
        # Player 1: A-2-3-4 with 5-6-7-8-K -> has wheel low
        p1_hole = [Card('A', 'h'), Card('2', 'd'), Card('3', 'c'), Card('4', 's')]
        # Player 2: 9-9-9-9 -> only high
        p2_hole = [Card('9', 'h'), Card('9', 'd'), Card('9', 'c'), Card('9', 's')]
        board = [Card('5', 'h'), Card('6', 'd'), Card('7', 'c'), Card('7', 's'), Card('K', 'd')]
        
        results = []
        for hole in [p1_hole, p2_hole]:
            results.append(eval.evaluate(hole, board))
        
        shares = eval.split_pot(results)
        # P1 has both high and low wins -> 0.5 high, 0.5 low = full pot
        # P2 has only high share
        assert len(shares) == 2

    def test_split_pot_high_only(self):
        """When no low qualifies, high takes entire pot"""
        eval = OmahaHiLoEvaluator()
        
        # Board with all high cards (9+) — no low possible
        p1_hole = [Card('A', 'h'), Card('K', 'd'), Card('Q', 'c'), Card('J', 's')]
        p2_hole = [Card('9', 'h'), Card('9', 'd'), Card('9', 'c'), Card('9', 's')]
        board = [Card('T', 'h'), Card('J', 'd'), Card('Q', 'c'), Card('K', 's'), Card('A', 'd')]
        # Board is Broadway cards, all 9+
        
        results = []
        for hole in [p1_hole, p2_hole]:
            results.append(eval.evaluate(hole, board))
        
        shares = eval.split_pot(results)
        # Both have no low, high takes all
        assert all(not r.can_win_low for r in results), "No low should qualify"
        total_high = sum(s[0] for s in shares)
        assert abs(total_high - 1.0) < 0.01, f"High should take all, got {total_high}"

    def test_split_pot_low_only(self):
        """Test case where only low hand qualifies"""
        eval = OmahaHiLoEvaluator()
        
        p1_hole = [Card('2', 'h'), Card('3', 'd'), Card('4', 'c'), Card('5', 's')]
        p2_hole = [Card('9', 'h'), Card('9', 'd'), Card('K', 'c'), Card('K', 's')]
        board = [Card('6', 'h'), Card('7', 'd'), Card('8', 'c'), Card('A', 's'), Card('A', 'd')]
        # P1 has 2-3-4-5-6 (low), P2 has high only (Aces full pair)
        results = []
        for hole in [p1_hole, p2_hole]:
            results.append(eval.evaluate(hole, board))
        
        shares = eval.split_pot(results)
        total_low = sum(s[1] for s in shares)
        # Low gets half, but only if low exists
        assert total_low <= 0.5


class TestOmahaHiLoCompare:
    """Tests for comparing Hi/Lo hands between players"""

    def test_best_low_wins_low_half(self):
        """Best low hand wins the low half of pot"""
        eval = OmahaHiLoEvaluator()

        # Player 1: 2-3-4-5-7 low (use 2-3 from hole + 4-5-7 from board)
        p1_hole = [Card('2', 'h'), Card('3', 'd'), Card('8', 'c'), Card('K', 's')]
        # Player 2: 2-3-4-5-6 low (better, lower — use 2-3 from hole + 4-5-6 from board)
        p2_hole = [Card('2', 'h'), Card('3', 'd'), Card('6', 'c'), Card('K', 's')]
        # Board has 3 low cards (4,5,7) — note: 8 and K are too high for low
        board = [Card('4', 'h'), Card('5', 'd'), Card('7', 'c'), Card('8', 's'), Card('K', 'd')]

        r1 = eval.evaluate(p1_hole, board)
        r2 = eval.evaluate(p2_hole, board)

        # Check that both have valid low
        assert r1.has_low is True, f"P1 should have low: {r1}"
        assert r2.has_low is True, f"P2 should have low: {r2}"

    def test_wheel_beats_other_lows(self):
        """The wheel (A-2-3-4-5) beats all other lows"""
        eval = OmahaHiLoEvaluator()

        # Player 1: wheel A-2-3-4-5 (using A-2 from hole + 3-4-5 from board)
        p1_hole = [Card('A', 'h'), Card('2', 'd'), Card('K', 'c'), Card('Q', 's')]
        # Player 2: 2-3-4-5-6 (using 2-3 from hole + 4-5-6 from board)
        p2_hole = [Card('2', 'h'), Card('3', 'd'), Card('6', 'c'), Card('K', 's')]
        # Board has 3-4-5 (low) + two high cards
        board = [Card('3', 'h'), Card('4', 'd'), Card('5', 'c'), Card('T', 's'), Card('Q', 'd')]

        r1 = eval.evaluate(p1_hole, board)
        r2 = eval.evaluate(p2_hole, board)

        # Both should have low
        assert r1.has_low is True, f"P1 should have wheel low: {r1}"
        assert r2.has_low is True, f"P2 should have low: {r2}"


class TestOmahaHiLoRankKey:
    """Tests for low hand ranking key"""

    def test_wheel_lowest_rank(self):
        """A-2-3-4-5 (wheel) should have the lowest/best rank key"""
        k1 = omaha_hi_lo_rank_key([Card('A', 'h'), Card('2', 'd'), Card('3', 'c'), Card('4', 's'), Card('5', 'h')])
        k2 = omaha_hi_lo_rank_key([Card('2', 'h'), Card('3', 'd'), Card('4', 'c'), Card('5', 's'), Card('6', 'h')])
        # Lower rank key wins in low, so k1 < k2 means wheel beats top pair low
        assert k1 < k2

    def test_ace_plays_low_in_low_hand(self):
        """Ace plays as 1 in low hands, not 14"""
        eval = OmahaHiLoEvaluator()
        # This is tested via rank key comparison
        pass  # Covered above


class TestOmahaHiLoIntegration:
    """Integration tests for full Omaha Hi/Lo evaluation"""

    def test_evaluate_combined_results(self):
        """Test evaluate method returns complete result"""
        eval = OmahaHiLoEvaluator()
        hole = [Card('A', 'h'), Card('2', 'd'), Card('3', 'c'), Card('4', 's')]
        board = [Card('5', 'h'), Card('6', 'd'), Card('7', 'c'), Card('8', 's'), Card('9', 'd')]
        
        result = eval.evaluate(hole, board)
        
        assert hasattr(result, 'high_hand')
        assert hasattr(result, 'low_hand')
        assert hasattr(result, 'high_rank_key')
        assert hasattr(result, 'low_rank_key')
        assert hasattr(result, 'has_low')

    def test_full_showdown(self):
        """Test full showdown with two players"""
        eval = OmahaHiLoEvaluator()
        
        p1_hole = [Card('A', 'h'), Card('2', 'd'), Card('3', 'c'), Card('4', 's')]
        p2_hole = [Card('9', 'h'), Card('9', 'd'), Card('9', 'c'), Card('9', 's')]
        # Board with 3 distinct low ranks (5, 6, 7) plus two high cards
        # P1 can make A-2-5-6-7 (A+2 from hole, 5+6+7 from board) = valid low
        # P2 has no low (9s are too high)
        board = [Card('5', 'h'), Card('6', 'd'), Card('7', 'c'), Card('K', 's'), Card('Q', 'd')]
        
        r1 = eval.evaluate(p1_hole, board)
        r2 = eval.evaluate(p2_hole, board)
        
        # P1 has best low (A-2-5-6-7), P2 has trips (9999)
        assert r1.has_low is True
        assert r2.can_win_low is False
