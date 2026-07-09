"""
Redis to WebSocket bridge for solver progress streaming.

This module provides the missing bridge between:
1. Celery tasks publishing progress to Redis pub/sub (solver:progress:{job_id})
2. WebSocket clients subscribed to job progress updates

The bridge runs as a background task that:
1. Subscribes to Redis pub/sub channels for active jobs
2. Forwards progress messages to the WebSocket manager
3. Cleans up subscriptions when jobs complete

Usage:
    from apps.api.services.redis_bridge import start_redis_bridge
    
    # Start the bridge (typically during app startup)
    await start_redis_bridge()
"""

import asyncio
import json
import logging
import threading
from typing import Dict, Optional, Callable, Any
from datetime import datetime, timezone

from apps.api.websocket.manager import get_websocket_manager, WebSocketManager

logger = logging.getLogger(__name__)

# Redis connection configuration
import os
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
PROGRESS_CHANNEL_PREFIX = "solver:progress:"


class RedisToWebSocketBridge:
    """
    Bridge that forwards Redis pub/sub solver progress to WebSocket clients.
    
    This solves the missing link between:
    - apps/worker/tasks.py:publish_progress() publishes to Redis
    - apps/api/routers/solver.py:solver_websocket() expects WebSocket updates
    - apps/api/websocket/manager.py:handle_solver_progress() exists but never called
    
    The bridge runs a listener thread that subscribes to solver:progress:* channels
    and forwards messages to the WebSocket manager.
    """
    
    def __init__(self, redis_url: str = REDIS_URL):
        self.redis_url = redis_url
        self._redis_client = None
        self._pubsub_client = None
        self._listener_thread: Optional[threading.Thread] = None
        self._running = False
        self._subscriptions: Dict[str, Callable] = {}
        self._lock = threading.Lock()
        self._active_jobs: Dict[str, int] = {}  # job_id -> last_activity timestamp
    
    @property
    def redis_client(self):
        """Lazy Redis client initialization."""
        if self._redis_client is None:
            import redis
            self._redis_client = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._redis_client
    
    @property
    def pubsub_client(self):
        """Lazy pub/sub Redis client initialization."""
        if self._pubsub_client is None:
            import redis
            self._pubsub_client = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._pubsub_client
    
    def _get_progress_channel(self, job_id: str) -> str:
        """Get pub/sub channel name for job progress."""
        return f"{PROGRESS_CHANNEL_PREFIX}{job_id}"
    
    async def start(self):
        """
        Start the Redis-to-WebSocket bridge.
        
        Should be called during application startup.
        """
        if self._running:
            logger.warning("Redis bridge already running")
            return
        
        self._running = True
        self._listener_thread = threading.Thread(
            target=self._listener_loop,
            daemon=True,
            name="RedisBridgeListener"
        )
        self._listener_thread.start()
        logger.info("Redis-to-WebSocket bridge started")
    
    def stop(self):
        """Stop the bridge and cleanup resources."""
        self._running = False
        if self._listener_thread:
            self._listener_thread.join(timeout=5)
        logger.info("Redis-to-WebSocket bridge stopped")
    
    def _listener_loop(self):
        """
        Main listener loop running in background thread.
        
        Subscribes to all active job progress channels and forwards
        messages to the WebSocket manager.
        """
        import redis
        
        pubsub = self.pubsub_client.pubsub()
        
        try:
            # Initial subscription to pattern
            pubsub.psubscribe(f"{PROGRESS_CHANNEL_PREFIX}*")
            logger.info(f"Subscribed to {PROGRESS_CHANNEL_PREFIX}* pattern")
            
            while self._running:
                try:
                    message = pubsub.get_message(timeout=0.5)
                    if message and message['type'] == 'pmessage':
                        self._handle_message(message)
                except Exception as e:
                    logger.error(f"Error in bridge listener: {e}")
                    if self._running:
                        # Reconnect on error
                        try:
                            pubsub.close()
                            pubsub = self.pubsub_client.pubsub()
                            pubsub.psubscribe(f"{PROGRESS_CHANNEL_PREFIX}*")
                        except Exception as re:
                            logger.error(f"Failed to reconnect: {re}")
                            import time
                            time.sleep(1)
                            
        except Exception as e:
            logger.error(f"Redis bridge listener failed: {e}")
        finally:
            pubsub.close()
    
    def _handle_message(self, message: dict):
        """
        Handle incoming Redis pub/sub message.
        
        Forwards progress to WebSocket manager via handle_solver_progress.
        """
        try:
            channel = message['channel']
            data = json.loads(message['data'])
            
            # Extract job_id from channel (format: solver:progress:{job_id})
            job_id = data.get('job_id')
            if not job_id:
                # Try to extract from channel
                if channel.startswith(PROGRESS_CHANNEL_PREFIX):
                    job_id = channel[len(PROGRESS_CHANNEL_PREFIX):]
            
            if not job_id:
                logger.warning(f"No job_id in progress message: {data}")
                return
            
            # Update last activity
            with self._lock:
                self._active_jobs[job_id] = datetime.now(timezone.utc).timestamp()
            
            # Forward to WebSocket manager
            ws_manager = get_websocket_manager()
            
            # Create progress message
            progress_msg = {
                "type": "solve:progress",
                "job_id": job_id,
                "progress": data.get('progress', 0),
                "status": data.get('status', 'running'),
                "stage": data.get('stage', ''),
                "iteration": data.get('iteration', 0),
                "total_iterations": data.get('total_iterations', 0),
                "infosets": data.get('infosets', 0),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            
            # Broadcast to all clients subscribed to this job
            # Note: This is synchronous but WebSocketManager methods are async
            # We need to use asyncio to call them from this thread
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    # Schedule the broadcast
                    loop.run_until_complete(
                        ws_manager.broadcast_to_job(job_id, progress_msg)
                    )
                finally:
                    loop.close()
            except Exception as e:
                logger.warning(f"Failed to broadcast to job {job_id}: {e}")
            
            logger.debug(f"Forwarded progress for job {job_id}: {data.get('progress')}%")
            
            # Check if job is complete and cleanup
            if data.get('status') in ('complete', 'error'):
                with self._lock:
                    if job_id in self._active_jobs:
                        del self._active_jobs[job_id]
                logger.info(f"Job {job_id} completed with status {data.get('status')}")
                
                # Send completion message
                complete_msg = {
                    "type": "solve:complete" if data.get('status') == 'complete' else "solve:error",
                    "job_id": job_id,
                    "progress": 100 if data.get('status') == 'complete' else 0,
                    "status": data.get('status'),
                    "error": data.get('error', ''),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(
                            ws_manager.broadcast_to_job(job_id, complete_msg)
                        )
                    finally:
                        loop.close()
                except Exception as e:
                    logger.warning(f"Failed to send completion for job {job_id}: {e}")
                    
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in pub/sub message: {e}")
        except Exception as e:
            logger.error(f"Error handling Redis message: {e}")
    
    def get_active_jobs(self) -> Dict[str, int]:
        """Get dict of active jobs and their last activity timestamp."""
        with self._lock:
            return dict(self._active_jobs)
    
    @property
    def is_running(self) -> bool:
        """Check if bridge is running."""
        return self._running


# Global bridge instance
_bridge: Optional[RedisToWebSocketBridge] = None
_bridge_lock = threading.Lock()


def get_redis_bridge() -> RedisToWebSocketBridge:
    """Get singleton Redis-to-WebSocket bridge instance."""
    global _bridge
    if _bridge is None:
        with _bridge_lock:
            if _bridge is None:
                _bridge = RedisToWebSocketBridge()
    return _bridge


async def start_redis_bridge():
    """Start the Redis-to-WebSocket bridge (call during app startup)."""
    bridge = get_redis_bridge()
    await bridge.start()


def stop_redis_bridge():
    """Stop the Redis-to-WebSocket bridge (call during app shutdown)."""
    global _bridge
    if _bridge:
        _bridge.stop()
        _bridge = None