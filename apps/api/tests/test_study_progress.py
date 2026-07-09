"""
Tests for study progress API endpoints.

Uses an isolated FastAPI app with just the study_progress router
and a fresh file-based SQLite database per test function.
"""

import os
import uuid
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from apps.api.services.database import Base
from apps.api.routers.study_progress import router as study_progress_router


@pytest.fixture(scope="function")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="function")
async def app():
    """Create a minimal FastAPI app with fresh file-based DB per test."""
    db_path = f"/tmp/test_study_progress_{uuid.uuid4().hex}.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    os.environ["DATABASE_URL"] = db_url

    from apps.api.services import database as db_module

    # Override the module-level constant (evaluated at import time)
    db_module.DATABASE_URL = db_url
    db_module._engine = None
    db_module._session_factory = None

    app = FastAPI()
    app.include_router(study_progress_router)

    from apps.api.models.study_progress import StudyProgress

    engine = db_module.get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(StudyProgress.__table__.create, checkfirst=True)

    yield app

    # Teardown
    db_module._engine = None
    db_module._session_factory = None
    try:
        os.remove(db_path)
    except OSError:
        pass


@pytest_asyncio.fixture
async def client(app):
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_post_progress_returns_201(client):
    """POST with valid payload returns 201 with id and created_at."""
    resp = await client.post(
        "/api/v1/study/progress",
        json={
            "hand": "AA",
            "position": "UTG",
            "stack_depth": 100,
            "action_chosen": "raise_2.5bb",
            "action_gto": "raise_2.5bb",
            "correct": True,
            "user_id": "test-user",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert "created_at" in data
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_post_progress_missing_field_returns_422(client):
    """POST with missing required field returns 422."""
    resp = await client.post(
        "/api/v1/study/progress",
        json={
            "hand": "AA",
            "position": "UTG",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_progress_optional_user_id_defaults(client):
    """POST without user_id defaults to 'anonymous'."""
    resp = await client.post(
        "/api/v1/study/progress",
        json={
            "hand": "KK",
            "position": "BTN",
            "stack_depth": 100,
            "action_chosen": "call",
            "action_gto": "raise_2.5bb",
            "correct": False,
        },
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_get_progress_returns_aggregated_stats(client):
    """GET /api/v1/study/progress?user_id=stats-test returns aggregated stats."""
    for record in [
        {
            "hand": "AA",
            "position": "UTG",
            "stack_depth": 100,
            "action_chosen": "raise_2.5bb",
            "action_gto": "raise_2.5bb",
            "correct": True,
            "user_id": "stats-test",
        },
        {
            "hand": "KK",
            "position": "BTN",
            "stack_depth": 100,
            "action_chosen": "fold",
            "action_gto": "raise_2.5bb",
            "correct": False,
            "user_id": "stats-test",
        },
        {
            "hand": "AKs",
            "position": "UTG",
            "stack_depth": 50,
            "action_chosen": "raise_2.0bb",
            "action_gto": "raise_2.0bb",
            "correct": True,
            "user_id": "stats-test",
        },
    ]:
        await client.post("/api/v1/study/progress", json=record)

    resp = await client.get("/api/v1/study/progress?user_id=stats-test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "stats-test"
    assert data["total_hands"] == 3
    assert data["correct_hands"] == 2
    assert data["overall_accuracy"] == pytest.approx(2 / 3, abs=0.01)
    assert "by_position" in data
    assert "by_action" in data
    assert "recent_sessions" in data
    assert "last_week" in data
    assert "current_streak" in data
    assert "best_streak" in data


@pytest.mark.asyncio
async def test_get_progress_returns_position_breakdown(client):
    """GET progress returns accuracy by position."""
    for record in [
        {
            "hand": "AA",
            "position": "UTG",
            "stack_depth": 100,
            "action_chosen": "raise_2.5bb",
            "action_gto": "raise_2.5bb",
            "correct": True,
            "user_id": "pos-test",
        },
        {
            "hand": "KK",
            "position": "UTG",
            "stack_depth": 100,
            "action_chosen": "fold",
            "action_gto": "raise_2.5bb",
            "correct": False,
            "user_id": "pos-test",
        },
        {
            "hand": "AKs",
            "position": "BTN",
            "stack_depth": 100,
            "action_chosen": "raise_2.0bb",
            "action_gto": "raise_2.0bb",
            "correct": True,
            "user_id": "pos-test",
        },
    ]:
        await client.post("/api/v1/study/progress", json=record)

    resp = await client.get("/api/v1/study/progress?user_id=pos-test")
    data = resp.json()
    pos_map = {p["position"]: p for p in data["by_position"]}
    assert "UTG" in pos_map
    assert pos_map["UTG"]["total"] == 2
    assert pos_map["UTG"]["correct"] == 1
    assert pos_map["UTG"]["accuracy"] == 0.5
    assert "BTN" in pos_map
    assert pos_map["BTN"]["total"] == 1
    assert pos_map["BTN"]["correct"] == 1


@pytest.mark.asyncio
async def test_get_progress_empty_history(client):
    """GET progress for user with no records returns zero stats."""
    resp = await client.get("/api/v1/study/progress?user_id=empty-user")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_hands"] == 0
    assert data["correct_hands"] == 0
    assert data["overall_accuracy"] == 0.0
    assert data["by_position"] == []
    assert data["by_action"] == []
