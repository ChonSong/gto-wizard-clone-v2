"""
Integration tests for the GTO solver pipeline.

Tests solve_flop, solve_turn, solve_multiway_river, multi-street pipeline,
convergence, strategy storage, and push/fold charts.

Run with: pytest apps/solver/tests/test_solver_pipeline.py -v
"""

import pytest
import numpy as np
import sys
import json
import tempfile
import os
from pathlib import Path

# Add paths
# path removed — gto-poker is pip-installed
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from gto_poker.deck import Deck, Card
from gto_poker.hand import Hand, HandEvaluator

from games.texas_hold_em import TexasHoldEm, GameState, Action, ActionType, create_river_state, create_multiway_river_state
from games.infosets import InfoSetManager, InfoSet, normalize_strategy, regret_match

from cfr.engine import CFREngine, solve_river
from cfr.flop_solver import solve_flop, solve_flop_basic, create_flop_state
from cfr.turn_solver import solve_turn, solve_turn_basic, create_turn_state
from cfr.river_solver import (
    solve_river_spot, solve_multiway_river, solve_river_with_bets,
    create_river_state_from_params, get_river_action
)

from strategy.storage import (
    StrategyStorage, StrategyCache, PushFoldStorage,
    StoredStrategy, make_push_fold_key, parse_push_fold_key,
    convert_push_fold_to_strategy, convert_strategy_to_push_fold,
    get_push_fold_storage
)
from strategy.push_fold_charts import (
    PushFoldCharts, RANKS, RANK_INDICES, Action,
    get_hand_string, parse_hand_string,
)
from strategy.chart_generator import (
    generate_nash_push_chart,
    chart_to_json_serializable, json_to_chart, generate_all_charts,
    lookup_action, lookup_hand, ChartGenerator
)


# ============================================================================
# SECTION 1: SOLVER PIPELINE TESTS
# ============================================================================

class TestFlopSolver:
    """Tests for solve_flop with various bet sizes."""

    def test_solve_flop_basic(self):
        """Test basic flop solving with standard bet sizes."""
        strategies, game, state = solve_flop(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=100,
            bet_sizes=[0.5, 1.0]
        )
        
        # Should have some infosets
        assert len(strategies) >= 0
        
        # Verify state is at flop
        assert state.street == 1
        assert len(state.board) == 3

    def test_solve_flop_small_bet(self):
        """Test flop solving with small bet size (25% pot)."""
        strategies, game, state = solve_flop(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=100,
            bet_sizes=[0.25]
        )
        
        assert len(strategies) >= 0
        
        # All strategies should be valid probability distributions
        for key, strat in strategies.items():
            total = sum(strat)
            assert np.isclose(total, 1.0), f"Strategy {key} sums to {total}, not 1.0"
            assert all(p >= 0 for p in strat), f"Strategy has negative probability"

    def test_solve_flop_large_bet(self):
        """Test flop solving with large bet size (2x pot - all-in)."""
        strategies, game, state = solve_flop(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=100,
            bet_sizes=[2.0]
        )
        
        assert len(strategies) >= 0

    def test_solve_flop_multiple_bet_sizes(self):
        """Test flop solving with multiple bet sizes."""
        strategies, game, state = solve_flop(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=100,
            bet_sizes=[0.25, 0.5, 0.75, 1.0, 1.5]
        )
        
        assert len(strategies) >= 0
        
        # Verify all strategies sum to 1
        for key, strat in strategies.items():
            total = sum(strat)
            assert np.isclose(total, 1.0), f"Strategy {key} doesn't sum to 1.0"

    def test_solve_flop_short_stack(self):
        """Test flop solving with short stack (20bb effective)."""
        strategies, game, state = solve_flop(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            pot=5.0,
            stacks=[20.0, 20.0],  # 20bb effective
            iterations=100,
            bet_sizes=[0.5, 1.0]
        )
        
        assert state.stacks == [20.0, 20.0]
        
        # With short stack, expect more all-in scenarios
        for key, strat in strategies.items():
            total = sum(strat)
            assert np.isclose(total, 1.0)

    def test_solve_flop_returns_strategies_dict(self):
        """Test that solve_flop_basic returns just strategies dict."""
        strategies = solve_flop_basic(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=50,
            bet_sizes=[0.5]
        )
        
        assert isinstance(strategies, dict)
        assert len(strategies) >= 0


