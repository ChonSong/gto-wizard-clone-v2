"""
Redis service for pub/sub and caching.

Handles:
- Solver progress pub/sub via Redis channels
- Job status caching
- WebSocket broadcast integration

Falls back to fakeredis when Redis is not available.
"""

import json
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# Redis connection configuration
REDIS_URL = os.environ.get("REDIS_URL", "")

# Try to import real redis, fall back to fakeredis
_redis_available = False
_redis_module = None

try:
    import redis as _redis_module
    _redis_available = True
except ImportError:
    _redis_module = None

# Try fakeredis
_fakeredis_available = False
_fakeredis = None
try:
    import fakeredis as _fakeredis
    _fakeredis_available = True
except ImportError:
    pass


def _create_redis_client():
    """Create a Redis client, falling back to fakeredis if real Redis is unavailable."""
    if _redis_available and REDIS_URL:
        try:
            client = _redis_module.from_url(REDIS_URL, decode_responses=True)
            client.ping()
            logger.info("Connected to Redis at %s", REDIS_URL)
            return client, True
        except Exception as e:
            logger.warning("Redis connection failed (%s), trying fakeredis", e)

    if _fakeredis_available:
        logger.info("Using fakeredis (in-memory fake)")
        return _fakeredis.FakeRedis(decode_responses=True), False

    # Last resort: create a minimal fake client
    logger.warning("No Redis or fakeredis available, using minimal in-memory stub")
    return _InMemoryStub(), False


class _InMemoryStub:
    """Minimal in-memory stub that mimics basic Redis methods."""

    def __init__(self):
        self._data = {}
        self._pubsub_channels = {}

    def ping(self):
        return True

    def get(self, key):
        val = self._data.get(key)
        if val is not None and isinstance(val, dict) and "expires_at" in val:
            if val["expires_at"] is not None and time.time() > val["expires_at"]:
                del self._data[key]
                return None
            return val["value"]
        if isinstance(val, dict) and "value" in val:
            return val["value"]
        return val

    def set(self, key, value, ex=None):
        expires_at = time.time() + ex if ex is not None else None
        self._data[key] = {"value": value, "expires_at": expires_at}
        return True

    def delete(self, *keys):
        count = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                count += 1
        return count

    def publish(self, channel, message):
        if channel in self._pubsub_channels:
            for callback in self._pubsub_channels[channel]:
                try:
                    callback(message)
                except Exception:
                    pass
        return 0

    def zadd(self, key, mapping):
        if key not in self._data:
            self._data[key] = {}
        self._data[key].update(mapping)
        return len(mapping)

    def zrangebyscore(self, key, min_score, max_score):
        data = self._data.get(key, {})
        result = []
        for member, score in data.items():
            if min_score <= score <= max_score:
                result.append(member)
        return sorted(result)

    def zrevrange(self, key, start, stop):
        data = self._data.get(key, {})
        sorted_items = sorted(data.items(), key=lambda x: x[1], reverse=True)
        if stop >= 0:
            return [m for m, s in sorted_items[start:stop + 1]]
        return [m for m, s in sorted_items[start:]]

    def zrem(self, key, member):
        data = self._data.get(key, {})
        if member in data:
            del data[member]
            return 1
        return 0

    def pubsub(self):
        return self

    def subscribe(self, channels):
        if isinstance(channels, list):
            for ch in channels:
                if ch not in self._pubsub_channels:
                    self._pubsub_channels[ch] = []

    def listen(self):
        return []  # No messages in stub

    def close(self):
        pass


