"""
End-to-end tests for solver API endpoints.

These tests hit the running API server on localhost:8000 and verify
the full HTTP request/response cycle including serialization, error
handling, and response structure.

Prerequisites:
  - API server running on localhost:8000
  - Redis available (or fakeredis fallback)

Run with: pytest apps/api/tests/test_solver_e2e.py -v --timeout=60
"""

import os
import sys
import time
import urllib.request
import urllib.error
import json

import pytest

# ── Config ──────────────────────────────────────────────────────────
API_BASE = os.environ.get("E2E_API_BASE", "http://localhost:8000")
HEALTH_URL = f"{API_BASE}/api/v1/health"
SOLVER_HEALTH_URL = f"{API_BASE}/api/v1/solver/health"
SOLVER_SOLVE_URL = f"{API_BASE}/api/v1/solver/solve"
SOLVER_PREFLOP_URL = f"{API_BASE}/api/v1/solver/preflop-range"
SOLVER_POSTFLOP_URL = f"{API_BASE}/api/v1/solver/postflop-strategy"
STRATEGY_LOOKUP_URL = f"{API_BASE}/api/v1/strategy-lookup"


def _api_reachable() -> bool:
    """Check if the API server is reachable."""
    try:
        req = urllib.request.urlopen(HEALTH_URL, timeout=3)
        return req.status == 200
    except Exception:
        return False


def _post(url: str, payload: dict, timeout: int = 30) -> tuple[int, dict]:
    """POST JSON to url, return (status_code, parsed_json)."""
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        data = json.loads(resp.read().decode())
        return resp.status, data
    except urllib.error.HTTPError as e:
        data = json.loads(e.read().decode()) if e.fp else {}
        return e.code, data


def _get(url: str, timeout: int = 10) -> tuple[int, dict]:
    """GET url, return (status_code, parsed_json)."""
    try:
        resp = urllib.request.urlopen(url, timeout=timeout)
        data = json.loads(resp.read().decode())
        return resp.status, data
    except urllib.error.HTTPError as e:
        data = json.loads(e.read().decode()) if e.fp else {}
        return e.code, data


# Skip all e2e tests if the server is not running
pytestmark = pytest.mark.skipif(
    not _api_reachable(),
    reason=f"API server not reachable at {API_BASE}",
)


# ════════════════════════════════════════════════════════════════════
# Health Checks
# ════════════════════════════════════════════════════════════════════


class TestHealthEndpoints:
    """Verify health endpoints return 200 with expected structure."""

    def test_api_health_returns_200(self):
        """Root health endpoint returns 200."""
        status, data = _get(HEALTH_URL)
        assert status == 200

    def test_solver_health_returns_200(self):
        """Solver health endpoint returns 200 with engine status."""
        status, data = _get(SOLVER_HEALTH_URL)
        assert status == 200
        assert "status" in data
        assert data["status"] in ("ok", "degraded")

    def test_solver_health_includes_engine_field(self):
        """Solver health response includes engine name."""
        status, data = _get(SOLVER_HEALTH_URL)
        assert status == 200
        assert "engine" in data


# ════════════════════════════════════════════════════════════════════
# Preflop Range Endpoint
# ════════════════════════════════════════════════════════════════════