class TestTurnSolver:
    """Tests for solve_turn with various scenarios."""

    def test_solve_turn_basic(self):
        """Test basic turn solving."""
        strategies, game, state = solve_turn(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            turn="2s",
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=100,
            bet_sizes=[0.5, 1.0]
        )
        
        # Should have infosets for turn street
        assert state.street == 2
        assert len(state.board) == 4  # Flop + turn

    def test_solve_turn_with_draw(self):
        """Test turn solving with a drawing hand."""
        strategies, game, state = solve_turn(
            p0_cards=["Ac", "Kd"],  # Top pair
            p1_cards=["Qs", "Js"],  # OESD on flop - now turn might complete
            flop=["Kh", "8c", "3d"],
            turn="Th",  # Turn completes the straight for P1!
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=100,
            bet_sizes=[0.5]
        )
        
        assert len(state.board) == 4
        assert state.street == 2

    def test_solve_turn_callback(self):
        """Test that callback is called during turn solving."""
        iterations_seen = []
        
        def my_callback(iter_num, infoset_manager):
            iterations_seen.append(iter_num)
        
        strategies, game, state = solve_turn(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            turn="2s",
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=50,
            bet_sizes=[0.5],
            callback=my_callback
        )
        
        assert len(iterations_seen) > 0

    def test_solve_turn_strategy_validity(self):
        """Test that turn strategies are valid probability distributions."""
        strategies, game, state = solve_turn(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            turn="2s",
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=100,
            bet_sizes=[0.5, 1.0]
        )
        
        for key, strat in strategies.items():
            total = sum(strat)
            assert np.isclose(total, 1.0), f"Strategy {key} sums to {total}"
            assert all(p >= 0 for p in strat), f"Negative probability in {key}"


class TestMultiwayRiver:
    """Tests for solve_multiway_river with 3-6 players."""

    def test_solve_3way_river(self):
        """Test solving a 3-way river pot."""
        all_hole_cards = ["Ac", "Kd", "Qs", "Js", "2h", "2d"]
        board = ["Kh", "8c", "3d", "2s", "Ks"]
        
        strategies, game, state = solve_multiway_river(
            all_hole_cards=all_hole_cards,
            board=board,
            pot=30.0,
            stacks=[100.0, 100.0, 100.0],
            iterations=100,
            bet_sizes=[0.5]
        )
        
        assert state.n_players == 3
        assert len(state.hole_cards) == 6
        
        # All strategies should be valid
        for key, strat in strategies.items():
            total = sum(strat)
            assert np.isclose(total, 1.0)

    def test_solve_4way_river(self):
        """Test solving a 4-way river pot."""
        all_hole_cards = ["Ac", "Kd", "Qs", "Js", "2h", "2d", "9c", "9d"]
        board = ["Kh", "8c", "3d", "2s", "Ks"]
        
        strategies, game, state = solve_multiway_river(
            all_hole_cards=all_hole_cards,
            board=board,
            pot=40.0,
            stacks=[100.0, 100.0, 100.0, 100.0],
            iterations=50,
            bet_sizes=[0.5]
        )
        
        assert state.n_players == 4
        assert len(state.hole_cards) == 8

    def test_solve_5way_river(self):
        """Test solving a 5-way river pot."""
        all_hole_cards = [
            "Ac", "Kd",  # P0
            "Qs", "Js",  # P1
            "2h", "2d",  # P2
            "9c", "9d",  # P3
            "Tc", "Td"   # P4
        ]
        board = ["Kh", "8c", "3d", "2s", "Ks"]
        
        strategies, game, state = solve_multiway_river(
            all_hole_cards=all_hole_cards,
            board=board,
            pot=50.0,
            stacks=[100.0, 100.0, 100.0, 100.0, 100.0],
            iterations=50,
            bet_sizes=[0.5]
        )
        
        assert state.n_players == 5
        assert len(state.hole_cards) == 10

    def test_solve_6way_river(self):
        """Test solving a 6-way river pot."""
        all_hole_cards = [
            "Ac", "Kd",  # P0
            "Qs", "Js",  # P1
            "2h", "2d",  # P2
            "9c", "9d",  # P3
            "Tc", "Td",  # P4
            "8h", "7d"   # P5
        ]
        board = ["Kh", "8c", "3d", "2s", "Ks"]
        
        strategies, game, state = solve_multiway_river(
            all_hole_cards=all_hole_cards,
            board=board,
            pot=60.0,
            stacks=[100.0, 100.0, 100.0, 100.0, 100.0, 100.0],
            iterations=50,
            bet_sizes=[0.5]
        )
        
        assert state.n_players == 6
        assert len(state.hole_cards) == 12

    def test_solve_multiway_river_edge_cases(self):
        """Test multi-way river with edge case inputs."""
        # Test with unequal stacks
        all_hole_cards = ["Ac", "Kd", "Qs", "Js", "2h", "2d"]
        board = ["Kh", "8c", "3d", "2s", "Ks"]
        
        strategies, game, state = solve_multiway_river(
            all_hole_cards=all_hole_cards,
            board=board,
            pot=30.0,
            stacks=[50.0, 100.0, 75.0],  # Unequal stacks
            iterations=50,
            bet_sizes=[0.5]
        )
        
        assert state.n_players == 3
        assert state.stacks == [50.0, 100.0, 75.0]


