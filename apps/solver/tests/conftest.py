"""
Test configuration for solver tests.

Flushes pre-seeded strategy data from Redis before each test session
to ensure test isolation. Tests should not depend on cached data from
development or prior test runs.
"""

import sys
from pathlib import Path

# Add project root to path (4 levels up from apps/solver/tests/)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Also add solver itself
SOLVER_ROOT = Path(__file__).resolve().parents[1]
if str(SOLVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SOLVER_ROOT))


def pytest_sessionstart(session):
    """Flush strategy keys from Redis before test session."""
    try:
        import redis

        r = redis.Redis(host="localhost", port=6379, db=0, socket_connect_timeout=2)
        keys = r.keys("strategy:*")
        if keys:
            for k in keys:
                r.delete(k)
    except Exception:
        pass  # Redis not available — tests should still run
