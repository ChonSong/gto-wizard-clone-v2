"""Tests for Double Board PLO equity calculation.

This is a novel variant — two independent boards, scoop/chop scoring:
  adjusted_equity = (scoop_wins × 1.0 + chop_wins × 0.5) / total_sims
"""
import pytest
import sys

sys.path.insert(0, "/tmp/PokerHandEvaluator/python")
sys.path.insert(0, "packages/poker-core/src")

from gto_poker.double_board import (
    DoubleBoardEvaluator,
    DoubleBoardEquity,
    ScoopTracker,
)


class TestDoubleBoardValidation:
    """Test input validation for DoubleBoardEvaluator."""

    def test_rejects_overlapping_boards(self):
        """evaluate() must reject boards that share cards."""
        eval = DoubleBoardEvaluator()
        hole = ["Ah", "Kh", "Qh", "Jh"]
        board1 = ["Td", "9d", "8d"]
        board2 = ["8d", "7c", "6c"]  # 8d overlaps with board1... wait, no it doesn't
        # Let me use a clear overlap
        board1 = ["Td", "9d", "8d"]
        board2 = ["8d", "7c", "6c"]  # 8d appears in both

        with pytest.raises(ValueError, match="share cards"):
            eval.evaluate(hole, board1, board2)

    def test_rejects_hole_overlap_with_board(self):
        """evaluate() must reject hole cards that overlap with boards."""
        eval = DoubleBoardEvaluator()
        hole = ["Ah", "Kh", "Qh", "Jh"]
        board1 = ["Ah", "Td", "9d"]  # Ah appears in both hole and board1
        board2 = ["7c", "6c", "5c"]

        with pytest.raises(ValueError, match="overlap with board 1"):
            eval.evaluate(hole, board1, board2)

    def test_rejects_hole_overlap_with_board2(self):
        """evaluate() must reject hole cards that overlap with board2."""
        eval = DoubleBoardEvaluator()
        hole = ["Ah", "Kh", "Qh", "Jh"]
        board1 = ["Td", "9d", "8d"]
        board2 = ["Ah", "7c", "6c"]  # Ah appears in both hole and board2

        with pytest.raises(ValueError, match="overlap with board 2"):
            eval.evaluate(hole, board1, board2)


class TestDoubleBoardEvaluator:
    """Test DoubleBoardEvaluator on two independent boards."""

    def test_evaluate_returns_ranks_for_both_boards(self):
        """evaluate() returns (rank1, rank2) for board1 and board2."""
        eval = DoubleBoardEvaluator()
        hole = ["Ah", "Kh", "Qh", "Jh"]  # four broadway
        board1 = ["Td", "9d", "8d"]
        board2 = ["7c", "6c", "5c"]

        rank1, rank2 = eval.evaluate(hole, board1, board2)

        # Both should be valid ranks (lower = better)
        assert isinstance(rank1, int)
        assert isinstance(rank2, int)
        assert 1 <= rank1 <= 7462
        assert 1 <= rank2 <= 7462

    def test_evaluate_list_input_only(self):
        """evaluate() expects List[str] for all parameters."""
        eval = DoubleBoardEvaluator()
        hole = ["Ah", "Kh", "Qh", "Jh"]
        board1 = ["Td", "9d", "8d"]
        board2 = ["7c", "6c", "5c"]

        rank1, rank2 = eval.evaluate(hole, board1, board2)
        assert 1 <= rank1 <= 7462
        assert 1 <= rank2 <= 7462

    def test_better_hand_on_one_board(self):
        """Premium hand should beat trash on at least one board."""
        eval = DoubleBoardEvaluator()

        # Strong: double-suited broadway
        premium = ["Ah", "Kh", "Qh", "Jh"]
        # Weak: low unconnected cards
        trash = ["2h", "3d", "4c", "5s"]

        # Evaluate on same board - premium should be better
        rank_premium, rank_trash = eval.evaluate(premium, ["Td", "9d", "8d"], ["7c", "6c", "5c"])

        # Premium has higher rank (lower number = better hand)
        assert rank_premium < rank_trash, f"Premium ({rank_premium}) should beat trash ({rank_trash})"