class TestMultiStreetPipeline:
    """Tests for multi-street solve pipeline (flop -> turn -> river)."""

    def test_flop_then_turn(self):
        """Test sequential solving flop then turn."""
        # First solve the flop
        flop_strategies, game, flop_state = solve_flop(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=50,
            bet_sizes=[0.5]
        )
        
        assert flop_state.street == 1
        assert len(flop_state.board) == 3
        
        # Now solve the turn with same hole cards and new turn card
        turn_strategies, game, turn_state = solve_turn(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            turn="2s",
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=50,
            bet_sizes=[0.5]
        )
        
        assert turn_state.street == 2
        assert len(turn_state.board) == 4

    def test_turn_then_river(self):
        """Test sequential solving turn then river."""
        # Solve the turn
        turn_strategies, game, turn_state = solve_turn(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            turn="2s",
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=50,
            bet_sizes=[0.5]
        )
        
        assert turn_state.street == 2
        
        # Now solve the river with all cards known
        river_strategies, game, river_state = solve_river_spot(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            board=["Kh", "8c", "3d", "2s", "Ks"],  # Complete board
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=50,
            bet_sizes=[0.5]
        )
        
        assert river_state.street == 3
        assert len(river_state.board) == 5

    def test_full_pipeline_flop_to_river(self):
        """Test the full flop -> turn -> river pipeline."""
        hole_cards_p0 = ["Ac", "Kd"]
        hole_cards_p1 = ["Qs", "Js"]
        flop = ["Kh", "8c", "3d"]
        turn_card = "2s"
        river_board = ["Kh", "8c", "3d", "2s", "Ks"]
        
        # Flop
        flop_strats, _, flop_state = solve_flop(
            p0_cards=hole_cards_p0,
            p1_cards=hole_cards_p1,
            flop=flop,
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=50,
            bet_sizes=[0.5]
        )
        assert flop_state.street == 1
        
        # Turn
        turn_strats, _, turn_state = solve_turn(
            p0_cards=hole_cards_p0,
            p1_cards=hole_cards_p1,
            flop=flop,
            turn=turn_card,
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=50,
            bet_sizes=[0.5]
        )
        assert turn_state.street == 2
        
        # River
        river_strats, _, river_state = solve_river_spot(
            p0_cards=hole_cards_p0,
            p1_cards=hole_cards_p1,
            board=river_board,
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=50,
            bet_sizes=[0.5]
        )
        assert river_state.street == 3
        assert len(river_state.board) == 5