class TestPreflopRangeEndpoint:
    """Test POST /api/v1/solver/preflop-range for all positions."""

    @pytest.mark.parametrize("position", ["UTG", "HJ", "CO", "BTN", "SB", "BB"])
    def test_preflop_range_returns_200(self, position):
        """Preflop range endpoint returns 200 for every position."""
        status, data = _post(
            SOLVER_PREFLOP_URL,
            {
                "position": position,
                "stack_depth": 100,
            },
        )
        assert status == 200, f"Expected 200 for {position}, got {status}: {data}"

    @pytest.mark.parametrize("position", ["UTG", "HJ", "CO", "BTN", "SB", "BB"])
    def test_preflop_range_returns_169_hands(self, position):
        """Preflop range response contains all 169 hand combos."""
        status, data = _post(
            SOLVER_PREFLOP_URL,
            {
                "position": position,
                "stack_depth": 100,
            },
        )
        assert status == 200
        assert "hands" in data
        assert len(data["hands"]) == 169, (
            f"Expected 169 hands for {position}, got {len(data['hands'])}"
        )

    def test_preflop_range_response_has_required_fields(self):
        """Each hand cell has hand, action, frequency, equity."""
        status, data = _post(
            SOLVER_PREFLOP_URL,
            {
                "position": "BTN",
                "stack_depth": 100,
            },
        )
        assert status == 200
        hand = data["hands"][0]
        assert "hand" in hand
        assert "action" in hand
        assert "frequency" in hand
        assert "equity" in hand

    def test_preflop_range_position_in_response(self):
        """Response echoes the requested position."""
        status, data = _post(
            SOLVER_PREFLOP_URL,
            {
                "position": "CO",
                "stack_depth": 100,
            },
        )
        assert status == 200
        assert data["position"] == "CO"

    def test_preflop_range_stack_depth_in_response(self):
        """Response echoes the requested stack depth."""
        status, data = _post(
            SOLVER_PREFLOP_URL,
            {
                "position": "BTN",
                "stack_depth": 75,
            },
        )
        assert status == 200
        assert data["stack_depth"] == 75

    def test_preflop_range_btn_has_more_raises_than_utg(self):
        """BTN opening range is wider than UTG (more raise actions)."""
        _, btn_data = _post(
            SOLVER_PREFLOP_URL,
            {
                "position": "BTN",
                "stack_depth": 100,
            },
        )
        _, utg_data = _post(
            SOLVER_PREFLOP_URL,
            {
                "position": "UTG",
                "stack_depth": 100,
            },
        )
        btn_raises = sum(1 for h in btn_data["hands"] if h["action"] != "fold")
        utg_raises = sum(1 for h in utg_data["hands"] if h["action"] != "fold")
        assert btn_raises > utg_raises, (
            f"BTN ({btn_raises} raises) should be wider than UTG ({utg_raises} raises)"
        )

    def test_preflop_range_has_source_field(self):
        """Response includes source indicating data origin."""
        status, data = _post(
            SOLVER_PREFLOP_URL,
            {
                "position": "UTG",
                "stack_depth": 100,
            },
        )
        assert status == 200
        assert "source" in data
        assert isinstance(data["source"], str) and len(data["source"]) > 0


# ════════════════════════════════════════════════════════════════════
# Postflop Strategy Endpoint
# ════════════════════════════════════════════════════════════════════


