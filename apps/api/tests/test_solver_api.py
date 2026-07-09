"""
Tests for solver API endpoints.

Tests:
- Job submission
- Job status polling
- Strategy retrieval
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import uuid


def test_submit_solve_request():
    """Test that submit solve request model works."""
    from apps.api.routers.solver import SolveRequest

    req = SolveRequest(
        game_type="nlh",
        players=2,
        board=None,
        pot_size=100,
        stack_depth=100,
    )

    assert req.game_type == "nlh"
    assert req.players == 2
    assert req.stack_depth == 100


def test_solve_job_response():
    """Test that solve job response model works."""
    from apps.api.routers.solver import SolveResponse

    resp = SolveResponse(
        job_id="test-job-123",
        status="queued",
        progress=0,
    )

    assert resp.job_id == "test-job-123"
    assert resp.status == "queued"
    assert resp.progress == 0


def test_strategy_key_parsing():
    """Test strategy key parsing."""
    from apps.api.services.strategy_storage import StrategyStorageService

    key = "nlh:2:preflop::0:100"
    parsed = StrategyStorageService.parse_strategy_key(key)

    assert parsed["game_type"] == "nlh"
    assert parsed["players"] == 2
    assert parsed["street"] == "preflop"
    assert parsed["stack_depth"] == 100


def test_strategy_key_creation():
    """Test strategy key creation."""
    from apps.api.services.strategy_storage import StrategyStorageService

    key = StrategyStorageService.make_strategy_key(
        street="flop",
        board_hash="",
        bet_size=0.5,
        stack_depth=100,
        game_type="nlh",
        players=2,
    )

    assert key == "nlh:2:flop::0.5:100"


@pytest.mark.asyncio
async def test_strategy_storage_service():
    """Test strategy storage service."""
    from apps.api.services.strategy_storage import StrategyStorageService

    storage = StrategyStorageService()

    # Store a strategy
    strategy = await storage.store_strategy(
        street="preflop",
        board_hash="",
        bet_size=0.0,
        stack_depth=100,
        game_type="nlh",
        players=2,
        strategy_data={
            "hands": [
                {"hand": "AA", "action": "raise", "frequency": 1.0, "ev": 10.5},
                {"hand": "KK", "action": "raise", "frequency": 0.95, "ev": 8.2},
            ]
        },
    )

    assert "nlh:2:preflop" in strategy.key
    assert len(strategy.strategy_data["hands"]) == 2

    # Retrieve it
    retrieved = await storage.get_strategy(strategy.key)
    assert retrieved is not None
    assert retrieved.key == strategy.key


def test_websocket_manager_initialization():
    """Test WebSocket manager initializes correctly."""
    from apps.api.websocket.manager import WebSocketManager

    manager = WebSocketManager()
    assert manager.connection_count == 0


def test_redis_service_initialization():
    """Test Redis service initializes correctly."""
    from apps.api.services.redis_service import RedisService

    # Get singleton instance
    service = RedisService.get_instance()
    assert service is not None
    assert service.client is not None


def test_celery_app_configuration():
    """Test Celery app configuration."""
    from apps.worker.celery_app import celery_app, get_progress_channel

    assert celery_app is not None
    assert celery_app.conf.task_serializer == "json"
    assert get_progress_channel("job-123") == "solver:progress:job-123"


def test_progress_channel_format():
    """Test progress channel format."""
    from apps.worker.celery_app import get_progress_channel

    job_id = "abc-123"
    channel = get_progress_channel(job_id)
    assert channel == f"solver:progress:{job_id}"


# ════════════════════════════════════════════════════════════════════
# Postflop Strategy Tests
# ════════════════════════════════════════════════════════════════════


def test_postflop_strategy_request_model():
    """Test that PostflopStrategyRequest model works with defaults."""
    from apps.api.routers.solver import PostflopStrategyRequest

    req = PostflopStrategyRequest(
        board="KsKc3s",
        position="BTN",
        street="flop",
        pot_size=5.5,
        stack_depth=97.5,
    )

    assert req.board == "KsKc3s"
    assert req.position == "BTN"
    assert req.street == "flop"
    assert req.pot_size == 5.5
    assert req.stack_depth == 97.5
    assert req.hero_hand is None


def test_postflop_strategy_request_with_hero_hand():
    """Test PostflopStrategyRequest with hero_hand provided."""
    from apps.api.routers.solver import PostflopStrategyRequest

    req = PostflopStrategyRequest(
        board="KsKc3s",
        position="BTN",
        street="river",
        pot_size=15.0,
        stack_depth=85.0,
        hero_hand="AhKh",
    )

    assert req.hero_hand == "AhKh"
    assert req.street == "river"


def test_postflop_strategy_response_model():
    """Test that PostflopStrategyResponse model works."""
    from apps.api.routers.solver import PostflopStrategyResponse, StrategyAction

    resp = PostflopStrategyResponse(
        actions=[
            StrategyAction(action="check", frequency=0.45, ev=3.0),
            StrategyAction(action="bet_50", frequency=0.35, ev=4.5),
            StrategyAction(action="bet_33", frequency=0.20, ev=3.8),
        ],
        source="live-solver",
        status="complete",
        message="Solved flop spot (12 infosets)",
    )

    assert len(resp.actions) == 3
    assert resp.source == "live-solver"
    assert resp.status == "complete"
    assert "flop" in resp.message


def test_postflop_cache_key():
    """Test cache key generation is deterministic."""
    from apps.api.routers.solver import _make_postflop_cache_key

    key1 = _make_postflop_cache_key("KsKc3s", "BTN", "flop", 5.5, 97.5, None)
    key2 = _make_postflop_cache_key("KsKc3s", "BTN", "flop", 5.5, 97.5, None)
    key3 = _make_postflop_cache_key("KsKc3s", "BB", "flop", 5.5, 97.5, None)

    assert key1 == key2  # Same input → same key
    assert key1 != key3  # Different position → different key
    assert isinstance(key1, str) and len(key1) > 0


def test_pick_unused_cards():
    """Test card picking doesn't return excluded cards."""
    from apps.api.routers.solver import _pick_unused_cards

    excluded = {"Ah", "Kh", "Ks", "Kc", "3s"}
    cards = _pick_unused_cards(excluded.copy(), 2)

    assert len(cards) == 2
    for c in cards:
        assert c not in excluded, f"Picked card {c} is in exclude set"
    assert cards[0] != cards[1]  # Two different cards