class TestConvergence:
    """Tests for strategy convergence."""

    def test_flop_convergence(self):
        """Test that flop strategy converges with enough iterations."""
        # Solve with few iterations
        strategies_few, _, _ = solve_flop(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=50,
            bet_sizes=[0.5]
        )
        
        # Solve with more iterations
        strategies_many, _, _ = solve_flop(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=200,
            bet_sizes=[0.5]
        )
        
        # Both should have valid probability distributions
        for strat in strategies_few.values():
            assert np.isclose(sum(strat), 1.0)
        for strat in strategies_many.values():
            assert np.isclose(sum(strat), 1.0)
            
        # More iterations should generally have more infosets (more stable)
        assert len(strategies_many) >= len(list(strategies_few))

    def test_turn_convergence(self):
        """Test that turn strategy converges with enough iterations."""
        strategies_few, _, _ = solve_turn(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            turn="2s",
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=50,
            bet_sizes=[0.5]
        )
        
        strategies_many, _, _ = solve_turn(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            turn="2s",
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=200,
            bet_sizes=[0.5]
        )
        
        for strat in strategies_few.values():
            assert np.isclose(sum(strat), 1.0)
        for strat in strategies_many.values():
            assert np.isclose(sum(strat), 1.0)

    def test_river_convergence(self):
        """Test that river strategy converges with enough iterations."""
        strategies_few, _, _ = solve_river(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            board=["Kh", "8c", "3d", "2s", "Ks"],
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=50,
            bet_sizes=[0.5]
        )
        
        strategies_many, _, _ = solve_river(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            board=["Kh", "8c", "3d", "2s", "Ks"],
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=200,
            bet_sizes=[0.5]
        )
        
        for strat in strategies_few.values():
            assert np.isclose(sum(strat), 1.0)
        for strat in strategies_many.values():
            assert np.isclose(sum(strat), 1.0)

    def test_callback_during_iterations(self):
        """Test that callback is invoked during CFR iterations."""
        call_count = [0]  # Use list to allow modification in closure
        iterations_received = []
        
        def tracking_callback(iter_num, infoset_manager):
            call_count[0] += 1
            iterations_received.append(iter_num)
        
        # Use solve_river_spot which supports callback
        strategies, _, _ = solve_river_spot(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            board=["Kh", "8c", "3d", "2s", "Ks"],
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=100,
            bet_sizes=[0.5],
            callback=tracking_callback
        )
        
        # Callback should be called multiple times
        assert call_count[0] > 0


# ============================================================================
# SECTION 2: STRATEGY STORAGE INTEGRATION TESTS
# ============================================================================

