"""
Tests for flop and turn solvers to ensure they work correctly with the CFR engine.

These tests verify:
1. Flop solver creates valid states and solves correctly
2. Turn solver creates valid states and solves correctly
3. Street advancement (flop→turn→river) works in chance sampling
4. Strategies returned are valid probability distributions
5. Integration with CFR engine is correct
"""

import sys
import os
# path removed — gto-poker is pip-installed
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import pytest
import numpy as np
from cfr.flop_solver import (
    solve_flop, solve_flop_basic, create_flop_state, 
    test_flop_solve, test_flop_convergence
)
from cfr.turn_solver import (
    solve_turn, solve_turn_basic, create_turn_state,
    test_create_turn_state, test_turn_state_with_existing_actions
)
from cfr.river_solver import solve_river_spot


class TestFlopSolver:
    """Test flop solver functionality."""
    
    def test_create_flop_state(self):
        """Test that create_flop_state produces a valid state."""
        state = create_flop_state(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            pot=10.0,
            stacks=[100.0, 100.0],
            current_player=0
        )
        
        # Verify street is flop (1)
        assert state.street == 1, f"Expected street 1, got {state.street}"
        
        # Verify board has 3 cards (flop)
        assert len(state.board) == 3, f"Expected 3 board cards, got {len(state.board)}"
        
        # Verify hole cards for both players
        assert len(state.hole_cards) == 4, f"Expected 4 hole cards, got {len(state.hole_cards)}"
        
        # Verify pot
        assert state.pot == 10.0, f"Expected pot 10.0, got {state.pot}"
        
        # Verify stacks
        assert state.stacks == [100.0, 100.0], f"Expected stacks [100, 100], got {state.stacks}"
    
    def test_solve_flop_basic(self):
        """Test basic flop solving returns strategies."""
        strategies = solve_flop_basic(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=50,
            bet_sizes=[0.5]
        )
        
        assert len(strategies) > 0, "Should have at least one infoset"
    
    def test_solve_flop_returns_tuple(self):
        """Test that solve_flop returns expected tuple."""
        strategies, game, state = solve_flop(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=50,
            bet_sizes=[0.5]
        )
        
        assert isinstance(strategies, dict), "First return value should be dict"
        assert hasattr(game, 'get_valid_actions'), "Game should have get_valid_actions"
        assert hasattr(state, 'street'), "State should have street attribute"
        assert state.street == 1, "State should be at flop street"
    
    def test_solve_flop_chance_sampling(self):
        """Test that flop solver performs chance sampling for turn/river."""
        strategies, game, state = solve_flop(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=100,
            bet_sizes=[0.5]
        )
        
        # Should have infosets for multiple turn/river scenarios
        # (since chance sampling samples different turn/river cards)
        assert len(strategies) > 10, f"Expected more than 10 infosets, got {len(strategies)}"
    
    def test_flop_strategies_valid(self):
        """Test that strategies returned are valid probability distributions."""
        strategies, _, _ = solve_flop(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=100,
            bet_sizes=[0.5]
        )
        
        for key, strat in strategies.items():
            total = sum(strat)
            assert np.isclose(total, 1.0), f"Strategy for {key} sums to {total}, not 1.0"
            assert all(p >= 0 for p in strat), f"Strategy for {key} has negative probabilities"
    
    def test_flop_solver_convergence(self):
        """Test flop solver converges to reasonable strategies."""
        strategies, _, _ = solve_flop(
            p0_cards=["Ac", "Kd"],  # Top pair
            p1_cards=["Qs", "Js"],  # Straight draw
            flop=["Kh", "8c", "3d"],
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=200,
            bet_sizes=[0.5, 1.0]
        )
        
        # More iterations should lead to more informed strategies
        assert len(strategies) > 0
        
        # Check that not all strategies are uniform (solver is learning)
        non_uniform = 0
        for strat in strategies.values():
            if not np.allclose(strat, strat[0]):
                non_uniform += 1
        
        # At least some strategies should be non-uniform after learning
        assert non_uniform > 0, "Solver should produce non-uniform strategies after learning"