class RedisService:
    """Singleton service for Redis operations with fakeredis fallback."""

    _instance: Optional["RedisService"] = None
    _lock = threading.Lock()

    PROGRESS_CHANNEL_PREFIX = "solver:progress:"

    def __init__(self):
        self._client = None
        self._pubsub_client = None
        self._is_real_redis = False
        self._initialized = False

        self._subscriptions: Dict[str, Callable] = {}
        self._running = False
        self._listener_thread: Optional[threading.Thread] = None

    @classmethod
    def get_instance(cls) -> "RedisService":
        """Get singleton instance of RedisService."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _ensure_initialized(self):
        """Lazily initialize Redis clients on first access."""
        if not self._initialized:
            self._client, self._is_real_redis = _create_redis_client()
            self._pubsub_client, _ = _create_redis_client()
            self._initialized = True

    @property
    def client(self):
        """Get Redis client (lazy initialization)."""
        self._ensure_initialized()
        return self._client

    @property
    def pubsub_client(self):
        """Get separate Redis client for pub/sub subscriptions (lazy initialization)."""
        self._ensure_initialized()
        return self._pubsub_client

    @property
    def is_redis_available(self) -> bool:
        """Check if real Redis is connected."""
        self._ensure_initialized()
        return self._is_real_redis

    def get_progress_channel(self, job_id: str) -> str:
        """Get pub/sub channel name for job progress."""
        return f"{self.PROGRESS_CHANNEL_PREFIX}{job_id}"

    def publish_progress(
        self,
        job_id: str,
        progress: int,
        status: str,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Publish solver progress to Redis pub/sub.

        Args:
            job_id: Unique job identifier
            progress: Progress percentage (0-100)
            status: Job status (queued, running, complete, error)
            extra_data: Additional data to include in the message

        Returns:
            Number of subscribers that received the message
        """
        channel = self.get_progress_channel(job_id)
        message = {
            "job_id": job_id,
            "progress": progress,
            "status": status,
            "timestamp": time.time(),
        }
        if extra_data:
            message.update(extra_data)

        try:
            # Publish to channel
            subscribers = self.client.publish(channel, json.dumps(message))

            # Also cache the latest status
            self.client.set(
                f"job:status:{job_id}",
                json.dumps(message),
                ex=86400,  # 24 hour expiry
            )

            logger.debug("Published progress to %s: %s @ %d%%", channel, status, progress)
            return subscribers

        except Exception as e:
            logger.error("Failed to publish progress for %s: %s", job_id, e)
            return 0

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get cached job status from Redis/fakeredis.

        Args:
            job_id: Job identifier

        Returns:
            Job status dict or None if not found
        """
        try:
            status_json = self.client.get(f"job:status:{job_id}")
            if status_json:
                return json.loads(status_json)

            result_json = self.client.get(f"job:result:{job_id}")
            if result_json:
                return json.loads(result_json)

            return None

        except Exception as e:
            logger.error("Failed to get job status for %s: %s", job_id, e)
            return None

    def set_job_result(self, job_id: str, result: Dict[str, Any], ttl: int = 86400):
        """
        Cache job result in Redis/fakeredis.

        Args:
            job_id: Job identifier
            result: Result data to cache
            ttl: Time-to-live in seconds (default 24 hours)
        """
        try:
            self.client.set(
                f"job:result:{job_id}",
                json.dumps(result),
                ex=ttl,
            )
        except Exception as e:
            logger.error("Failed to cache job result for %s: %s", job_id, e)

    def subscribe_to_progress(
        self,
        job_id: str,
        callback: Callable[[Dict[str, Any]], None],
    ):
        """
        Subscribe to progress updates for a specific job.

        Args:
            job_id: Job identifier to subscribe to
            callback: Function to call when progress is received
        """
        channel = self.get_progress_channel(job_id)
        self._subscriptions[channel] = callback

        # Start listener thread if not running
        if not self._running:
            self._start_listener()

    def unsubscribe_from_progress(self, job_id: str):
        """
        Unsubscribe from progress updates for a job.

        Args:
            job_id: Job identifier to unsubscribe from
        """
        channel = self.get_progress_channel(job_id)
        if channel in self._subscriptions:
            del self._subscriptions[channel]

    def _start_listener(self):
        """Start the pub/sub listener thread."""
        if self._running:
            return

        self._running = True
        self._listener_thread = threading.Thread(
            target=self._listen_for_updates,
            daemon=True,
        )
        self._listener_thread.start()
        logger.info("Started Redis pub/sub listener thread")

    def _listen_for_updates(self):
        """Listen for updates on subscribed channels."""
        try:
            pubsub = self.pubsub_client.pubsub()
        except Exception as e:
            logger.error("Failed to create pubsub connection: %s", e)
            return

        try:
            # Subscribe to all subscribed channels
            if self._subscriptions:
                pubsub.subscribe(list(self._subscriptions.keys()))

                for message in pubsub.listen():
                    if not self._running:
                        break

                    if message["type"] == "message":
                        channel = message["channel"]
                        try:
                            data = json.loads(message["data"])
                            callback = self._subscriptions.get(channel)
                            if callback:
                                callback(data)
                        except json.JSONDecodeError:
                            logger.warning("Invalid JSON in pub/sub message: %s", message["data"])

        except Exception as e:
            logger.error("Error in pub/sub listener: %s", e)
        finally:
            try:
                pubsub.close()
            except Exception:
                pass

    def close(self):
        """Close Redis connections and stop listener."""
        self._running = False
        if self._listener_thread:
            self._listener_thread.join(timeout=2)
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        if self._pubsub_client:
            try:
                self._pubsub_client.close()
            except Exception:
                pass


def get_redis_service() -> RedisService:
    """Get singleton RedisService instance."""
    return RedisService.get_instance()
