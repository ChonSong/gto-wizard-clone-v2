"""Tests for node locking (frequency constraints) on preflop ranges."""
import pytest
from apps.api.routers.solver import (
    HandLock,
    PreflopRangeRequest,
    _apply_node_locks,
    HandCell,
)


class TestHandLockValidation:
    """HandLock model should validate frequency constraints."""

    def test_valid_lock(self):
        lock = HandLock(actions={"fold": 0.3, "call": 0.7})
        assert lock.actions == {"fold": 0.3, "call": 0.7}

    def test_empty_lock(self):
        lock = HandLock(actions={})
        assert lock.actions == {}

    def test_frequency_sum_exceeds_one(self):
        with pytest.raises(Exception) as exc_info:
            HandLock(actions={"fold": 0.6, "call": 0.6})
        assert "1.0" in str(exc_info.value)

    def test_all_in_lock(self):
        lock = HandLock(actions={"all_in": 1.0})
        assert lock.actions["all_in"] == 1.0


class TestApplyNodeLocks:
    """_apply_node_locks should override cell frequencies."""

    def test_no_locks(self):
        cells = [HandCell(hand="AA", action="raise", frequency=1.0)]
        applied, counter = _apply_node_locks(cells, None, [])
        assert applied == []
        assert counter is None

    def test_empty_locks(self):
        cells = [HandCell(hand="AA", action="raise", frequency=1.0)]
        applied, counter = _apply_node_locks(cells, {}, [])
        assert applied == []

    def test_simple_frequency_lock(self):
        cells = [
            HandCell(hand="AA", action="raise", frequency=1.0),
            HandCell(hand="KK", action="fold", frequency=0.0),
        ]
        locks = {"AA": HandLock(actions={"raise": 0.8, "call": 0.2})}
        applied, counter = _apply_node_locks(cells, locks, [{"actionBase": "raise"}, {"actionBase": "call"}])
        assert "AA" in applied
        assert cells[0].frequency == 0.8  # primary action's frequency
        assert cells[0].action == "raise"  # primary action
        assert counter is not None
        assert "AA" in counter  # deviation from 1.0 to 0.8

    def test_lock_not_in_available_actions_skipped(self):
        cells = [HandCell(hand="AA", action="raise", frequency=1.0)]
        # Lock has action "bluff" which isn't available
        locks = {"AA": HandLock(actions={"bluff": 1.0})}
        applied, counter = _apply_node_locks(cells, locks, [{"actionBase": "raise"}])
        # Should still apply (with warning logged) since it's a valid action string
        assert "AA" in applied

    def test_lock_nonexistent_hand_ignored(self):
        cells = [HandCell(hand="AA", action="raise", frequency=1.0)]
        locks = {"ZZ": HandLock(actions={"raise": 1.0})}
        applied, counter = _apply_node_locks(cells, locks, [{"actionBase": "raise"}])
        assert applied == []

    def test_multiple_hands_locked(self):
        cells = [
            HandCell(hand="AA", action="raise", frequency=1.0),
            HandCell(hand="KK", action="fold", frequency=0.0),
            HandCell(hand="QQ", action="fold", frequency=0.0),
        ]
        locks = {
            "AA": HandLock(actions={"raise": 0.8}),
            "KK": HandLock(actions={"call": 1.0}),
        }
        applied, counter = _apply_node_locks(cells, locks, [{"actionBase": "raise"}, {"actionBase": "call"}])
        assert "AA" in applied
        assert "KK" in applied
        assert "QQ" not in applied
        # KK was 0.0 -> now 1.0
        assert cells[1].frequency == 1.0
        assert cells[1].action == "call"

    def test_counter_strategy_deviation(self):
        cells = [HandCell(hand="AA", action="raise", frequency=1.0)]
        locks = {"AA": HandLock(actions={"fold": 0.5, "call": 0.5})}
        applied, counter = _apply_node_locks(cells, locks, [{"actionBase": "fold"}, {"actionBase": "call"}])
        assert counter is not None
        # AA was 1.0 (raise) → now 0.5 (fold). Deviation = 0.5 - 1.0 = -0.5
        assert counter["AA"] == pytest.approx(-0.5)


class TestPreflopRangeRequestWithLocks:
    """PreflopRangeRequest should accept locked_hands field."""

    def test_request_without_locks(self):
        req = PreflopRangeRequest(position="UTG", stack_depth=100)
        assert req.locked_hands is None

    def test_request_with_locks(self):
        req = PreflopRangeRequest(
            position="UTG",
            stack_depth=100,
            locked_hands={"AA": {"actions": {"raise": 0.8, "call": 0.2}}},
        )
        assert req.locked_hands is not None
        assert "AA" in req.locked_hands
        assert req.locked_hands["AA"].actions["raise"] == 0.8
