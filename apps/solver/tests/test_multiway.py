"""
Tests for multi-way pot support (2-6 players) in GTO solver.

This module tests:
- 3-way, 4-way, 5-way, 6-way river scenarios
- Multi-way terminal state resolution (showdown and fold)
- Multi-way infoset management
- Strategy validity for multi-way pots
"""

import pytest
import numpy as np
import os
import sys

# path removed — gto-poker is pip-installed
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from games.texas_hold_em import TexasHoldEm, create_multiway_river_state, create_river_state, GameState
from cfr.engine import CFREngine
from gto_poker.hand import Hand, HandEvaluator
from gto_poker.deck import Deck


class TestMultiWayStateCreation:
    """Test creating multi-way game states."""
    
    def test_3way_state(self):
        """Test creating a 3-player river state."""
        state = create_multiway_river_state(
            all_hole_cards=['Ac', 'Kd', 'Qs', 'Js', '2h', '2d'],
            board=['Kh', '8c', '3d', '2s', 'Ks'],
            pot=30.0,
            stacks=[100.0, 100.0, 100.0],
            current_player=0
        )
        
        assert state.n_players == 3
        assert len(state.hole_cards) == 6
        assert len(state.board) == 5
        assert state.street == 3
        assert state.pot == 30.0
    
    def test_4way_state(self):
        """Test creating a 4-player river state."""
        state = create_multiway_river_state(
            all_hole_cards=['Ac', 'Kd', 'Qs', 'Js', '2h', '2d', '9c', '9d'],
            board=['Kh', '8c', '3d', '2s', 'Ks'],
            pot=40.0,
            stacks=[100.0, 100.0, 100.0, 100.0],
            current_player=0
        )
        
        assert state.n_players == 4
        assert len(state.hole_cards) == 8
        assert len(state.board) == 5
    
    def test_5way_state(self):
        """Test creating a 5-player river state."""
        state = create_multiway_river_state(
            all_hole_cards=['Ac', 'Kd', 'Qs', 'Js', '2h', '2d', '9c', '9d', 'Th', 'Td'],
            board=['Kh', '8c', '3d', '2s', 'Ks'],
            pot=50.0,
            stacks=[100.0] * 5,
            current_player=0
        )
        
        assert state.n_players == 5
        assert len(state.hole_cards) == 10
    
    def test_6way_state(self):
        """Test creating a 6-player river state."""
        state = create_multiway_river_state(
            all_hole_cards=['Ac', 'Kd', 'Qs', 'Js', '2h', '2d', '9c', '9d', 'Th', 'Td', '8c', '8d'],
            board=['Kh', '8c', '3d', '2s', 'Ks'],
            pot=60.0,
            stacks=[100.0] * 6,
            current_player=0
        )
        
        assert state.n_players == 6
        assert len(state.hole_cards) == 12


class TestMultiWayValidActions:
    """Test valid actions in multi-way pots."""
    
    def test_3way_valid_actions_first_player(self):
        """Test valid actions for first player in 3-way pot."""
        game = TexasHoldEm(n_players=3, bet_sizes=[0.5, 1.0])
        state = create_multiway_river_state(
            all_hole_cards=['Ac', 'Kd', 'Qs', 'Js', '2h', '2d'],
            board=['Kh', '8c', '3d', '2s', 'Ks'],
            pot=30.0,
            stacks=[100.0, 100.0, 100.0],
            current_player=0
        )
        
        actions = game.get_valid_actions(state, 0)
        assert 'fold' in actions
        assert 'check' in actions
        assert 'bet:0.5' in actions
    
    def test_3way_valid_actions_facing_bet(self):
        """Test valid actions when facing a bet in 3-way pot."""
        game = TexasHoldEm(n_players=3, bet_sizes=[0.5, 1.0])
        state = create_multiway_river_state(
            all_hole_cards=['Ac', 'Kd', 'Qs', 'Js', '2h', '2d'],
            board=['Kh', '8c', '3d', '2s', 'Ks'],
            pot=30.0,
            stacks=[95.0, 100.0, 100.0],  # P0 has 5bb invested
            current_player=1,
            bet_to_call=5.0,
            action_history=[
                type('Action', (), {'player': 0, 'action_type': 'bet', 'amount': 5.0})()
            ]
        )
        
        actions = game.get_valid_actions(state, 1)
        assert 'fold' in actions
        # Action might be 'call' or 'call:5.0' depending on implementation
        assert any('call' in a for a in actions), f"Expected 'call' in actions, got {actions}"
    
    def test_4way_valid_actions(self):
        """Test valid actions for 4-way pot."""
        game = TexasHoldEm(n_players=4, bet_sizes=[0.5])
        state = create_multiway_river_state(
            all_hole_cards=['Ac', 'Kd', 'Qs', 'Js', '2h', '2d', '9c', '9d'],
            board=['Kh', '8c', '3d', '2s', 'Ks'],
            pot=40.0,
            stacks=[100.0] * 4,
            current_player=0
        )
        
        actions = game.get_valid_actions(state, 0)
        assert len(actions) >= 2  # At least fold and check/bet