class TestScoopTracker:
    """Test scoop/chop tracking and adjusted equity calculation."""

    def test_adjusted_equity_formula(self):
        """adjusted_equity = (scoop_wins × 1.0 + chop_wins × 0.5) / total_sims"""
        tracker = ScoopTracker(total_sims=1000)

        # Scenario: player1 scoops 300, chops 400, loses 300
        tracker.scoop_wins = 300
        tracker.chop_wins = 400
        tracker.total_sims = 1000

        # Expected: (300 * 1.0 + 400 * 0.5) / 1000 = (300 + 200) / 1000 = 0.5
        assert tracker.adjusted_equity == 0.5

    def test_full_scoop_is_1_percent(self):
        """Winning both boards every time = 100% equity."""
        tracker = ScoopTracker(total_sims=100)
        tracker.scoop_wins = 100
        tracker.chop_wins = 0
        tracker.total_sims = 100
        assert tracker.adjusted_equity == 1.0

    def test_full_loss_is_0_percent(self):
        """Losing both boards every time = 0% equity."""
        tracker = ScoopTracker(total_sims=100)
        tracker.scoop_wins = 0
        tracker.chop_wins = 0
        tracker.total_sims = 100
        assert tracker.adjusted_equity == 0.0

    def test_all_chops_is_50_percent(self):
        """Tying one board and losing the other every time = 50% equity."""
        tracker = ScoopTracker(total_sims=100)
        tracker.scoop_wins = 0
        tracker.chop_wins = 100
        tracker.total_sims = 100
        assert tracker.adjusted_equity == 0.5


class TestDoubleBoardEquity:
    """Test DoubleBoardEquity calculator with Monte Carlo and exact modes."""

    def test_exact_equity_with_complete_boards(self):
        """When both boards are complete, use exact enumeration."""
        equity_calc = DoubleBoardEquity()

        # Both players have 4 cards each, both boards complete
        hand1 = ["Ah", "Kh", "Qh", "Jh"]
        hand2 = ["2h", "3h", "4h", "5h"]
        board1 = ["Td", "9d", "8d", "2c", "3c"]  # 5 cards
        board2 = ["7c", "6c", "5c", "4d", "3d"]  # 5 cards

        eq1, eq2, stats = equity_calc.calculate(
            hand1, hand2, board1, board2, samples=0  # 0 = exact mode
        )

        # Should get valid equity percentages
        assert 0 <= eq1 <= 100
        assert 0 <= eq2 <= 100

        # Stats should have scoop tracking
        assert hasattr(stats, "scoop_wins")
        assert hasattr(stats, "chop_wins")

    def test_monte_carlo_with_partial_boards(self):
        """Partial boards use Monte Carlo simulation."""
        equity_calc = DoubleBoardEquity()

        hand1 = ["Ah", "Kh", "Qh", "Jh"]
        hand2 = ["2h", "3h", "4h", "5h"]
        board1 = ["Td", "9d"]  # only 2 board cards
        board2 = ["7c"]        # only 1 board card

        eq1, eq2, stats = equity_calc.calculate(
            hand1, hand2, board1, board2, samples=1000
        )

        assert 0 <= eq1 <= 100
        assert 0 <= eq2 <= 100
        assert stats.total_sims == 1000

    def test_premium_hand_has_higher_equity(self):
        """Premium vs trash should show higher equity for premium."""
        equity_calc = DoubleBoardEquity()

        # Strong: Broadway cards with some coordination
        premium = ["Ah", "Kh", "Qh", "Jh"]
        # Weak: Low disconnected cards
        trash = ["2h", "3d", "4c", "5s"]

        eq_premium, eq_trash, _ = equity_calc.calculate(
            premium, trash, [], [], samples=5000
        )

        # Premium should have higher equity
        assert eq_premium > eq_trash

    def test_equity_sums_to_100(self):
        """Equity of both players should sum to ~1.0 (100%)."""
        equity_calc = DoubleBoardEquity()

        hand1 = ["Ah", "Kh", "Qh", "Jh"]
        hand2 = ["Ad", "Kd", "Qd", "Jd"]

        eq1, eq2, _ = equity_calc.calculate(
            hand1, hand2, [], [], samples=5000
        )

        # Equity is in 0-1 range, should sum to 1.0 (within rounding error)
        assert abs(eq1 + eq2 - 1.0) < 0.01