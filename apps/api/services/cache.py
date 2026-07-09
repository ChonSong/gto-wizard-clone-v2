"""
Response caching utility for FastAPI endpoints.

Provides a simple TTL-based cache backed by the app's Redis/fakeredis client.
Falls back to an in-memory LRU cache when Redis is unavailable.

Usage:
    from apps.api.services.cache import cached, init_cache

    # In main.py startup:
    init_cache(app)

    # On any endpoint:
    @router.get("/endpoint")
    @cached(ttl=300)  # 5 minutes
    async def my_endpoint():
        ...
"""

import asyncio
import functools
import hashlib
import json
import logging
import time
from typing import Any, Callable, Dict, Optional, Tuple

from fastapi import FastAPI

logger = logging.getLogger(__name__)

# In-memory fallback cache when Redis/fakeredis is not available
_memory_cache: Dict[str, Tuple[Any, Optional[float]]] = {}  # key -> (value, expires_at)
_memory_cache_max = 500

# Reference to the app's Redis client (set via init_cache)
_app_redis = None


def init_cache(app: FastAPI):
    """Initialize the cache module with the app's Redis client."""
    global _app_redis
    try:
        _app_redis = getattr(app.state, "redis", None)
    except Exception:
        _app_redis = None


def _make_cache_key(prefix: str, args: Tuple, kwargs: Dict) -> str:
    """Generate a deterministic cache key from function arguments."""
    key_parts = [prefix]
    key_parts.append(str(args))
    key_parts.append(str(sorted(kwargs.items())))
    raw = ":".join(key_parts)
    return hashlib.md5(raw.encode()).hexdigest()


def _get_from_memory(key: str) -> Optional[Any]:
    """Get value from in-memory cache if not expired."""
    if key in _memory_cache:
        value, expires_at = _memory_cache[key]
        if expires_at is None or time.time() < expires_at:
            return value
        del _memory_cache[key]
    return None


def _set_in_memory(key: str, value: Any, ttl: int):
    """Set value in in-memory cache with TTL."""
    # Bound cache size
    if len(_memory_cache) >= _memory_cache_max:
        # Remove oldest 10% of entries
        oldest = sorted(_memory_cache.items(), key=lambda x: x[1][1])[:50]
        for k, _ in oldest:
            del _memory_cache[k]

    expires_at = time.time() + ttl if ttl else None
    _memory_cache[key] = (value, expires_at)


def cached(ttl: int = 60):
    """
    Decorator that caches endpoint responses with TTL.

    Uses the application's Redis/fakeredis client (app.state.redis) if available,
    otherwise falls back to an in-memory LRU cache.

    Args:
        ttl: Time-to-live in seconds (default: 60)

    Usage:
        @router.get("/courses")
        @cached(ttl=300)
        async def list_courses():
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Build cache key from function name and arguments
            cache_key = _make_cache_key(f"resp:{func.__name__}", args, kwargs)

            # Try app-level Redis/fakeredis cache first
            redis = _app_redis
            if redis is not None:
                try:
                    cached_json = redis.get(cache_key)
                    if cached_json:
                        return json.loads(cached_json)
                except Exception as e:
                    logger.debug(f"Redis cache miss/error for {cache_key}: {e}")
            else:
                # Fallback to in-memory cache
                cached_value = _get_from_memory(cache_key)
                if cached_value is not None:
                    return cached_value

            # Cache miss — call the function
            result = await func(*args, **kwargs)

            # Cache the result
            try:
                # Handle Pydantic models
                if hasattr(result, "model_dump"):
                    serialized = json.dumps(result.model_dump(), default=str)
                elif hasattr(result, "dict"):
                    serialized = json.dumps(result.dict(), default=str)
                else:
                    serialized = json.dumps(result, default=str)
                if redis is not None:
                    try:
                        redis.setex(cache_key, ttl, serialized)
                    except Exception as e:
                        logger.debug(f"Redis cache set failed: {e}")
                        _set_in_memory(cache_key, result, ttl)
                else:
                    _set_in_memory(cache_key, result, ttl)
            except (TypeError, ValueError) as e:
                logger.debug(f"Could not serialize response for caching: {e}")

            return result

        return wrapper

    return decorator
