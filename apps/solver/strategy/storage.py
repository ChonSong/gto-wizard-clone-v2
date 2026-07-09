"""
Storage layer for push/fold charts and GTO strategies.

Handles serialization to JSON and storage in PostgreSQL via the API.
Strategy key format: nlh:2:{street}:{board_hash}:{bet_size}:{stack}

Example keys:
- nlh:2:preflop::100 (preflop, 100bb stack)
- nlh:2:river:Kd7h2c:0.5:100 (river with board, 0.5 pot bet, 100bb)
"""

import json
import logging
import os
import time
from typing import Dict, Optional, List, Any, Union
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager

from .chart_generator import (
    chart_to_json_serializable,
    json_to_chart,
    generate_nash_push_chart,
)

logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/gto_wizard"
)

# Redis configuration
REDIS_URL = os.environ.get(
    "REDIS_URL",
    "redis://localhost:6379/0"
)

# Cache TTL settings
STRATEGY_CACHE_TTL = 3600  # 1 hour default TTL for strategies
REDIS_CACHE_PREFIX = "strategy:"
REDIS_CACHE_TTL = 3600  # 1 hour for Redis cache

# Lazy imports for optional dependencies
_psycopg2 = None
_redis = None
_sqlalchemy = None


def _get_psycopg2():
    """Lazy import psycopg2."""
    global _psycopg2
    if _psycopg2 is None:
        try:
            import psycopg2
            _psycopg2 = psycopg2
        except ImportError:
            logger.warning("psycopg2 not installed, PostgreSQL storage disabled")
            _psycopg2 = False
    return _psycopg2 if _psycopg2 else None


def _get_redis():
    """Lazy import redis."""
    global _redis
    if _redis is None:
        try:
            import redis
            _redis = redis
        except ImportError:
            logger.warning("redis not installed, Redis caching disabled")
            _redis = False
    return _redis if _redis else None


def _get_sqlalchemy():
    """Lazy import SQLAlchemy."""
    global _sqlalchemy
    if _sqlalchemy is None:
        try:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker, Session
            _sqlalchemy = (create_engine, sessionmaker, Session)
        except ImportError:
            logger.warning("SQLAlchemy not installed, PostgreSQL storage disabled")
            _sqlalchemy = False
    return _sqlalchemy if _sqlalchemy else None