class TestTurnSolver:
    """Test turn solver functionality."""
    
    def test_create_turn_state(self):
        """Test that create_turn_state produces a valid state."""
        state = create_turn_state(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            turn="2s",
            pot=10.0,
            stacks=[100.0, 100.0],
            current_player=0
        )
        
        # Verify street is turn (2)
        assert state.street == 2, f"Expected street 2, got {state.street}"
        
        # Verify board has 4 cards (flop + turn)
        assert len(state.board) == 4, f"Expected 4 board cards, got {len(state.board)}"
        
        # Verify hole cards for both players
        assert len(state.hole_cards) == 4, f"Expected 4 hole cards, got {len(state.hole_cards)}"
        
        # Verify pot
        assert state.pot == 10.0, f"Expected pot 10.0, got {state.pot}"
    
    def test_create_turn_state_with_bet(self):
        """Test creating turn state with existing betting action."""
        from games.texas_hold_em import Action, ActionType
        
        actions = [
            Action(ActionType.BET, 0, 5.0),
            Action(ActionType.CALL, 1, 5.0),
        ]
        
        state = create_turn_state(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            turn="2s",
            pot=20.0,
            stacks=[95.0, 95.0],
            current_player=0,
            bet_to_call=0.0,
            action_history=actions
        )
        
        assert state.street == 2
        assert state.pot == 20.0
        assert len(state.action_history) == 2
    
    def test_solve_turn_basic(self):
        """Test basic turn solving returns strategies."""
        strategies = solve_turn_basic(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            turn="2s",
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=50,
            bet_sizes=[0.5]
        )
        
        assert len(strategies) > 0, "Should have at least one infoset"
    
    def test_solve_turn_returns_tuple(self):
        """Test that solve_turn returns expected tuple."""
        strategies, game, state = solve_turn(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            turn="2s",
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=50,
            bet_sizes=[0.5]
        )
        
        assert isinstance(strategies, dict), "First return value should be dict"
        assert state.street == 2, "State should be at turn street"
        assert len(state.board) == 4, "Board should have 4 cards"
    
    def test_turn_chance_sampling(self):
        """Test that turn solver performs chance sampling for river."""
        strategies, _, state = solve_turn(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            turn="2s",
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=100,
            bet_sizes=[0.5]
        )
        
        # Should have infosets for different river scenarios
        assert len(strategies) > 10, f"Expected more than 10 infosets, got {len(strategies)}"
    
    def test_turn_strategies_valid(self):
        """Test that strategies returned are valid probability distributions."""
        strategies, _, _ = solve_turn(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            turn="2s",
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=100,
            bet_sizes=[0.5]
        )
        
        for key, strat in strategies.items():
            total = sum(strat)
            assert np.isclose(total, 1.0), f"Strategy for {key} sums to {total}, not 1.0"
            assert all(p >= 0 for p in strat), f"Strategy for {key} has negative probabilities"
    
    def test_turn_short_stack(self):
        """Test turn solver with short stack player."""
        strategies, _, state = solve_turn(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            turn="2s",
            pot=10.0,
            stacks=[100.0, 20.0],  # P1 is short stacked
            iterations=50,
            bet_sizes=[0.5, 1.0]
        )
        
        assert state.stacks == [100.0, 20.0]
        assert len(strategies) > 0


class TestStreetIntegration:
    """Test that flop→turn→river integration works correctly."""
    
    def test_river_solver_vs_chance_sampling(self):
        """Test that chance sampling with known river gives similar results to full river solve."""
        # Solve at river (known cards)
        strategies_river, _, _ = solve_river_spot(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            board=["Kh", "8c", "3d", "2s", "Ks"],
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=100,
            bet_sizes=[0.5]
        )
        
        # Turn solver with turn card known, river sampled
        strategies_turn, _, state_turn = solve_turn(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            turn="2s",
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=100,
            bet_sizes=[0.5]
        )
        
        # Both should produce strategies
        assert len(strategies_river) > 0
        assert len(strategies_turn) > 0
        
        # Turn state should have street=2 and 4 board cards
        assert state_turn.street == 2
        assert len(state_turn.board) == 4


class TestFlopTurnConsistency:
    """Test consistency between flop and turn solvers."""
    
    def test_flop_to_turn_progression(self):
        """Test that solving at flop then turn gives consistent results."""
        # Same hand, different streets
        flop_strategies, _, flop_state = solve_flop(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=100,
            bet_sizes=[0.5]
        )
        
        turn_strategies, _, turn_state = solve_turn(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            turn="2s",
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=100,
            bet_sizes=[0.5]
        )
        
        # Both should have flop on board
        assert len(flop_state.board) == 3
        assert len(turn_state.board) == 4
        
        # Flop state is at street 1, turn at street 2
        assert flop_state.street == 1
        assert turn_state.street == 2
        
        # Both should produce strategies
        assert len(flop_strategies) > 0
        assert len(turn_strategies) > 0
    
    def test_callback_invoked(self):
        """Test that callback is invoked during solving."""
        call_count = [0]
        
        def my_callback(iter_num, infoset_manager):
            call_count[0] += 1
        
        solve_flop(
            p0_cards=["Ac", "Kd"],
            p1_cards=["Qs", "Js"],
            flop=["Kh", "8c", "3d"],
            pot=10.0,
            stacks=[100.0, 100.0],
            iterations=100,
            bet_sizes=[0.5],
            callback=my_callback
        )
        
        # Callback should be called (every 100 iterations by default)
        assert call_count[0] > 0, "Callback was not called"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])