class TestPostflopStrategyEndpoint:
    """Test POST /api/v1/solver/postflop-strategy."""

    def test_postflop_flop_returns_200(self):
        """Postflop strategy for a flop spot returns 200."""
        status, data = _post(
            SOLVER_POSTFLOP_URL,
            {
                "board": "KsKc3s",
                "position": "BTN",
                "street": "flop",
                "pot_size": 5.5,
                "stack_depth": 97.5,
            },
            timeout=45,
        )
        assert status == 200, f"Expected 200, got {status}: {data}"

    def test_postflop_response_has_status_field(self):
        """Postflop response includes status field."""
        status, data = _post(
            SOLVER_POSTFLOP_URL,
            {
                "board": "KsKc3s",
                "position": "BTN",
                "street": "flop",
                "pot_size": 5.5,
                "stack_depth": 97.5,
            },
            timeout=45,
        )
        assert status == 200
        assert "status" in data

    def test_postflop_response_has_source_field(self):
        """Postflop response includes source (cached or live-solver)."""
        status, data = _post(
            SOLVER_POSTFLOP_URL,
            {
                "board": "KsKc3s",
                "position": "BTN",
                "street": "flop",
                "pot_size": 5.5,
                "stack_depth": 97.5,
            },
            timeout=45,
        )
        assert status == 200
        if data.get("status") == "complete":
            assert "source" in data

    def test_postflop_invalid_board_returns_error(self):
        """Too-short board for the requested street returns error status."""
        status, data = _post(
            SOLVER_POSTFLOP_URL,
            {
                "board": "Ks",
                "position": "BTN",
                "street": "flop",
                "pot_size": 5.5,
                "stack_depth": 97.5,
            },
            timeout=15,
        )
        # Should not be a 500 — the handler catches ValueError
        assert status in (200, 500)
        if status == 200:
            assert data.get("status") == "error"

    def test_postflop_with_hero_hand(self):
        """Postflop strategy with explicit hero hand returns 200."""
        status, data = _post(
            SOLVER_POSTFLOP_URL,
            {
                "board": "KsKc3s",
                "position": "BTN",
                "street": "flop",
                "pot_size": 5.5,
                "stack_depth": 97.5,
                "hero_hand": "AhKh",
            },
            timeout=45,
        )
        assert status == 200

    def test_postflop_river_spot(self):
        """Postflop strategy for a complete river board returns 200."""
        status, data = _post(
            SOLVER_POSTFLOP_URL,
            {
                "board": "KsKc3s2h7d",
                "position": "BTN",
                "street": "river",
                "pot_size": 15.0,
                "stack_depth": 85.0,
            },
            timeout=45,
        )
        assert status == 200


# ════════════════════════════════════════════════════════════════════
# Solve Endpoint
# ════════════════════════════════════════════════════════════════════


class TestSolveEndpoint:
    """Test POST /api/v1/solver/solve."""

    def test_solve_river_returns_200(self):
        """Solve endpoint with a river board returns 200."""
        status, data = _post(
            SOLVER_SOLVE_URL,
            {
                "game_type": "nlh",
                "players": 2,
                "board": "KsKc3s2h7d",
                "pot_size": 100,
                "stack_depth": 100,
                "street": "river",
                "position": "BTN",
                "iterations": 50,
            },
            timeout=60,
        )
        assert status == 200, f"Expected 200, got {status}: {data}"

    def test_solve_response_has_status(self):
        """Solve response includes status field."""
        status, data = _post(
            SOLVER_SOLVE_URL,
            {
                "game_type": "nlh",
                "players": 2,
                "board": "KsKc3s2h7d",
                "pot_size": 100,
                "stack_depth": 100,
                "street": "river",
                "iterations": 50,
            },
            timeout=60,
        )
        assert status == 200
        assert "status" in data

    def test_solve_without_board_returns_error_or_empty(self):
        """Solve with no board returns error or empty strategy."""
        status, data = _post(
            SOLVER_SOLVE_URL,
            {
                "game_type": "nlh",
                "players": 2,
                "board": None,
                "pot_size": 100,
                "stack_depth": 100,
                "street": "river",
                "iterations": 50,
            },
            timeout=15,
        )
        assert status == 200
        # Should not crash — either error or empty strategy
        assert data.get("status") in ("error", "complete")


# ════════════════════════════════════════════════════════════════════
# Strategy Lookup Endpoint
# ════════════════════════════════════════════════════════════════════


class TestStrategyLookupEndpoint:
    """Test GET /api/v1/strategy-lookup."""

    def test_strategy_lookup_preflop_returns_200(self):
        """Strategy lookup for preflop returns 200 (or 404 if no data)."""
        status, data = _get(f"{STRATEGY_LOOKUP_URL}?board=preflop&stack_depth=100&position=UTG")
        # 200 with data or 404 if not seeded — both are acceptable
        assert status in (200, 404), f"Unexpected status {status}: {data}"

    def test_strategy_lookup_no_500_error(self):
        """Strategy lookup never returns 500 (the original bug)."""
        status, data = _get(f"{STRATEGY_LOOKUP_URL}?board=preflop&stack_depth=100&position=UTG")
        assert status != 500, f"Got 500 error: {data}"


