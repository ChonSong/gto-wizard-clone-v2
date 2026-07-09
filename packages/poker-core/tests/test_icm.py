"""Tests for ICM (Independent Chip Model) calculator."""

import pytest
from gto_poker.icm import (
    ICMResult,
    malmoud_harville,
    calculate_bubble_factor,
    icm_calculate,
    icm_equity_chips,
)


class TestMalmoudHarville:
    """Malmoud-Harville tie-handling equity formula."""

    def test_basic_calculation(self):
        """Big stack should have most equity."""
        stacks = [3000.0, 2000.0, 1000.0]
        prizes = [0.5, 0.3, 0.2]

        equity = malmoud_harville(stacks, prizes, n_simulations=5000, seed=42)

        assert equity[0] > equity[1] > equity[2]
        assert abs(sum(equity) - 1.0) < 0.001

    def test_equal_stacks(self):
        """Equal stacks: each player has equal probability of each finish place.

        With 1000 chips each (1/3 of total), expected equity = sum(p_i * prize_i)
        = 1/3 * 0.5 + 1/3 * 0.3 + 1/3 * 0.2 ≈ 0.333.
        """
        stacks = [1000.0, 1000.0, 1000.0]
        prizes = [0.5, 0.3, 0.2]

        equity = malmoud_harville(stacks, prizes, n_simulations=5000, seed=42)

        # All equal, each gets ~1/3 of equity = 0.333
        assert abs(equity[0] - equity[1]) < 0.002
        assert abs(equity[1] - equity[2]) < 0.002

    def test_single_player(self):
        """Single player gets all equity."""
        stacks = [5000.0]
        prizes = [1.0]

        equity = malmoud_harville(stacks, prizes, n_simulations=5000, seed=42)

        assert abs(equity[0] - 1.0) < 0.001

    def test_empty_players(self):
        """Empty player list raises ValueError."""
        with pytest.raises(ValueError, match="Number of stacks and prizes must match"):
            malmoud_harville([], [1.0])

    def test_seed_reproducibility(self):
        """Same seed produces same results."""
        stacks = [3000.0, 2000.0, 1000.0]
        prizes = [0.5, 0.3, 0.2]

        result1 = malmoud_harville(stacks, prizes, n_simulations=5000, seed=12345)
        result2 = malmoud_harville(stacks, prizes, n_simulations=5000, seed=12345)

        for v1, v2 in zip(result1, result2):
            assert abs(v1 - v2) < 1e-6

    def test_invalid_prizes(self):
        """Mismatched prizes length raises ValueError."""
        stacks = [1000.0, 1000.0]
        prizes = [1.0]

        with pytest.raises(ValueError, match="Number of stacks and prizes must match"):
            malmoud_harville(stacks, prizes)


class TestCalculateBubbleFactor:
    """Bubble factor calculation."""

    def test_equal_stacks_bubble_factor_one(self):
        """Equal stacks have bubble factor of 1.0."""
        stacks = [3333.0, 3333.0, 3333.0]
        prizes = [0.5, 0.3, 0.2]

        bf = calculate_bubble_factor(stacks, prizes, player_idx=0, n_simulations=5000, seed=42)
        assert abs(bf - 1.0) < 0.01

    def test_short_stack_bubbles_harder(self):
        """Short stack has higher bubble factor than big stack."""
        stacks = [8000.0, 1500.0, 500.0]
        prizes = [0.5, 0.3, 0.2]

        bf_short = calculate_bubble_factor(stacks, prizes, player_idx=2, n_simulations=5000, seed=42)
        bf_big = calculate_bubble_factor(stacks, prizes, player_idx=0, n_simulations=5000, seed=42)

        assert bf_short > bf_big
        assert bf_short > 1.0

    def test_invalid_player_index(self):
        """Invalid player index raises ValueError."""
        stacks = [1000.0, 1000.0, 1000.0]
        prizes = [0.5, 0.3, 0.2]

        with pytest.raises(ValueError, match="Invalid player index"):
            calculate_bubble_factor(stacks, prizes, player_idx=5)


class TestICMCalculate:
    """Main ICM calculation entry point."""

    def test_basic_calculation(self):
        """Returns list of ICMResult."""
        stacks = [3000.0, 2000.0, 1000.0]
        prizes = [500.0, 300.0, 200.0]
        players = ["Big", "Mid", "Short"]

        results = icm_calculate(stacks, prizes, players=players, n_simulations=5000, seed=42)

        assert len(results) == 3
        assert all(isinstance(r, ICMResult) for r in results)

    def test_equity_sums_to_prize_pool(self):
        """Total equity equals sum of prizes."""
        stacks = [3000.0, 2000.0, 1000.0]
        prizes = [500.0, 300.0, 200.0]
        players = ["P1", "P2", "P3"]

        results = icm_calculate(stacks, prizes, players=players, n_simulations=5000, seed=42)

        total = sum(r.equity for r in results)
        assert abs(total - sum(prizes)) < 0.01

    def test_prize_extension(self):
        """Short prize list extended proportionally."""
        stacks = [5000.0, 3000.0, 2000.0]
        prizes = [500.0, 300.0]  # 2 prizes for 3 players
        players = ["P1", "P2", "P3"]

        results = icm_calculate(stacks, prizes, players=players, n_simulations=5000, seed=42)
        total = sum(r.equity for r in results)
        assert abs(total - 800.0) < 0.01


class TestICMEquityChips:
    """Simple chip-proportional equity."""

    def test_proportional_equity(self):
        """Returns fractions, not absolute values."""
        stacks = [6000.0, 3000.0, 1000.0]
        total = sum(stacks)

        equity = icm_equity_chips(stacks, total)

        assert abs(equity[0] - 0.6) < 0.01
        assert abs(equity[1] - 0.3) < 0.01
        assert abs(equity[2] - 0.1) < 0.01

    def test_equal_stacks(self):
        """Equal stacks get equal equity."""
        stacks = [3333.0, 3333.0, 3334.0]
        total = sum(stacks)

        equity = icm_equity_chips(stacks, total)

        assert abs(equity[0] - equity[1]) < 0.01


class TestICMEdgeCases:
    """Boundary conditions."""

    def test_two_player_icm(self):
        """Heads-up ICM."""
        stacks = [7000.0, 3000.0]
        prizes = [700.0, 300.0]
        players = ["HU1", "HU2"]

        results = icm_calculate(stacks, prizes, players=players, n_simulations=5000, seed=42)

        assert len(results) == 2
        assert results[0].equity > results[1].equity

    def test_nine_max_icm(self):
        """9-max table ICM."""
        stacks = [5000.0, 4000.0, 3000.0, 2000.0, 1500.0, 1000.0, 800.0, 500.0, 200.0]
        prizes = [500.0, 300.0, 150.0, 50.0]
        players = [f"P{i}" for i in range(9)]

        results = icm_calculate(stacks, prizes, players=players, n_simulations=5000, seed=42)

        assert len(results) == 9
        assert results[0].equity > results[-1].equity

    def test_zero_stack(self):
        """Zero stack player has zero chip equity."""
        stacks = [5000.0, 0.0, 5000.0]
        prizes = [500.0, 300.0, 200.0]
        players = ["P1", "P2", "P3"]

        results = icm_calculate(stacks, prizes, players=players, n_simulations=5000, seed=42)

        # Player with 0 chips gets 0 chip_equity
        zero_players = [r for r in results if r.chip_equity == 0.0]
        assert len(zero_players) >= 1