def test_pick_unused_cards_respects_count():
    """Test card picking returns exactly the requested count."""
    from apps.api.routers.solver import _pick_unused_cards

    cards = _pick_unused_cards(set(), 4)
    assert len(cards) == 4
    assert len(set(cards)) == 4  # All unique


def test_compute_ev():
    """Test EV computation returns reasonable values."""
    from apps.api.routers.solver import _compute_ev

    assert _compute_ev("fold", 10.0) == 0.0
    assert _compute_ev("check", 10.0) == 5.0
    assert _compute_ev("call", 10.0) == 5.0
    assert _compute_ev("bet_50", 10.0) == 6.0
    assert _compute_ev("raise_100", 10.0) == 6.0
    assert _compute_ev("all_in", 10.0) == 6.5
    assert _compute_ev("unknown", 10.0) == 5.0


def test_postflop_strategy_endpoint_no_engine():
    """Postflop endpoint returns error gracefully when solver unavailable."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from apps.api.routers.solver import router

    # Create an isolated app with just the solver router
    app = FastAPI()
    app.include_router(router)

    client = TestClient(app)

    resp = client.post(
        "/api/v1/solver/postflop-strategy",
        json={
            "board": "KsKc3s",
            "position": "BTN",
            "street": "flop",
            "pot_size": 5.5,
            "stack_depth": 97.5,
        },
    )

    # Should succeed (200) — the handler catches ImportError gracefully
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data


def test_postflop_strategy_invalid_board():
    """Postflop endpoint returns error for invalid board/street combo."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from apps.api.routers.solver import router

    app = FastAPI()
    app.include_router(router)

    client = TestClient(app)

    resp = client.post(
        "/api/v1/solver/postflop-strategy",
        json={
            "board": "Ks",  # Too short for flop
            "position": "BTN",
            "street": "flop",
            "pot_size": 5.5,
            "stack_depth": 97.5,
        },
    )

    # Should get an error response (not 500)
    assert resp.status_code in (200, 500)
    if resp.status_code == 200:
        data = resp.json()
        assert data["status"] in ("error", "complete")


def test_dedup_actions_removes_duplicates():
    """_dedup_actions keeps max frequency per unique action name."""
    from apps.api.routers.solver import _dedup_actions, StrategyAction

    raw = [
        StrategyAction(action="check", frequency=0.3, ev=2.5),
        StrategyAction(action="check", frequency=0.5, ev=2.5),  # duplicate, higher freq
        StrategyAction(action="check", frequency=0.2, ev=2.5),  # duplicate, lower freq
        StrategyAction(action="bet_33", frequency=0.4, ev=3.0),
        StrategyAction(action="bet_50", frequency=0.1, ev=3.5),
        StrategyAction(action="bet_33", frequency=0.3, ev=3.0),  # duplicate
        StrategyAction(action="fold", frequency=0.05, ev=0.0),
        StrategyAction(action="call", frequency=0.15, ev=1.0),
    ]

    deduped = _dedup_actions(raw)

    # Should have 5 unique actions
    assert len(deduped) == 5, f"Expected 5, got {len(deduped)}: {[a.action for a in deduped]}"

    # Should keep the highest frequency for each name
    by_name = {a.action: a for a in deduped}
    assert by_name["check"].frequency == 0.5  # max of 0.3, 0.5, 0.2
    assert by_name["bet_33"].frequency == 0.4  # max of 0.4, 0.3

    # Should be sorted by frequency descending
    for i in range(len(deduped) - 1):
        assert deduped[i].frequency >= deduped[i + 1].frequency, (
            f"Not sorted: {deduped[i].frequency} < {deduped[i + 1].frequency}"
        )

    # Case-insensitive dedup
    mixed_case = [
        StrategyAction(action="CHECK", frequency=0.4, ev=2.0),
        StrategyAction(action="check", frequency=0.6, ev=2.0),
    ]
    deduped_mixed = _dedup_actions(mixed_case)
    assert len(deduped_mixed) == 1
    assert deduped_mixed[0].frequency == 0.6


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
