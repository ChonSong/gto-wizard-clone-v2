"""Polish edge case tests for Bomb Pot

- Verify BombPotState.get_action_space() exists and returns correct actions per street
- Verify action space transitions through phases
- Verify no fold in straddle round
"""
import pytest
import sys
sys.path.insert(0, "packages/poker-core/src")

from gto_poker.bomb_pot import (
    BombPotGameState,
    BombPotState,
    BombPotGameModel,
    BombPotAction,
    Phase,
    ActionType,
)


class TestBombPotActionSpaceEdgeCases:
    """Verify get_action_space() returns correct actions per street."""

    def test_bomb_pot_state_alias_has_get_action_space(self):
        """BombPotState alias must have get_action_space method."""
        assert hasattr(BombPotState, "get_action_space"), \
            "BombPotState alias should have get_action_space"
        assert BombPotState.get_action_space is BombPotGameState.get_action_space, \
            "BombPotState.get_action_space should be same as BombPotGameState.get_action_space"

    def test_get_action_space_instance_method(self):
        """Instance of BombPotState should have get_action_space."""
        state = BombPotState(positions=["p0", "p1"])
        assert hasattr(state, "get_action_space")
        assert callable(state.get_action_space)

    def test_straddle_round_actions_no_fold(self):
        """STRADDLE_ROUND: straddle, call, raise, check. NOT fold."""
        state = BombPotState(
            positions=["p0", "p1", "p2", "p3"],
            phase=Phase.STRADDLE_ROUND,
        )
        actions = state.get_action_space()
        expected = {ActionType.STRADDLE, ActionType.CALL, ActionType.RAISE, ActionType.CHECK}
        assert set(actions) == expected
        assert ActionType.FOLD not in actions

    def test_flop_actions_with_fold(self):
        """FLOP: call, raise, check, fold."""
        state = BombPotState(
            positions=["p0", "p1"],
            phase=Phase.FLOP,
        )
        actions = state.get_action_space()
        expected = {ActionType.CALL, ActionType.RAISE, ActionType.CHECK, ActionType.FOLD}
        assert set(actions) == expected

    def test_turn_actions_with_fold(self):
        """TURN: call, raise, check, fold."""
        state = BombPotState(
            positions=["p0", "p1"],
            phase=Phase.TURN,
        )
        actions = state.get_action_space()
        expected = {ActionType.CALL, ActionType.RAISE, ActionType.CHECK, ActionType.FOLD}
        assert set(actions) == expected

    def test_river_actions_with_fold(self):
        """RIVER: call, raise, check, fold."""
        state = BombPotState(
            positions=["p0", "p1"],
            phase=Phase.RIVER,
        )
        actions = state.get_action_space()
        expected = {ActionType.CALL, ActionType.RAISE, ActionType.CHECK, ActionType.FOLD}
        assert set(actions) == expected

    def test_showdown_no_actions(self):
        """SHOWDOWN: empty action list."""
        state = BombPotState(
            positions=["p0", "p1"],
            phase=Phase.SHOWDOWN,
        )
        actions = state.get_action_space()
        assert actions == []

    def test_action_space_transition(self):
        """As phase transitions, action space should change."""
        model = BombPotGameModel()
        state = BombPotState(
            positions=["p0", "p1", "p2"],
            phase=Phase.STRADDLE_ROUND,
        )
        # Straddle round: no fold
        assert ActionType.FOLD not in state.get_action_space()

        # Transition to flop
        new_state, _ = model.resolve_preflop(state)
        # Flop: has fold
        assert new_state.phase == Phase.FLOP
        assert ActionType.FOLD in new_state.get_action_space()
        assert ActionType.STRADDLE not in new_state.get_action_space()

    def test_legal_actions_straddle_round_post_flop(self):
        """legal_actions from model mirrors get_action_space."""
        model = BombPotGameModel()
        state = BombPotState(
            positions=["p0", "p1", "p2", "p3"],
            phase=Phase.STRADDLE_ROUND,
            straddle_map={1: 20},
        )

        actions = model.legal_actions(state, player=2)
        assert ActionType.STRADDLE in actions  # Not already straddling
        assert ActionType.FOLD not in actions  # No fold in straddle round

        # Player who already straddled can't straddle again
        actions_straddler = model.legal_actions(state, player=1)
        assert ActionType.STRADDLE not in actions_straddler, \
            "Player who already straddled can't straddle again"