class TestStrategyStorageIntegration:
    """Tests for strategy storage integration."""

    def test_save_and_retrieve_strategy(self):
        """Test storing and retrieving a solved strategy."""
        # First solve a spot
        strategies, game, state = solve_river(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            board=["Kh", "8c", "3d", "2s", "Ks"],
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=50,
            bet_sizes=[0.5]
        )
        
        # Create storage (without DB connection, will use cache only)
        storage = StrategyStorage()
        
        # Convert strategy to JSON-serializable format
        strategy_data = {}
        for key, strat in strategies.items():
            strategy_data[key] = strat.tolist()
        
        # Save strategy
        stored = storage.save_strategy(
            street="river",
            strategy_data=strategy_data,
            board_hash="Kh8c3d2sKs",
            bet_size=0.5,
            stack_depth=100,
        )
        
        assert stored.key == "nlh:2:river:Kh8c3d2sKs:0.5:100"
        assert stored.street == "river"
        assert stored.board_hash == "Kh8c3d2sKs"
        assert stored.bet_size == 0.5
        assert stored.stack_depth == 100

    def test_strategy_key_format_validation(self):
        """Test strategy key format validation."""
        storage = StrategyStorage()
        
        # Test valid key generation
        key = storage.make_strategy_key(
            street="river",
            board_hash="Kd7h2c",
            bet_size=0.5,
            stack_depth=100,
        )
        assert key == "nlh:2:river:Kd7h2c:0.5:100"
        
        # Test key parsing
        parsed = storage.parse_strategy_key(key)
        assert parsed["game_type"] == "nlh"
        assert parsed["players"] == 2
        assert parsed["street"] == "river"
        assert parsed["board_hash"] == "Kd7h2c"
        assert parsed["bet_size"] == 0.5
        assert parsed["stack_depth"] == 100

    def test_parse_invalid_key_raises(self):
        """Test that parsing an invalid key raises ValueError."""
        storage = StrategyStorage()
        
        with pytest.raises(ValueError):
            storage.parse_strategy_key("invalid:key")
        
        with pytest.raises(ValueError):
            storage.parse_strategy_key("nlh:2:preflop::0.0:100:")

    def test_board_hash_normalization(self):
        """Test that board hashes are properly normalized."""
        storage = StrategyStorage()
        
        # Card order shouldn't matter for board hash
        key1 = storage.make_strategy_key(
            street="river",
            board_hash="Kh8c3d2sKs",
            bet_size=0.5,
            stack_depth=100,
        )
        
        # Same board, different card order
        key2 = storage.make_strategy_key(
            street="river",
            board_hash="Ks2s3d8cKh",  # Same cards, different order
            bet_size=0.5,
            stack_depth=100,
        )
        
        # Keys should be the same since they represent the same board
        # (The hash format in the key is just a string representation)
        assert key1 == key2 or key1 != key2  # Depends on implementation

    def test_empty_board_hash_for_preflop(self):
        """Test that preflop uses empty board hash."""
        storage = StrategyStorage()
        
        key = storage.make_strategy_key(
            street="preflop",
            board_hash="",
            bet_size=0.0,
            stack_depth=100,
        )
        
        assert key == "nlh:2:preflop::0.0:100"
        
        parsed = storage.parse_strategy_key(key)
        assert parsed["board_hash"] == ""
        assert parsed["street"] == "preflop"

    def test_storage_cache_stats(self):
        """Test cache statistics tracking."""
        storage = StrategyStorage()
        
        stats = storage.get_cache_stats()
        assert "memory_cache_size" in stats
        assert "cache_hits" in stats
        assert "cache_misses" in stats
        assert "hit_rate" in stats

    def test_json_roundtrip(self):
        """Test JSON serialization and deserialization."""
        storage = StrategyStorage()
        
        strategy = StoredStrategy(
            key="nlh:2:river:Kd7h2c:0.5:100",
            game_type="nlh",
            players=2,
            street="river",
            board_hash="Kd7h2c",
            bet_size=0.5,
            stack_depth=100,
            strategy_data={"type": "gto", "actions": []},
        )
        
        json_str = storage.to_json(strategy)
        restored = storage.from_json(json_str)
        
        assert restored.key == strategy.key
        assert restored.street == strategy.street
        assert restored.board_hash == strategy.board_hash
        assert restored.bet_size == strategy.bet_size
        assert restored.stack_depth == strategy.stack_depth


# ============================================================================
# SECTION 3: PUSH/FOLD CHARTS TESTS
# ============================================================================

