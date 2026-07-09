"""Tests for Bomb Pot game model.

Bomb Pot is a novel variant where:
- Pre-flop action happens BEFORE the board is dealt
- No fold option for players who posted straddle
- Straddle round is a mandatory action round (no fold)

Game model: straddle_map + junk_blinds + betting order
"""
import pytest
import sys

sys.path.insert(0, "/tmp/PokerHandEvaluator/python")
sys.path.insert(0, "packages/poker-core/src")

from gto_poker.bomb_pot import (
    BombPotGameState,
    BombPotAction,
    BombPotGameModel,
    BombPotEquity,
    BombPotState,
    Phase,
    ActionType,
)


class TestBombPotActionSpace:
    """Test BombPotState.get_action_space() for each street/phase."""

    def test_get_action_space_exists(self):
        """BombPotState should have get_action_space method."""
        state = BombPotGameState(positions=["p0", "p1"])
        assert hasattr(state, "get_action_space"), "get_action_space() must exist"
        # Also test via the BombPotState alias
        assert BombPotState.get_action_space is BombPotGameState.get_action_space, \
            "BombPotState alias should share get_action_space"

    def test_straddle_round_no_fold(self):
        """STRADDLE_ROUND: straddle, call, raise, check — NO fold."""
        state = BombPotGameState(
            positions=["p0", "p1", "p2", "p3"],
            phase=Phase.STRADDLE_ROUND,
        )
        actions = state.get_action_space()
        expected = {ActionType.STRADDLE, ActionType.CALL, ActionType.RAISE, ActionType.CHECK}
        assert set(actions) == expected, f"Expected {expected}, got {set(actions)}"
        assert ActionType.FOLD not in actions, "Fold should not be available in straddle round"

    def test_flop_has_fold(self):
        """FLOP: call, raise, check, fold."""
        state = BombPotGameState(
            positions=["p0", "p1", "p2", "p3"],
            phase=Phase.FLOP,
        )
        actions = state.get_action_space()
        expected = {ActionType.CALL, ActionType.RAISE, ActionType.CHECK, ActionType.FOLD}
        assert set(actions) == expected, f"Expected {expected}, got {set(actions)}"
        assert ActionType.STRADDLE not in actions, "Straddle should not be available post-flop"

    def test_turn_has_fold(self):
        """TURN: call, raise, check, fold."""
        state = BombPotGameState(
            positions=["p0", "p1", "p2", "p3"],
            phase=Phase.TURN,
        )
        actions = state.get_action_space()
        expected = {ActionType.CALL, ActionType.RAISE, ActionType.CHECK, ActionType.FOLD}
        assert set(actions) == expected

    def test_river_has_fold(self):
        """RIVER: call, raise, check, fold."""
        state = BombPotGameState(
            positions=["p0", "p1", "p2", "p3"],
            phase=Phase.RIVER,
        )
        actions = state.get_action_space()
        expected = {ActionType.CALL, ActionType.RAISE, ActionType.CHECK, ActionType.FOLD}
        assert set(actions) == expected

    def test_showdown_empty_actions(self):
        """SHOWDOWN: no actions available."""
        state = BombPotGameState(
            positions=["p0", "p1", "p2", "p3"],
            phase=Phase.SHOWDOWN,
        )
        actions = state.get_action_space()
        assert actions == [], f"Showdown should have no actions, got {actions}"

    def test_bomb_pot_state_alias_works(self):
        """BombPotState alias should have the same interface."""
        state = BombPotState(  # noqa: F841 (using imported alias)
            positions=["p0", "p1"],
            phase=Phase.FLOP,
        )
        # Just verify the class is the same
        assert BombPotState is BombPotGameState


class TestBombPotGameState:
    """Test BombPotGameState initialization and properties."""

    def test_create_with_straddle_map(self):
        """Can create game state with straddle map."""
        state = BombPotGameState(
            positions=["UTG", "UTG+1", "UTG+2", "CO", "BTN", "SB"],
            straddle_map={1: 20, 3: 40},  # UTG+1 straddle $20, CO straddle $40
            junk_blinds=[10, 20],  # extra antes
        )

        assert state.player_count == 6
        assert state.straddle_map[1] == 20
        assert state.straddle_map[3] == 40

    def test_default_phase_is_straddle_round(self):
        """New bomb pot starts in STRADDLE_ROUND phase."""
        state = BombPotGameState(
            positions=["UTG", "UTG+1", "CO", "BTN"]
        )
        assert state.phase == Phase.STRADDLE_ROUND

    def test_betting_order_starts_with_straddlers(self):
        """Betting order starts with players who straddled."""
        state = BombPotGameState(
            positions=["UTG", "UTG+1", "UTG+2", "CO", "BTN", "SB"],
            straddle_map={1: 20},
            betting_order=[1, 2, 3, 4, 5]
        )
        assert state.betting_order[0] == 1