@dataclass
class StoredStrategy:
    """Represents a stored strategy with metadata."""
    key: str
    game_type: str  # e.g., "nlh"
    players: int    # e.g., 2
    street: str     # e.g., "preflop", "flop", "turn", "river"
    board_hash: str  # e.g., "Kd7h2c" or "" for preflop
    bet_size: float  # Bet size as fraction of pot (e.g., 0.5 for half-pot)
    stack_depth: int  # Stack depth in big blinds
    strategy_data: Dict[str, Any]  # JSON-serializable strategy data
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class StrategyStorage:
    """
    Storage handler for GTO strategies with PostgreSQL persistence and Redis caching.
    
    Supports:
    - JSON serialization for file storage
    - PostgreSQL storage via SQLAlchemy
    - Redis caching for hot strategies with TTL
    - In-memory LRU-style caching
    
    Strategy key format: nlh:2:{street}:{board_hash}:{bet_size}:{stack}
    
    Example keys:
    - nlh:2:preflop::100 (preflop, 100bb stack)
    - nlh:2:river:Kd7h2c:0.5:100 (river with board, 0.5 pot bet, 100bb)
    """
    
    # Strategy key components
    GAME_TYPE = "nlh"
    PLAYERS = 2
    
    def __init__(
        self,
        database_url: Optional[str] = None,
        redis_url: Optional[str] = None,
        cache_ttl: int = STRATEGY_CACHE_TTL,
    ):
        """
        Initialize strategy storage.
        
        Args:
            database_url: PostgreSQL connection URL
            redis_url: Redis connection URL
            cache_ttl: Default TTL for cached strategies in seconds
        """
        self.database_url = database_url or DATABASE_URL
        self.redis_url = redis_url or REDIS_URL
        self.cache_ttl = cache_ttl
        
        # In-memory cache: key -> (StoredStrategy, timestamp)
        self._cache: Dict[str, tuple] = {}
        
        # Lazy-initialized connections
        self._db_engine = None
        self._db_session_factory = None
        self._redis_client = None
        
        # Track cache age for LRU-style eviction
        self._cache_hits = 0
        self._cache_misses = 0
    
    @property
    def db_engine(self):
        """Lazy initialization of database engine."""
        if self._db_engine is None:
            sa = _get_sqlalchemy()
            if sa is None:
                raise RuntimeError(
                    "SQLAlchemy not installed. Install with: pip install sqlalchemy"
                )
            create_engine, _, _ = sa
            self._db_engine = create_engine(
                self.database_url,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
            )
            self._ensure_tables()
        return self._db_engine
    
    @property
    def redis_client(self):
        """Lazy initialization of Redis client."""
        if self._redis_client is None:
            redis = _get_redis()
            if redis is None:
                raise RuntimeError(
                    "Redis not installed. Install with: pip install redis"
                )
            self._redis_client = redis.from_url(
                self.redis_url,
                decode_responses=True,
            )
        return self._redis_client
    
    def _ensure_tables(self):
        """Ensure the strategies table exists in the database."""
        sa = _get_sqlalchemy()
        if sa is None:
            return
        
        from sqlalchemy import text
        create_table_sql = text("""
            CREATE TABLE IF NOT EXISTS strategies (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                key TEXT UNIQUE NOT NULL,
                game_type TEXT NOT NULL,
                players INTEGER NOT NULL,
                street TEXT NOT NULL,
                board_hash TEXT NOT NULL DEFAULT '',
                bet_size REAL NOT NULL DEFAULT 0,
                stack_depth INTEGER NOT NULL,
                strategy_data JSONB NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            
            CREATE INDEX IF NOT EXISTS idx_strategies_key ON strategies(key);
            CREATE INDEX IF NOT EXISTS idx_strategies_lookup ON strategies(
                game_type, players, street, board_hash, bet_size, stack_depth
            );
        """)
        try:
            with self.db_engine.connect() as conn:
                conn.execute(create_table_sql)
                conn.commit()
        except Exception as e:
            logger.warning(f"Could not create strategies table: {e}")
    
    @contextmanager
    def _get_db_session(self):
        """Context manager for database sessions."""
        sa = _get_sqlalchemy()
        if sa is None:
            raise RuntimeError("SQLAlchemy not installed")
        _, sessionmaker, _ = sa
        
        if self._db_session_factory is None:
            self._db_session_factory = sessionmaker(bind=self.db_engine)
        
        session = self._db_session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    @staticmethod
    def make_strategy_key(
        street: str,
        board_hash: str = "",
        bet_size: float = 0.0,
        stack_depth: int = 100,
        game_type: str = "nlh",
        players: int = 2,
    ) -> str:
        """
        Generate a strategy key.
        
        Format: nlh:2:{street}:{board_hash}:{bet_size}:{stack}
        
        Args:
            street: Street name (preflop, flop, turn, river)
            board_hash: Board cards hash (e.g., "Kd7h2c" or "" for preflop)
            bet_size: Bet size as fraction of pot (e.g., 0.5 for half-pot)
            stack_depth: Stack depth in big blinds
            game_type: Game type (nlh, plo)
            players: Number of players
            
        Returns:
            Strategy key string
        """
        return f"{game_type}:{players}:{street}:{board_hash}:{bet_size}:{stack_depth}"
    
    @staticmethod
    def parse_strategy_key(key: str) -> Dict[str, Any]:
        """
        Parse a strategy key into components.
        
        Args:
            key: Strategy key like "nlh:2:river:Kd7h2c:0.5:100"
            
        Returns:
            Dict with game_type, players, street, board_hash, bet_size, stack_depth
        """
        parts = key.split(":")
        if len(parts) != 6:
            raise ValueError(f"Invalid strategy key format: {key}. Expected 6 parts separated by ':'")
        
        return {
            "game_type": parts[0],
            "players": int(parts[1]),
            "street": parts[2],
            "board_hash": parts[3],
            "bet_size": float(parts[4]) if parts[4] else 0.0,
            "stack_depth": int(parts[5]),
        }
    
    def _get_from_memory_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """Get strategy from in-memory cache if not expired."""
        if key in self._cache:
            strategy, timestamp = self._cache[key]
            if time.time() - timestamp < self.cache_ttl:
                self._cache_hits += 1
                return strategy.strategy_data
            else:
                del self._cache[key]
        return None
    
    def _set_in_memory_cache(self, key: str, strategy: StoredStrategy):
        """Set strategy in memory cache with current timestamp."""
        # Simple LRU: keep cache size bounded
        if len(self._cache) > 1000:
            # Remove oldest 100 entries
            oldest = sorted(
                self._cache.items(),
                key=lambda x: x[1][1]
            )[:100]
            for k, _ in oldest:
                del self._cache[k]
        
        self._cache[key] = (strategy, time.time())
    
    def _get_from_redis_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """Get strategy from Redis cache if available and not expired."""
        redis = _get_redis()
        if redis is None:
            return None
        
        try:
            cache_key = f"{REDIS_CACHE_PREFIX}{key}"
            cached = self.redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Redis cache get failed for {key}: {e}")
        
        return None
    
    def _set_in_redis_cache(self, key: str, strategy_data: Dict[str, Any]):
        """Set strategy in Redis cache with TTL."""
        redis = _get_redis()
        if redis is None:
            return
        
        try:
            cache_key = f"{REDIS_CACHE_PREFIX}{key}"
            self.redis_client.setex(
                cache_key,
                REDIS_CACHE_TTL,
                json.dumps(strategy_data)
            )
        except Exception as e:
            logger.warning(f"Redis cache set failed for {key}: {e}")
    
    def get_strategy(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get a strategy by key from cache or database.
        
        Args:
            key: Strategy key (e.g., "nlh:2:river:Kd7h2c:0.5:100")
            
        Returns:
            Strategy data dict or None if not found
        """
        # Check memory cache first
        cached = self._get_from_memory_cache(key)
        if cached is not None:
            logger.debug(f"Memory cache hit for {key}")
            return cached
        
        # Check Redis cache
        cached = self._get_from_redis_cache(key)
        if cached is not None:
            logger.debug(f"Redis cache hit for {key}")
            return cached
        
        self._cache_misses += 1
        
        # Query PostgreSQL
        strategy = self._get_from_db(key)
        if strategy is not None:
            # Populate caches
            self._set_in_memory_cache(key, strategy)
            self._set_in_redis_cache(key, strategy.strategy_data)
            return strategy.strategy_data
        
        return None
    
    def _get_from_db(self, key: str) -> Optional[StoredStrategy]:
        """Get strategy from PostgreSQL database."""
        sa = _get_sqlalchemy()
        if sa is None:
            return None
        
        from sqlalchemy import text
        
        sql = text("""
            SELECT key, game_type, players, street, board_hash, bet_size,
                   stack_depth, strategy_data, created_at, updated_at
            FROM strategies
            WHERE key = :key
        """)
        
        try:
            with self._get_db_session() as session:
                result = session.execute(sql, {"key": key})
                row = result.fetchone()
                
                if row:
                    return StoredStrategy(
                        key=row.key,
                        game_type=row.game_type,
                        players=row.players,
                        street=row.street,
                        board_hash=row.board_hash,
                        bet_size=row.bet_size,
                        stack_depth=row.stack_depth,
                        strategy_data=row.strategy_data,
                        created_at=row.created_at,
                        updated_at=row.updated_at,
                    )
        except Exception as e:
            logger.error(f"Database query failed for {key}: {e}")
        
        return None
    
    def save_strategy(
        self,
        street: str,
        strategy_data: Dict[str, Any],
        board_hash: str = "",
        bet_size: float = 0.0,
        stack_depth: int = 100,
        game_type: str = "nlh",
        players: int = 2,
    ) -> StoredStrategy:
        """
        Save a strategy to PostgreSQL and update caches.
        
        Args:
            street: Street name (preflop, flop, turn, river)
            strategy_data: Strategy data dict
            board_hash: Board cards hash (e.g., "Kd7h2c" or "" for preflop)
            bet_size: Bet size as fraction of pot
            stack_depth: Stack depth in big blinds
            game_type: Game type (nlh, plo)
            players: Number of players
            
        Returns:
            StoredStrategy object
        """
        key = self.make_strategy_key(
            street, board_hash, bet_size, stack_depth, game_type, players
        )
        
        now = datetime.now(timezone.utc)
        strategy = StoredStrategy(
            key=key,
            game_type=game_type,
            players=players,
            street=street,
            board_hash=board_hash,
            bet_size=bet_size,
            stack_depth=stack_depth,
            strategy_data=strategy_data,
            created_at=now,
            updated_at=now,
        )
        
        # Try to save to PostgreSQL, but continue even if it fails
        db_saved = False
        try:
            self._save_to_db(strategy)
            db_saved = True
        except Exception as e:
            logger.warning(f"Could not save to database for {key}: {e}. Caching only.")
        
        # Update caches
        self._set_in_memory_cache(key, strategy)
        self._set_in_redis_cache(key, strategy_data)
        
        if db_saved:
            logger.info(f"Saved strategy: {key}")
        else:
            logger.debug(f"Cached strategy (no DB): {key}")
        
        return strategy
    
    def _save_to_db(self, strategy: StoredStrategy):
        """Save strategy to PostgreSQL database."""
        sa = _get_sqlalchemy()
        if sa is None:
            raise RuntimeError("SQLAlchemy not installed")
        
        from sqlalchemy import text
        
        sql = text("""
            INSERT INTO strategies 
                (key, game_type, players, street, board_hash, bet_size,
                 stack_depth, strategy_data, created_at, updated_at)
            VALUES 
                (:key, :game_type, :players, :street, :board_hash, :bet_size,
                 :stack_depth, :strategy_data, :created_at, :updated_at)
            ON CONFLICT (key) DO UPDATE SET
                strategy_data = EXCLUDED.strategy_data,
                updated_at = EXCLUDED.updated_at
        """)
        
        try:
            with self._get_db_session() as session:
                session.execute(sql, {
                    "key": strategy.key,
                    "game_type": strategy.game_type,
                    "players": strategy.players,
                    "street": strategy.street,
                    "board_hash": strategy.board_hash,
                    "bet_size": strategy.bet_size,
                    "stack_depth": strategy.stack_depth,
                    "strategy_data": json.dumps(strategy.strategy_data),
                    "created_at": strategy.created_at,
                    "updated_at": strategy.updated_at,
                })
        except Exception as e:
            logger.error(f"Database save failed for {strategy.key}: {e}")
            raise
    
    def get_strategy_by_params(
        self,
        street: str,
        board_hash: str = "",
        bet_size: float = 0.0,
        stack_depth: int = 100,
        game_type: str = "nlh",
        players: int = 2,
    ) -> Optional[Dict[str, Any]]:
        """
        Get a strategy by its parameters.
        
        Args:
            street: Street name
            board_hash: Board cards hash
            bet_size: Bet size as fraction of pot
            stack_depth: Stack depth in big blinds
            game_type: Game type
            players: Number of players
            
        Returns:
            Strategy data dict or None if not found
        """
        key = self.make_strategy_key(
            street, board_hash, bet_size, stack_depth, game_type, players
        )
        return self.get_strategy(key)
    
    def delete_strategy(self, key: str) -> bool:
        """
        Delete a strategy from database and caches.
        
        Args:
            key: Strategy key
            
        Returns:
            True if deleted, False if not found
        """
        sa = _get_sqlalchemy()
        if sa is None:
            # Can't delete from DB without SQLAlchemy
            return False
        
        from sqlalchemy import text
        
        # Delete from PostgreSQL
        sql = text("DELETE FROM strategies WHERE key = :key")
        
        try:
            with self._get_db_session() as session:
                result = session.execute(sql, {"key": key})
                deleted = result.rowcount > 0
        except Exception as e:
            logger.error(f"Database delete failed for {key}: {e}")
            return False
        
        # Remove from caches
        if key in self._cache:
            del self._cache[key]
        
        redis = _get_redis()
        if redis is not None:
            try:
                cache_key = f"{REDIS_CACHE_PREFIX}{key}"
                self.redis_client.delete(cache_key)
            except Exception as e:
                logger.warning(f"Redis cache delete failed for {key}: {e}")
        
        if deleted:
            logger.info(f"Deleted strategy: {key}")
        
        return deleted
    
    def list_strategies(
        self,
        game_type: Optional[str] = None,
        players: Optional[int] = None,
        street: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List strategies with optional filters.
        
        Args:
            game_type: Filter by game type
            players: Filter by number of players
            street: Filter by street
            limit: Maximum number of results
            
        Returns:
            List of strategy metadata dicts
        """
        sa = _get_sqlalchemy()
        if sa is None:
            return []
        
        from sqlalchemy import text
        
        conditions = []
        params = {"limit": limit}
        
        if game_type:
            conditions.append("game_type = :game_type")
            params["game_type"] = game_type
        if players:
            conditions.append("players = :players")
            params["players"] = players
        if street:
            conditions.append("street = :street")
            params["street"] = street
        
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)
        
        sql = text(f"""
            SELECT key, game_type, players, street, board_hash, bet_size,
                   stack_depth, created_at, updated_at
            FROM strategies
            {where_clause}
            ORDER BY updated_at DESC
            LIMIT :limit
        """)
        
        try:
            with self._get_db_session() as session:
                result = session.execute(sql, params)
                return [
                    {
                        "key": row.key,
                        "game_type": row.game_type,
                        "players": row.players,
                        "street": row.street,
                        "board_hash": row.board_hash,
                        "bet_size": row.bet_size,
                        "stack_depth": row.stack_depth,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    }
                    for row in result.fetchall()
                ]
        except Exception as e:
            logger.error(f"Database list failed: {e}")
            return []
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total if total > 0 else 0
        
        return {
            "memory_cache_size": len(self._cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": hit_rate,
        }
    
    def clear_cache(self):
        """Clear all in-memory cache entries."""
        self._cache.clear()
        logger.info("Cleared in-memory strategy cache")
    
    def to_json(self, strategy: StoredStrategy) -> str:
        """
        Serialize a StoredStrategy to JSON string.
        
        Args:
            strategy: StoredStrategy to serialize
            
        Returns:
            JSON string
        """
        return json.dumps({
            "key": strategy.key,
            "game_type": strategy.game_type,
            "players": strategy.players,
            "street": strategy.street,
            "board_hash": strategy.board_hash,
            "bet_size": strategy.bet_size,
            "stack_depth": strategy.stack_depth,
            "strategy_data": strategy.strategy_data,
            "created_at": strategy.created_at.isoformat() if strategy.created_at else None,
            "updated_at": strategy.updated_at.isoformat() if strategy.updated_at else None,
        })
    
    def from_json(self, json_str: str) -> StoredStrategy:
        """
        Deserialize a StoredStrategy from JSON string.
        
        Args:
            json_str: JSON string
            
        Returns:
            StoredStrategy object
        """
        data = json.loads(json_str)
        return StoredStrategy(
            key=data["key"],
            game_type=data["game_type"],
            players=data["players"],
            street=data["street"],
            board_hash=data.get("board_hash", ""),
            bet_size=data.get("bet_size", 0.0),
            stack_depth=data["stack_depth"],
            strategy_data=data["strategy_data"],
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(timezone.utc),
        )


class StrategyCache:
    """
    In-memory cache for strategy lookups with TTL support.
    """
    
    def __init__(self, ttl_seconds: int = 3600):
        """
        Initialize cache.
        
        Args:
            ttl_seconds: Time-to-live for cached entries
        """
        self._cache: Dict[str, tuple] = {}  # key -> (value, timestamp)
        self.ttl_seconds = ttl_seconds
    
    def _is_expired(self, timestamp: float) -> bool:
        """Check if a cache entry has expired."""
        import time
        return time.time() - timestamp > self.ttl_seconds
    
    def get(self, key: str) -> Optional[Dict]:
        """Get value from cache if not expired."""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if not self._is_expired(timestamp):
                return value
            del self._cache[key]
        return None
    
    def set(self, key: str, value: Dict):
        """Set value in cache with current timestamp."""
        import time
        self._cache[key] = (value, time.time())
    
    def clear(self):
        """Clear all cache entries."""
        self._cache.clear()


# Global cache instance
_strategy_cache = StrategyCache()


def get_cached_chart(stack_depth: int, position: str) -> Optional[Dict[str, str]]:
    """
    Get chart from global cache.
    
    Args:
        stack_depth: Stack size in big blinds
        position: Position name
        
    Returns:
        Chart or None if not cached
    """
    key = f"{stack_depth}:{position}"
    return _strategy_cache.get(key)


def set_cached_chart(stack_depth: int, position: str, chart: Dict[str, str]):
    """
    Store chart in global cache.

    Args:
        stack_depth: Stack size in big blinds
        position: Position name
        chart: Chart to cache
    """
    key = f"{stack_depth}:{position}"
    _strategy_cache.set(key, chart)


# Backward compatibility: Legacy push/fold chart storage methods

def make_push_fold_key(stack_depth: int, position: str) -> str:
    """
    Generate a push/fold chart key (legacy format).

    Format: nlh:2:preflop:{stack_depth}:{position}

    Args:
        stack_depth: Stack size in big blinds
        position: Position name (lowercase)

    Returns:
        Strategy key string
    """
    return f"nlh:2:preflop:{stack_depth}:{position.lower()}"


def parse_push_fold_key(key: str) -> Dict[str, Any]:
    """
    Parse a push/fold chart key (legacy format).

    Args:
        key: Strategy key like "nlh:2:preflop:20:btn"

    Returns:
        Dict with game_type, players, street, stack_depth, position
    """
    parts = key.split(":")
    if len(parts) != 5:
        raise ValueError(f"Invalid push/fold key format: {key}")

    return {
        "game_type": parts[0],
        "players": int(parts[1]),
        "street": parts[2],
        "stack_depth": int(parts[3]),
        "position": parts[4],
    }


def convert_push_fold_to_strategy(
    stack_depth: int,
    position: str,
    chart: Dict[str, str],
) -> Dict[str, Any]:
    """
    Convert legacy push/fold chart format to strategy_data format.

    Args:
        stack_depth: Stack depth in big blinds
        position: Position name
        chart: Push/fold chart dict

    Returns:
        Strategy data in new format
    """
    return {
        "type": "push_fold",
        "stack_depth": stack_depth,
        "position": position,
        "actions": chart,  # e.g., {"AA": "push", "72o": "fold"}
    }


def convert_strategy_to_push_fold(strategy_data: Dict[str, Any]) -> Dict[str, str]:
    """
    Convert strategy_data format back to legacy push/fold chart format.

    Args:
        strategy_data: Strategy data dict

    Returns:
        Push/fold chart dict
    """
    if strategy_data.get("type") == "push_fold":
        return strategy_data.get("actions", {})
    return strategy_data


class PushFoldStorage:
    """
    Backward-compatible storage for push/fold charts.

    This class provides the legacy API for push/fold charts while
    using the new PostgreSQL-backed StrategyStorage under the hood.
    """

    def __init__(self, strategy_storage: Optional[StrategyStorage] = None):
        """
        Initialize push/fold storage.

        Args:
            strategy_storage: Optional StrategyStorage instance to use.
                           If None, creates a new StrategyStorage.
        """
        self._storage = strategy_storage or StrategyStorage()

    @staticmethod
    def make_strategy_key(stack_depth: int, position: str) -> str:
        """Generate a strategy key (legacy format)."""
        return make_push_fold_key(stack_depth, position)

    @staticmethod
    def parse_strategy_key(key: str) -> Dict[str, Any]:
        """Parse a strategy key (legacy format)."""
        return parse_push_fold_key(key)

    def store_chart(
        self,
        stack_depth: int,
        position: str,
        chart: Dict[str, str],
    ) -> StoredStrategy:
        """
        Store a chart using the new storage system.

        Args:
            stack_depth: Stack size in big blinds
            position: Position name
            chart: Chart in JSON-serializable format

        Returns:
            StoredStrategy object
        """
        strategy_data = convert_push_fold_to_strategy(stack_depth, position, chart)
        return self._storage.save_strategy(
            street="preflop",
            strategy_data=strategy_data,
            board_hash=position.lower(),
            bet_size=0.0,
            stack_depth=stack_depth,
        )

    def get_chart(self, stack_depth: int, position: str) -> Optional[Dict[str, str]]:
        """
        Get a chart from cache or database.

        Args:
            stack_depth: Stack size in big blinds
            position: Position name

        Returns:
            Chart in JSON-serializable format or None
        """
        strategy_data = self._storage.get_strategy_by_params(
            street="preflop",
            board_hash=position.lower(),
            bet_size=0.0,
            stack_depth=stack_depth,
        )
        if strategy_data:
            return convert_strategy_to_push_fold(strategy_data)
        return None

    def get_or_generate_chart(
        self,
        stack_depth: int,
        position: str,
    ) -> Dict[str, str]:
        """
        Get chart from cache or generate if not present.

        Args:
            stack_depth: Stack size in big blinds
            position: Position name

        Returns:
            Chart in JSON-serializable format
        """
        # Try cache first
        cached = self.get_chart(stack_depth, position)
        if cached:
            return cached

        # Generate new chart
        chart = generate_nash_push_chart(stack_depth, position)
        json_chart = chart_to_json_serializable(chart)

        # Store and return
        self.store_chart(stack_depth, position, json_chart)
        return json_chart


# Module-level storage instance for backward compatibility
_push_fold_storage: Optional[PushFoldStorage] = None


def get_push_fold_storage() -> PushFoldStorage:
    """Get the module-level PushFoldStorage instance."""
    global _push_fold_storage
    if _push_fold_storage is None:
        _push_fold_storage = PushFoldStorage()
    return _push_fold_storage