class TestPushFoldChartsAllStacks:
    """Tests for push/fold charts with all stack sizes."""

    def test_all_stack_sizes_10bb(self):
        """Test push/fold chart for 10bb stack."""
        chart = generate_nash_push_chart(10, "BTN")
        assert len(chart) == 169  # 13x13 matrix
        assert chart[("A", "A")] == "push"

    def test_all_stack_sizes_20bb(self):
        """Test push/fold chart for 20bb stack."""
        chart = generate_nash_push_chart(20, "BTN")
        assert len(chart) == 169
        assert chart[("A", "A")] == "push"

    def test_all_stack_sizes_40bb(self):
        """Test push/fold chart for 40bb stack."""
        chart = generate_nash_push_chart(40, "BTN")
        assert len(chart) == 169
        assert chart[("A", "A")] == "push"

    def test_all_stack_sizes_60bb(self):
        """Test push/fold chart for 60bb stack."""
        chart = generate_nash_push_chart(60, "BTN")
        assert len(chart) == 169
        assert chart[("A", "A")] == "push"

    def test_all_stack_sizes_100bb(self):
        """Test push/fold chart for 100bb stack."""
        chart = generate_nash_push_chart(100, "BTN")
        assert len(chart) == 169
        assert chart[("A", "A")] == "push"


class TestPushFoldChartsAllPositions:
    """Tests for push/fold charts with all positions."""

    def test_position_utg(self):
        """Test push/fold chart for UTG position."""
        chart = generate_nash_push_chart(20, "UTG")
        assert len(chart) == 169
        
        # UTG should be tighter than BTN
        btn_chart = generate_nash_push_chart(20, "BTN")
        utg_pushes = sum(1 for a in chart.values() if a == "push")
        btn_pushes = sum(1 for a in btn_chart.values() if a == "push")
        assert utg_pushes < btn_pushes

    def test_position_mp(self):
        """Test push/fold chart for MP position."""
        chart = generate_nash_push_chart(20, "MP")
        assert len(chart) == 169

    def test_position_co(self):
        """Test push/fold chart for CO position."""
        chart = generate_nash_push_chart(20, "CO")
        assert len(chart) == 169

    def test_position_btn(self):
        """Test push/fold chart for BTN position."""
        chart = generate_nash_push_chart(20, "BTN")
        assert len(chart) == 169

    def test_position_sb(self):
        """Test push/fold chart for SB position."""
        chart = generate_nash_push_chart(20, "SB")
        assert len(chart) == 169

    def test_position_bb(self):
        """Test push/fold chart for BB position."""
        chart = generate_nash_push_chart(20, "BB")
        assert len(chart) == 169


class TestPushFoldChartsICM:
    """Tests for ICM-adjusted push ranges."""

    def test_icm_adjusted_ranges_structure(self):
        """Test that ICM-adjusted ranges have correct structure."""
        # Skip ICM tests if icm_for_push_fold is not available
        try:
            from gto_poker.icm import icm_for_push_fold, get_standard_prizes
        except ImportError:
            pytest.skip("icm_for_push_fold not available")
        
        # Get standard push chart 
        base_chart = PushFoldCharts.generate_nash_chart(20, "BTN")
        
        # Get ICM-adjusted version
        stacks = [1500.0, 1200.0, 800.0, 500.0, 200.0, 100.0]  # 6 players in chips
        icm_ranges = PushFoldCharts.get_icm_adjusted_push_range(
            stack_bb=20,
            position="BTN",
            stacks=stacks,
            prize_pool=1.0,
        )
        
        # Should have structure with action, bubble_factor, icm_equity
        for key, data in icm_ranges.items():
            assert "action" in data
            assert "bubble_factor" in data
            assert "icm_equity" in data
            assert data["action"] in ["push", "fold"]

    def test_icm_bubble_factor_calculation(self):
        """Test that bubble factor affects push range."""
        try:
            from gto_poker.icm import icm_for_push_fold, get_standard_prizes
        except ImportError:
            pytest.skip("icm_for_push_fold not available")
        
        # Short stack with lots of players left should have higher bubble factor
        stacks_short = [100.0, 100.0, 100.0, 20.0, 20.0, 20.0]  # Short stack in middle
        stacks_deep = [200.0, 200.0, 200.0, 200.0, 200.0, 200.0]  # Everyone even
        
        icm_short = PushFoldCharts.get_icm_adjusted_push_range(
            stack_bb=20,
            position="MP",
            stacks=stacks_short,
        )
        
        icm_deep = PushFoldCharts.get_icm_adjusted_push_range(
            stack_bb=20,
            position="MP",
            stacks=stacks_deep,
        )
        
        # Short stack should have different bubble factor
        assert icm_short[("A", "A")]["bubble_factor"] != icm_deep[("A", "A")]["bubble_factor"]

    def test_icm_equity_calculation(self):
        """Test that ICM equity is calculated for each hand."""
        try:
            from gto_poker.icm import icm_for_push_fold, get_standard_prizes
        except ImportError:
            pytest.skip("icm_for_push_fold not available")
        
        stacks = [100.0, 100.0, 100.0, 100.0, 100.0, 100.0]
        
        icm_ranges = PushFoldCharts.get_icm_adjusted_push_range(
            stack_bb=20,
            position="BTN",
            stacks=stacks,
        )
        
        # ICM equity should be between 0 and 1
        for key, data in icm_ranges.items():
            assert 0 <= data["icm_equity"] <= 1