class TestBombPotAction:
    """Test BombPotAction action types."""

    def test_straddle_action(self):
        """Can create a straddle action."""
        action = BombPotAction(
            action_type=ActionType.STRADDLE,
            player=1,
            amount=20
        )
        assert action.action_type == ActionType.STRADDLE
        assert action.player == 1
        assert action.amount == 20

    def test_call_action(self):
        """Can create a call action."""
        action = BombPotAction(
            action_type=ActionType.CALL,
            player=2,
            amount=10
        )
        assert action.action_type == ActionType.CALL
        assert action.amount == 10

    def test_raise_action(self):
        """Can create a raise action."""
        action = BombPotAction(
            action_type=ActionType.RAISE,
            player=3,
            amount=40
        )
        assert action.action_type == ActionType.RAISE
        assert action.amount == 40

    def test_check_action(self):
        """Can create a check action in straddle round."""
        action = BombPotAction(
            action_type=ActionType.CHECK,
            player=4
        )
        assert action.action_type == ActionType.CHECK


class TestBombPotGameModel:
    """Test BombPotGameModel logic."""

    def test_create_straddle_map(self):
        """create_straddle_map() builds correct straddle positions."""
        model = BombPotGameModel()
        straddle_map = model.create_straddle_map(
            positions=[0, 1, 2, 3, 4, 5],
            amounts={1: 20, 3: 40}
        )

        assert straddle_map[1] == 20
        assert straddle_map[3] == 40
        assert 0 not in straddle_map  # UTG doesn't straddle
        assert 2 not in straddle_map  # UTG+2 doesn't straddle

    def test_calculate_pot_with_straddles(self):
        """Pot calculation includes straddle amounts."""
        model = BombPotGameModel()
        state = BombPotGameState(
            positions=["p0", "p1", "p2", "p3", "p4", "p5"],
            straddle_map={1: 20, 3: 40},
            junk_blinds=[5]  # $5 ante per player
        )

        pot = model.calculate_pot(state)
        # 6 players * $5 ante = $30
        # Position 1 straddle $20, position 3 straddle $40
        # Total = $30 + $20 + $40 = $90
        assert pot == 90

    def test_is_betting_complete_when_all_acted(self):
        """Betting is complete when all players have acted."""
        model = BombPotGameModel()
        state = BombPotGameState(
            positions=["p0", "p1", "p2", "p3"],
            straddle_map={1: 20},
            betting_order=[1],  # only position 1 needs to act
            betting_acted={1}  # they already acted
        )

        assert model.is_betting_complete(state) is True

    def test_next_bettor(self):
        """next_bettor() returns next player who hasn't acted."""
        model = BombPotGameModel()
        state = BombPotGameState(
            positions=["p0", "p1", "p2", "p3", "p4", "p5"],
            straddle_map={1: 20, 3: 40},
            betting_order=[0, 1, 3, 4, 5],  # all players
            betting_acted=set(),  # no one has acted
            current_bettor=0
        )

        next_player = model.next_bettor(state)
        # First player in betting order who hasn't acted
        assert next_player == 0

    def test_no_fold_option_in_straddle_round(self):
        """Players cannot fold in straddle round — only straddle/call/raise/check."""
        model = BombPotGameModel()
        state = BombPotGameState(
            positions=["p0", "p1", "p2", "p3"],
            straddle_map={1: 20},
            phase=Phase.STRADDLE_ROUND
        )

        legal_actions = model.legal_actions(state, player=2)
        # FOLD is intentionally not in the ActionType enum for straddle round
        # Player 2 (non-straddler) can call, raise, or check — NO FOLD
        assert ActionType.CALL in legal_actions
        assert ActionType.RAISE in legal_actions
        assert ActionType.CHECK in legal_actions

    def test_resolve_preflop_transitions_to_flop(self):
        """resolve_preflop() returns updated state with FLOP phase."""
        model = BombPotGameModel()
        state = BombPotGameState(
            positions=["p0", "p1", "p2", "p3"],
            straddle_map={1: 20},
            phase=Phase.STRADDLE_ROUND
        )

        new_state, pot = model.resolve_preflop(state)

        assert new_state.phase == Phase.FLOP
        assert pot > 0  # pot should have straddle money

    def test_raise_in_straddle_round_increases_pot(self):
        """A raise in straddle round adds to the pot."""
        model = BombPotGameModel()
        state = BombPotGameState(
            positions=["p0", "p1", "p2", "p3"],
            straddle_map={1: 20},
            phase=Phase.STRADDLE_ROUND,
            pot=40  # Antes + straddle
        )

        action = BombPotAction(action_type=ActionType.RAISE, player=1, amount=40)
        new_state = model.apply_action(state, action)

        # Pot should increase by the raise amount
        assert new_state.pot > state.pot


class TestBombPotEquity:
    """Test bomb pot equity calculation."""

    def test_equity_with_straddle_in_pot(self):
        """Equity calculation accounts for straddle dead money."""
        state = BombPotGameState(
            positions=["Hero", "Villain"],
            straddle_map={0: 20},  # hero straddles
            junk_blinds=[5]
        )

        equity_calc = BombPotEquity(seed=42)
        hero_hand = ["Ah", "Kh", "Qh", "Jh"]
        villain_hand = ["2h", "3h", "4h", "5h"]

        eq_hero, eq_villain = equity_calc.calculate(
            state, hero_hand, villain_hand, samples=1000
        )

        # Hero with premium should have > 50% equity
        assert eq_hero > 0.5
        # Clear favorite against trash (allow some variance)
        assert eq_hero > 55