class TestMultiWayCFRSolve:
    """Test CFR solving for multi-way pots."""
    
    def test_3way_river_solve(self):
        """Test solving a 3-player river spot."""
        game = TexasHoldEm(n_players=3, bet_sizes=[0.5])
        state = create_multiway_river_state(
            all_hole_cards=['Ac', 'Kd', 'Qs', 'Js', '2h', '2d'],
            board=['Kh', '8c', '3d', '2s', 'Ks'],
            pot=30.0,
            stacks=[100.0, 100.0, 100.0],
            current_player=0
        )
        
        engine = CFREngine(game)
        strategies = engine.solve(state, iterations=30, sample_chance=False)
        
        # Should have infosets for players who can act
        assert len(strategies) >= 1
        
        # Check strategy validity
        for key, strat in strategies.items():
            assert np.isclose(strat.sum(), 1.0), f"Strategy {key} doesn't sum to 1"
            assert all(p >= 0 for p in strat), f"Strategy {key} has negative probabilities"
    
    def test_4way_river_solve(self):
        """Test solving a 4-player river spot."""
        game = TexasHoldEm(n_players=4, bet_sizes=[0.5])
        state = create_multiway_river_state(
            all_hole_cards=['Ac', 'Kd', 'Qs', 'Js', '2h', '2d', '9c', '9d'],
            board=['Kh', '8c', '3d', '2s', 'Ks'],
            pot=40.0,
            stacks=[100.0, 100.0, 100.0, 100.0],
            current_player=0
        )
        
        engine = CFREngine(game)
        strategies = engine.solve(state, iterations=20, sample_chance=False)
        
        # With limited iterations, we may only see 2 infosets
        # But strategies should still be valid
        assert len(strategies) >= 1
        for key, strat in strategies.items():
            assert np.isclose(strat.sum(), 1.0), f"Strategy {key} doesn't sum to 1"
    
    def test_5way_river_solve(self):
        """Test solving a 5-player river spot."""
        game = TexasHoldEm(n_players=5, bet_sizes=[0.5])
        state = create_multiway_river_state(
            all_hole_cards=['Ac', 'Kd', 'Qs', 'Js', '2h', '2d', '9c', '9d', 'Th', 'Td'],
            board=['Kh', '8c', '3d', '2s', 'Ks'],
            pot=50.0,
            stacks=[100.0] * 5,
            current_player=0
        )
        
        engine = CFREngine(game)
        strategies = engine.solve(state, iterations=15, sample_chance=False)
        
        # With limited iterations, we may only see 2 infosets
        assert len(strategies) >= 1
        for key, strat in strategies.items():
            assert np.isclose(strat.sum(), 1.0), f"Strategy {key} doesn't sum to 1"
    
    def test_6way_river_solve(self):
        """Test solving a 6-player river spot."""
        game = TexasHoldEm(n_players=6, bet_sizes=[0.5])
        state = create_multiway_river_state(
            all_hole_cards=['Ac', 'Kd', 'Qs', 'Js', '2h', '2d', '9c', '9d', 'Th', 'Td', '8c', '8d'],
            board=['Kh', '8c', '3d', '2s', 'Ks'],
            pot=60.0,
            stacks=[100.0] * 6,
            current_player=0
        )
        
        engine = CFREngine(game)
        strategies = engine.solve(state, iterations=10, sample_chance=False)
        
        # Even with 10 iterations, should see at least one infoset
        assert len(strategies) >= 1
        for key, strat in strategies.items():
            assert np.isclose(strat.sum(), 1.0), f"Strategy {key} doesn't sum to 1"


class TestMultiWayShortStack:
    """Test multi-way scenarios with short stacks."""
    
    def test_3way_short_stack_solve(self):
        """Test 3-way pot with one short stack."""
        game = TexasHoldEm(n_players=3, bet_sizes=[0.5, 1.0])
        state = create_multiway_river_state(
            all_hole_cards=['Ac', 'Kd', 'Qs', 'Js', '2h', '2d'],
            board=['Kh', '8c', '3d', '2s', 'Ks'],
            pot=30.0,
            stacks=[100.0, 20.0, 100.0],  # P1 is short stacked
            current_player=0
        )
        
        engine = CFREngine(game)
        strategies = engine.solve(state, iterations=25, sample_chance=False)
        
        # Should handle short stack correctly
        assert len(strategies) >= 1


class TestMultiWayInfosetKeys:
    """Test infoset key generation for multi-way pots."""
    
    def test_3way_infoset_key_format(self):
        """Test that infoset keys properly encode 3-way state."""
        state = create_multiway_river_state(
            all_hole_cards=['Ac', 'Kd', 'Qs', 'Js', '2h', '2d'],
            board=['Kh', '8c', '3d', '2s', 'Ks'],
            pot=30.0,
            stacks=[100.0, 100.0, 100.0],
            current_player=0
        )
        
        for player in range(3):
            key = state.infoset_key(player)
            assert f"p{player}:" in key
            # Key should contain hole cards for this player
            assert len(key) > 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])