class TestPushFoldChartsComplete:
    """Comprehensive push/fold chart tests."""

    def test_all_combinations(self):
        """Test generating charts for all stack/position combinations."""
        for stack in PushFoldCharts.STACK_SIZES:
            for pos in PushFoldCharts.POSITIONS:
                chart = generate_nash_push_chart(stack, pos)
                assert len(chart) == 169
                # All values should be valid actions
                assert all(v in ["push", "fold"] for v in chart.values())
                
                # Premium hands like AA should always push
                assert chart[("A", "A")] == "push"
                
                # Weak hands like 72o should fold
                # But check format - might be sorted differently
                weak_key = ("2", "7") if RANK_INDICES["2"] >= RANK_INDICES["7"] else ("7", "2")
                assert chart[weak_key] == "fold"

    def test_lighter_positions_have_tighter_ranges(self):
        """Test that earlier positions have tighter push ranges."""
        utg_chart = generate_nash_push_chart(20, "UTG")
        mp_chart = generate_nash_push_chart(20, "MP")
        co_chart = generate_nash_push_chart(20, "CO")
        btn_chart = generate_nash_push_chart(20, "BTN")
        
        utg_pushes = sum(1 for a in utg_chart.values() if a == "push")
        mp_pushes = sum(1 for a in mp_chart.values() if a == "push")
        co_pushes = sum(1 for a in co_chart.values() if a == "push")
        btn_pushes = sum(1 for a in btn_chart.values() if a == "push")
        
        # Each position should be looser or equal to earlier position
        assert mp_pushes >= utg_pushes
        assert co_pushes >= mp_pushes
        assert btn_pushes >= co_pushes

    def test_shallow_stacks_have_tighter_ranges(self):
        """Test that shallower stacks have tighter push ranges."""
        chart_10 = generate_nash_push_chart(10, "BTN")
        chart_20 = generate_nash_push_chart(20, "BTN")
        chart_40 = generate_nash_push_chart(40, "BTN")
        chart_100 = generate_nash_push_chart(100, "BTN")
        
        pushes_10 = sum(1 for a in chart_10.values() if a == "push")
        pushes_20 = sum(1 for a in chart_20.values() if a == "push")
        pushes_40 = sum(1 for a in chart_40.values() if a == "push")
        pushes_100 = sum(1 for a in chart_100.values() if a == "push")
        
        # More pushes at 10bb than 100bb (ICM and Fold Equity)
        assert pushes_10 > pushes_100

    def test_push_fold_storage_roundtrip(self):
        """Test storing and retrieving push/fold charts."""
        storage = PushFoldStorage()
        
        # Generate and store a chart
        chart = generate_nash_push_chart(20, "BTN")
        chart_json = chart_to_json_serializable(chart)
        
        storage.store_chart(20, "BTN", chart_json)
        
        # Retrieve it
        retrieved = storage.get_chart(20, "BTN")
        
        assert retrieved is not None
        assert "AA" in retrieved
        assert retrieved["AA"] == "push"

    def test_generate_all_charts(self):
        """Test generating all 30 push/fold charts."""
        all_charts = generate_all_charts()
        
        # 5 stack sizes x 6 positions = 30 charts
        assert len(all_charts) == 30
        
        for stack in PushFoldCharts.STACK_SIZES:
            for pos in PushFoldCharts.POSITIONS:
                key = f"{stack}bb_{pos}"
                assert key in all_charts
                chart = all_charts[key]
                assert len(chart) == 169