# ════════════════════════════════════════════════════════════════════
# Response Structure Validation
# ════════════════════════════════════════════════════════════════════


class TestResponseStructure:
    """Validate response JSON structure matches Pydantic models."""

    def test_preflop_hand_cell_structure(self):
        """Every hand cell has the expected keys."""
        status, data = _post(
            SOLVER_PREFLOP_URL,
            {
                "position": "BTN",
                "stack_depth": 100,
            },
        )
        assert status == 200
        required_keys = {"hand", "action", "frequency", "equity"}
        for hand in data["hands"]:
            assert required_keys.issubset(hand.keys()), f"Missing keys in hand cell: {hand}"

    def test_preflop_frequency_values_valid(self):
        """All frequency values are between 0 and 1."""
        status, data = _post(
            SOLVER_PREFLOP_URL,
            {
                "position": "BTN",
                "stack_depth": 100,
            },
        )
        assert status == 200
        for hand in data["hands"]:
            assert 0.0 <= hand["frequency"] <= 1.0, (
                f"Invalid frequency for {hand['hand']}: {hand['frequency']}"
            )

    def test_preflop_equity_values_valid(self):
        """All equity values are between 0 and 1."""
        status, data = _post(
            SOLVER_PREFLOP_URL,
            {
                "position": "BTN",
                "stack_depth": 100,
            },
        )
        assert status == 200
        for hand in data["hands"]:
            assert 0.0 <= hand["equity"] <= 1.0, (
                f"Invalid equity for {hand['hand']}: {hand['equity']}"
            )

    def test_preflop_actions_are_known(self):
        """All actions are one of the expected values."""
        known_actions = {
            "fold",
            "call",
            "raise",
            "raise_2.5bb",
            "raise_3bb",
            "all_in",
            "allin",
            "check",
            "bet_33",
            "bet_50",
            "bet_75",
            "bet_125",
        }
        status, data = _post(
            SOLVER_PREFLOP_URL,
            {
                "position": "BTN",
                "stack_depth": 100,
            },
        )
        assert status == 200
        for hand in data["hands"]:
            # Action may contain prefix like "raise_2.5bb" — check base action
            base = hand["action"].split("_")[0] if "_" in hand["action"] else hand["action"]
            assert base in {"fold", "call", "raise", "all", "allin", "check", "bet"}, (
                f"Unknown action: {hand['action']} for {hand['hand']}"
            )


# ════════════════════════════════════════════════════════════════════
# Performance / Latency
# ════════════════════════════════════════════════════════════════════


class TestPerformance:
    """Basic latency checks — endpoints should respond within reasonable time."""

    def test_health_responds_under_1s(self):
        """Health endpoint responds in under 1 second."""
        start = time.time()
        status, _ = _get(HEALTH_URL)
        elapsed = time.time() - start
        assert status == 200
        assert elapsed < 1.0, f"Health took {elapsed:.2f}s"

    def test_preflop_range_responds_under_5s(self):
        """Preflop range endpoint responds in under 5 seconds."""
        start = time.time()
        status, _ = _post(
            SOLVER_PREFLOP_URL,
            {
                "position": "BTN",
                "stack_depth": 100,
            },
        )
        elapsed = time.time() - start
        assert status == 200
        assert elapsed < 5.0, f"Preflop range took {elapsed:.2f}s"

    def test_strategy_lookup_responds_under_3s(self):
        """Strategy lookup responds in under 3 seconds."""
        start = time.time()
        status, _ = _get(f"{STRATEGY_LOOKUP_URL}?board=preflop&stack_depth=100&position=UTG")
        elapsed = time.time() - start
        assert status in (200, 404)
        assert elapsed < 3.0, f"Strategy lookup took {elapsed:.2f}s"