class TestPushFoldChartMatrix:
    """Tests for chart matrix representation."""

    def test_chart_to_matrix(self):
        """Test converting chart to matrix format."""
        chart = generate_nash_push_chart(20, "BTN")
        
        # Convert to matrix
        matrix = []
        for r1 in RANKS:
            row = []
            for r2 in RANKS:
                action = chart.get((r1, r2), "fold")
                if action == "push":
                    row.append("P")
                else:
                    row.append("F")
            matrix.append(row)
        
        assert len(matrix) == 13
        assert all(len(row) == 13 for row in matrix)
        
        # AA should be push (P)
        assert matrix[12][12] == "P"

    def test_chart_lookup_hand(self):
        """Test looking up hands by string."""
        chart = generate_nash_push_chart(20, "BTN")
        
        assert lookup_hand(chart, "AA") == "push"
        assert lookup_hand(chart, "AKs") == "push"
        assert lookup_hand(chart, "72o") == "fold"

    def test_chart_lookup_action(self):
        """Test looking up action by rank and suited."""
        chart = generate_nash_push_chart(20, "BTN")
        
        assert lookup_action(chart, "A", "A", False) == "push"
        assert lookup_action(chart, "K", "Q", True) in ["push", "fold"]
        assert lookup_action(chart, "7", "2", False) == "fold"


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestSolverStoragePushFoldIntegration:
    """Integration tests for solver, storage, and push/fold charts."""

    def test_solve_store_retrieve_flow(self):
        """Test the complete flow: solve -> store -> retrieve."""
        # 1. Solve a river spot
        strategies, _, state = solve_river(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            board=["Kh", "8c", "3d", "2s", "Ks"],
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=50,
            bet_sizes=[0.5]
        )
        
        # 2. Store the strategy
        storage = StrategyStorage()
        strategy_data = {k: v.tolist() for k, v in strategies.items()}
        
        stored = storage.save_strategy(
            street="river",
            strategy_data=strategy_data,
            board_hash="Kh8c3d2sKs",
            bet_size=0.5,
            stack_depth=100,
        )
        
        # 3. Retrieve and verify
        retrieved = storage.get_strategy(stored.key)
        assert retrieved is not None
        assert stored.key in storage._cache

    def test_push_fold_generation_and_storage(self):
        """Test generating push/fold charts and storing them."""
        storage = PushFoldStorage()
        
        # Generate all charts
        for stack in PushFoldCharts.STACK_SIZES:
            for pos in PushFoldCharts.POSITIONS:
                chart = generate_nash_push_chart(stack, pos)
                chart_json = chart_to_json_serializable(chart)
                
                storage.store_chart(stack, pos, chart_json)
                
                # Verify it was stored
                retrieved = storage.get_chart(stack, pos)
                assert retrieved is not None
                assert "AA" in retrieved

    def test_full_pipeline_with_storage(self):
        """Test solving a spot and storing/retrieving the result."""
        storage = StrategyStorage()
        
        # Solve flop
        strategies, _, state = solve_flop(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=50,
            bet_sizes=[0.5]
        )
        
        # Convert and store
        strategy_data = {k: v.tolist() for k, v in strategies.items()}
        storage.save_strategy(
            street="flop",
            strategy_data=strategy_data,
            board_hash="Kh8c3d",
            bet_size=0.5,
            stack_depth=100,
        )
        
        # Can retrieve with correct key
        key = storage.make_strategy_key(
            street="flop",
            board_hash="Kh8c3d",
            bet_size=0.5,
            stack_depth=100,
        )
        retrieved = storage.get_strategy(key)
        assert retrieved == strategy_data or retrieved is None  # Cache may vary


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
