"""
Strategy storage service for PostgreSQL with Redis caching.

Handles serialization and storage of solved GTO strategies with
board-specific lookups for flop/turn/river strategies.

Key format: nlh:2:{street}:{board_hash}:{bet_size}:{stack_depth}

Example keys:
- nlh:2:preflop::100 (preflop, 100bb stack)
- nlh:2:flop:Kd7h2c:0.5:100 (flop with board, 0.5 pot bet, 100bb)
- nlh:2:river:Kd7h2c:0.5:100 (river with board, 0.5 pot bet, 100bb)
"""

import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Database configuration from environment
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/gto_wizard"
)

# Redis configuration
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Cache TTL settings
STRATEGY_CACHE_TTL = int(os.environ.get("STRATEGY_CACHE_TTL", "604800"))  # 7 days
REDIS_CACHE_PREFIX = "gto:strategy:"


class StrategyAction(BaseModel):
    """Single action in a strategy."""

    hand: str  # e.g., "AKs", "TT", "72o"
    action: str  # "raise", "call", "fold", "check"
    frequency: float = Field(default=1.0, ge=0.0, le=1.0)  # Probability
    ev: float = Field(default=0.0, description="Expected value in big blinds")


class StoredStrategy(BaseModel):
    """Full stored strategy with metadata."""

    id: Optional[str] = None
    key: str  # Strategy key
    game_type: str = "nlh"  # "nlh", "plo"
    players: int = 2
    street: str = "preflop"  # "preflop", "flop", "turn", "river"
    board_hash: str = ""  # e.g., "Kd7h2c" or "" for preflop
    bet_size: float = 0.0  # Bet size as fraction of pot
    stack_depth: int = 100  # Stack depth in big blinds
    strategy_data: Dict[str, Any] = Field(default_factory=dict)  # Actions with frequencies
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class StrategyFilters(BaseModel):
    """Filters for listing strategies."""

    game_type: Optional[str] = "nlh"
    players: Optional[int] = 2
    street: Optional[str] = None
    board_hash: Optional[str] = None
    stack_depth: Optional[int] = None
    limit: int = 100
    offset: int = 0


class StrategyStorageService:
    """
    Service for storing and retrieving GTO strategies from PostgreSQL.

    Uses Redis as L1 cache with PostgreSQL as backing store.

    Strategy key format: nlh:2:{street}:{board_hash}:{bet_size}:{stack_depth}

    Example keys:
    - nlh:2:preflop::100
    - nlh:2:flop:Kd7h2c:0.5:100
    - nlh:2:river:Kd7h2c:0.5:100
    """

    _instance: Optional["StrategyStorageService"] = None
    _lock: asyncio.Lock = None

    def __init__(
        self,
        database_url: Optional[str] = None,
        redis_url: Optional[str] = None,
    ):
        """Initialize strategy storage service."""
        self.database_url = database_url or DATABASE_URL
        self.redis_url = redis_url or REDIS_URL

        # Lazy-initialized connections
        self._db_pool = None
        self._redis_client = None
        self._initialized = False

        # In-memory cache for hot strategies
        self._memory_cache: Dict[str, tuple] = {}  # key -> (strategy, timestamp)
        self._cache_hits = 0
        self._cache_misses = 0

    @classmethod
    async def get_instance(cls) -> "StrategyStorageService":
        """Get or create singleton instance with async initialization."""
        if cls._instance is None:
            if cls._lock is None:
                cls._lock = asyncio.Lock()
            async with cls._lock:
                if cls._instance is None:
                    instance = cls()
                    await instance.initialize()
                    cls._instance = instance
        return cls._instance

    async def initialize(self) -> None:
        """Initialize database pool and ensure tables exist."""
        if self._initialized:
            return

        try:
            import asyncpg

            # asyncpg only accepts postgresql:// or postgres:// schemes — strip +asyncpg suffix
            dsn = self.database_url.replace("+asyncpg", "")
            self._db_pool = await asyncpg.create_pool(
                dsn,
                min_size=2,
                max_size=10,
            )
            await self._ensure_tables()
            self._initialized = True
            logger.info("Strategy storage database initialized")
        except ImportError:
            logger.warning("asyncpg not installed, database operations will fail")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    async def _ensure_tables(self) -> None:
        """Ensure the strategies table exists with proper indexes."""
        if self._db_pool is None:
            return

        create_table_sql = """
            CREATE TABLE IF NOT EXISTS strategies (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                key TEXT UNIQUE NOT NULL,
                game_type TEXT NOT NULL DEFAULT 'nlh',
                players INTEGER NOT NULL DEFAULT 2,
                street TEXT NOT NULL DEFAULT 'preflop',
                board_hash TEXT NOT NULL DEFAULT '',
                bet_size REAL NOT NULL DEFAULT 0,
                stack_depth INTEGER NOT NULL,
                strategy_data JSONB NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            
            -- Index for key lookups
            CREATE INDEX IF NOT EXISTS idx_strategies_key ON strategies(key);
            
            -- Composite index for board-based lookups (most common query pattern)
            CREATE INDEX IF NOT EXISTS idx_strategies_board_lookup ON strategies(
                game_type, players, street, board_hash
            );
            
            -- Index for street-based lookups
            CREATE INDEX IF NOT EXISTS idx_strategies_street ON strategies(
                game_type, players, street, stack_depth
            );
            
            -- Index for flop strategy lookups by board
            CREATE INDEX IF NOT EXISTS idx_strategies_flop ON strategies(
                game_type, players, street, board_hash, bet_size, stack_depth
            ) WHERE street IN ('flop', 'turn', 'river');
        """

        try:
            async with self._db_pool.acquire() as conn:
                await conn.execute(create_table_sql)
            logger.info("Strategy storage tables and indexes created")
        except Exception as e:
            logger.warning(f"Could not create strategies table: {e}")

    def _get_redis_client(self):
        """Get or create Redis client."""
        if self._redis_client is None:
            try:
                import redis.asyncio as aioredis

                self._redis_client = aioredis.from_url(
                    self.redis_url,
                    decode_responses=True,
                )
            except ImportError:
                logger.warning("Redis not installed")
                return None
        return self._redis_client

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

        Format: nlh:2:{street}:{board_hash}:{bet_size}:{stack_depth}

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
        Parse a strategy key into its components.

        Args:
            key: Strategy key like "nlh:2:river:Kd7h2c:0.5:100"

        Returns:
            Dict with game_type, players, street, board_hash, bet_size, stack_depth
        """
        parts = key.split(":")
        if len(parts) != 6:
            raise ValueError(
                f"Invalid strategy key format: {key}. Expected 6 parts separated by ':'"
            )

        return {
            "game_type": parts[0],
            "players": int(parts[1]),
            "street": parts[2],
            "board_hash": parts[3],
            "bet_size": float(parts[4]) if parts[4] else 0.0,
            "stack_depth": int(parts[5]),
        }

    @staticmethod
    def hash_board(board: str) -> str:
        """
        Create a consistent hash for a board.

        Args:
            board: Board cards like "Kd7h2c" or "AsTcKh"

        Returns:
            Normalized board hash
        """
        if not board:
            return ""
        # Normalize: sort cards and remove spaces
        cards = board.replace(" ", "").lower()
        sorted_cards = "".join(sorted(cards))
        return hashlib.md5(sorted_cards.encode()).hexdigest()[:6]

    def _get_from_memory_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """Get strategy from in-memory cache if not expired."""
        import time

        if key in self._memory_cache:
            strategy, timestamp = self._memory_cache[key]
            if time.time() - timestamp < STRATEGY_CACHE_TTL:
                self._cache_hits += 1
                return strategy
            else:
                del self._memory_cache[key]
        return None

    def _set_in_memory_cache(self, key: str, strategy_data: Dict[str, Any]):
        """Set strategy in memory cache with current timestamp."""
        import time

        # Bound cache size
        if len(self._memory_cache) > 1000:
            # Remove oldest 100 entries
            oldest = sorted(self._memory_cache.items(), key=lambda x: x[1][1])[:100]
            for k, _ in oldest:
                del self._memory_cache[k]

        self._memory_cache[key] = (strategy_data, time.time())

    async def _get_from_redis_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """Get strategy from Redis cache if available."""
        redis = self._get_redis_client()
        if redis is None:
            return None

        try:
            cache_key = f"{REDIS_CACHE_PREFIX}{key}"
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Redis cache get failed for {key}: {e}")

        return None

    async def _set_in_redis_cache(self, key: str, strategy_data: Dict[str, Any]):
        """Set strategy in Redis cache with TTL."""
        redis = self._get_redis_client()
        if redis is None:
            return

        try:
            cache_key = f"{REDIS_CACHE_PREFIX}{key}"
            await redis.setex(cache_key, STRATEGY_CACHE_TTL, json.dumps(strategy_data))
        except Exception as e:
            logger.warning(f"Redis cache set failed for {key}: {e}")

    async def store_strategy(
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
        Store a solved strategy to PostgreSQL.

        Args:
            street: Street name (preflop, flop, turn, river)
            strategy_data: Strategy data dict with actions and frequencies
            board_hash: Board cards hash (e.g., "Kd7h2c" or "" for preflop)
            bet_size: Bet size as fraction of pot
            stack_depth: Stack depth in big blinds
            game_type: Game type (nlh, plo)
            players: Number of players

        Returns:
            StoredStrategy object
        """
        key = self.make_strategy_key(street, board_hash, bet_size, stack_depth, game_type, players)

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

        # Try to save to PostgreSQL
        db_saved = False
        if self._db_pool:
            try:
                async with self._db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO strategies 
                            (key, game_type, players, street, board_hash, bet_size,
                             stack_depth, strategy_data, created_at, updated_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                        ON CONFLICT (key) DO UPDATE SET
                            strategy_data = EXCLUDED.strategy_data,
                            updated_at = EXCLUDED.updated_at
                    """,
                        key,
                        game_type,
                        players,
                        street,
                        board_hash,
                        bet_size,
                        stack_depth,
                        json.dumps(strategy_data),
                        now,
                        now,
                    )
                    db_saved = True
            except Exception as e:
                logger.warning(f"Could not save to database for {key}: {e}")

        # Update caches — store full metadata so get_strategy can reconstruct StoredStrategy
        cache_data = {
            "game_type": game_type,
            "players": players,
            "street": street,
            "board_hash": board_hash,
            "bet_size": bet_size,
            "stack_depth": stack_depth,
            "strategy_data": strategy_data,
            "created_at": now.isoformat() if isinstance(now, datetime) else None,
            "updated_at": now.isoformat() if isinstance(now, datetime) else None,
        }
        self._set_in_memory_cache(key, cache_data)
        await self._set_in_redis_cache(key, cache_data)

        logger.info(f"Stored strategy: {key}")
        return strategy

    async def get_strategy(self, key: str) -> Optional[StoredStrategy]:
        """
        Get a strategy by key.

        Checks memory cache -> Redis cache -> PostgreSQL.

        Args:
            key: Strategy key (e.g., "nlh:2:river:Kd7h2c:0.5:100")

        Returns:
            StoredStrategy or None if not found
        """
        # Check memory cache first
        cached = self._get_from_memory_cache(key)
        if cached is not None:
            logger.debug(f"Memory cache hit for {key}")
            return StoredStrategy(key=key, **cached)

        # Check Redis cache
        cached = await self._get_from_redis_cache(key)
        if cached is not None:
            logger.debug(f"Redis cache hit for {key}")
            return StoredStrategy(key=key, **cached)

        self._cache_misses += 1

        # Query PostgreSQL
        if self._db_pool:
            try:
                async with self._db_pool.acquire() as conn:
                    row = await conn.fetchrow(
                        """
                        SELECT key, game_type, players, street, board_hash, bet_size,
                               stack_depth, strategy_data, created_at, updated_at
                        FROM strategies
                        WHERE key = $1
                        """,
                        key,
                    )

                    if row:
                        # asyncpg returns JSONB as str in some configurations,
                        # parse it to dict for StoredStrategy compatibility
                        raw_strategy_data = row["strategy_data"]
                        if isinstance(raw_strategy_data, str):
                            try:
                                raw_strategy_data = json.loads(raw_strategy_data)
                            except (json.JSONDecodeError, TypeError):
                                logger.warning(f"Could not parse strategy_data JSON for {key}")

                        strategy = StoredStrategy(
                            key=row["key"],
                            game_type=row["game_type"],
                            players=row["players"],
                            street=row["street"],
                            board_hash=row["board_hash"],
                            bet_size=row["bet_size"],
                            stack_depth=row["stack_depth"],
                            strategy_data=raw_strategy_data,
                            created_at=row["created_at"],
                            updated_at=row["updated_at"],
                        )

                        # Populate caches
                        cache_data = {
                            "game_type": strategy.game_type,
                            "players": strategy.players,
                            "street": strategy.street,
                            "board_hash": strategy.board_hash,
                            "bet_size": strategy.bet_size,
                            "stack_depth": strategy.stack_depth,
                            "strategy_data": strategy.strategy_data,
                            "created_at": strategy.created_at.isoformat()
                            if strategy.created_at
                            else None,
                            "updated_at": strategy.updated_at.isoformat()
                            if strategy.updated_at
                            else None,
                        }
                        self._set_in_memory_cache(key, cache_data)
                        await self._set_in_redis_cache(key, cache_data)

                        return strategy
            except Exception as e:
                logger.error(f"Database query failed for {key}: {e}")

        return None

    async def get_strategy_by_params(
        self,
        street: str,
        board_hash: str = "",
        bet_size: float = 0.0,
        stack_depth: int = 100,
        game_type: str = "nlh",
        players: int = 2,
    ) -> Optional[StoredStrategy]:
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
            StoredStrategy or None if not found
        """
        key = self.make_strategy_key(street, board_hash, bet_size, stack_depth, game_type, players)
        return await self.get_strategy(key)

    async def list_strategies(
        self,
        filters: Optional[StrategyFilters] = None,
    ) -> List[Dict[str, Any]]:
        """
        List strategies with optional filters.

        Args:
            filters: Optional filters for game_type, players, street, board_hash

        Returns:
            List of strategy metadata dicts
        """
        if filters is None:
            filters = StrategyFilters()

        if not self._db_pool:
            return []

        conditions = []
        params = []
        param_idx = 1

        if filters.game_type:
            conditions.append(f"game_type = ${param_idx}")
            params.append(filters.game_type)
            param_idx += 1
        if filters.players:
            conditions.append(f"players = ${param_idx}")
            params.append(filters.players)
            param_idx += 1
        if filters.street:
            conditions.append(f"street = ${param_idx}")
            params.append(filters.street)
            param_idx += 1
        if filters.board_hash is not None:
            conditions.append(f"board_hash = ${param_idx}")
            params.append(filters.board_hash)
            param_idx += 1
        if filters.stack_depth:
            conditions.append(f"stack_depth = ${param_idx}")
            params.append(filters.stack_depth)
            param_idx += 1

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        params.extend([filters.limit, filters.offset])

        try:
            async with self._db_pool.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    SELECT key, game_type, players, street, board_hash, bet_size,
                           stack_depth, created_at, updated_at
                    FROM strategies
                    {where_clause}
                    ORDER BY updated_at DESC
                    LIMIT ${param_idx} OFFSET ${param_idx + 1}
                """,
                    *params,
                )

                return [
                    {
                        "key": row["key"],
                        "game_type": row["game_type"],
                        "players": row["players"],
                        "street": row["street"],
                        "board_hash": row["board_hash"],
                        "bet_size": row["bet_size"],
                        "stack_depth": row["stack_depth"],
                        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Database list failed: {e}")
            return []

    async def list_flop_strategies(
        self,
        game_type: str = "nlh",
        players: int = 2,
        stack_depth: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List flop strategies with optional stack depth filter.

        Args:
            game_type: Game type
            players: Number of players
            stack_depth: Optional stack depth filter
            limit: Maximum results

        Returns:
            List of flop strategy metadata
        """
        if not self._db_pool:
            return []

        conditions = ["game_type = $1", "players = $2", "street = $3"]
        params = [game_type, players, "flop"]
        param_idx = 4

        if stack_depth:
            conditions.append(f"stack_depth = ${param_idx}")
            params.append(stack_depth)
            param_idx += 1

        params.append(limit)

        try:
            async with self._db_pool.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    SELECT key, game_type, players, street, board_hash, bet_size,
                           stack_depth, created_at, updated_at
                    FROM strategies
                    WHERE {" AND ".join(conditions)}
                    ORDER BY stack_depth, bet_size, board_hash
                    LIMIT ${param_idx}
                """,
                    *params,
                )

                return [
                    {
                        "key": row["key"],
                        "game_type": row["game_type"],
                        "players": row["players"],
                        "street": row["street"],
                        "board_hash": row["board_hash"],
                        "bet_size": row["bet_size"],
                        "stack_depth": row["stack_depth"],
                        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Database list failed: {e}")
            return []

    async def delete_strategy(self, key: str) -> bool:
        """
        Delete a strategy by key.

        Args:
            key: Strategy key

        Returns:
            True if deleted, False if not found
        """
        deleted = False

        if self._db_pool:
            try:
                async with self._db_pool.acquire() as conn:
                    result = await conn.execute("DELETE FROM strategies WHERE key = $1", key)
                    deleted = result == "DELETE 1"
            except Exception as e:
                logger.error(f"Database delete failed for {key}: {e}")

        # Remove from caches
        if key in self._memory_cache:
            del self._memory_cache[key]

        redis = self._get_redis_client()
        if redis:
            try:
                cache_key = f"{REDIS_CACHE_PREFIX}{key}"
                await redis.delete(cache_key)
            except Exception as e:
                logger.warning(f"Redis cache delete failed for {key}: {e}")

        if deleted:
            logger.info(f"Deleted strategy: {key}")

        return deleted

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total if total > 0 else 0

        return {
            "memory_cache_size": len(self._memory_cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": hit_rate,
        }

    async def clear_cache(self):
        """Clear all caches."""
        self._memory_cache.clear()

        redis = self._get_redis_client()
        if redis:
            try:
                # Delete all strategy cache keys
                cursor = 0
                while True:
                    cursor, keys = await redis.scan(
                        cursor, match=f"{REDIS_CACHE_PREFIX}*", count=100
                    )
                    if keys:
                        await redis.delete(*keys)
                    if cursor == 0:
                        break
                logger.info("Cleared Redis strategy cache")
            except Exception as e:
                logger.warning(f"Failed to clear Redis cache: {e}")

        logger.info("Cleared in-memory strategy cache")

    def to_json(self, strategy: StoredStrategy) -> str:
        """Serialize a StoredStrategy to JSON string."""
        return json.dumps(
            {
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
            }
        )

    def from_json(self, json_str: str) -> StoredStrategy:
        """Deserialize a StoredStrategy from JSON string."""
        data = json.loads(json_str)
        return StoredStrategy(
            key=data["key"],
            game_type=data.get("game_type", "nlh"),
            players=data.get("players", 2),
            street=data.get("street", "preflop"),
            board_hash=data.get("board_hash", ""),
            bet_size=data.get("bet_size", 0.0),
            stack_depth=data["stack_depth"],
            strategy_data=data["strategy_data"],
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(data["updated_at"])
            if data.get("updated_at")
            else datetime.now(timezone.utc),
        )


# Common flop boards for pre-computation
COMMON_FLOP_BOARDS = [
    "AhKh2c",
    "AhKh3c",
    "AhKh4c",
    "AhKh5c",
    "AhKh6c",  # Ace-high kicker
    "AsKs2c",
    "AsKs3c",
    "AsKs4c",
    "AsKs5c",
    "AsKs6c",
    "AdKd2c",
    "AdKd3c",
    "AdKd4c",
    "AdKd5c",
    "AdKd6c",
    "AcKc2c",
    "AcKc3c",
    "AcKc4c",
    "AcKc5c",
    "AcKc6c",
    # Broadway boards
    "AT8r",
    "KQ9r",
    "QJ9r",
    "QT8r",
    "KT9r",
    "AJ8r",
    "AK9r",
    "AQ8r",
    "AQ9r",
    "KJ8r",
    # Mid cards
    "765r",
    "654r",
    "543r",
    "432r",
    "654r",
    "876r",
    "987r",
    "T87r",
    "T97r",
    "J87r",
    # Pairs
    "AA2r",
    "KK2r",
    "QQ2r",
    "JJ2r",
    "TT2r",
    "AAKr",
    "KKQr",
    "QQJr",
    "JJTr",
    "TT9r",
    # Monotone
    "AhKhQh",
    "AsKsQs",
    "AdKdQd",
    "AcKcQc",
    "2h3h4h",
    "2s3s4s",
    "2d3d4d",
    "2c3c4c",
]

# Common bet sizes for flop strategies
COMMON_BET_SIZES = [0.33, 0.5, 0.67, 0.75, 1.0]

# Common stack depths
COMMON_STACK_DEPTHS = [50, 75, 100, 125, 150, 200]


async def precompute_common_flop_strategies(
    storage: Optional[StrategyStorageService] = None,
) -> Dict[str, Any]:
    """
    Background task to pre-compute common flop strategies.

    Args:
        storage: Optional StrategyStorageService instance

    Returns:
        Dict with results of pre-computation
    """
    if storage is None:
        storage = await StrategyStorageService.get_instance()

    results = {
        "total": len(COMMON_FLOP_BOARDS) * len(COMMON_BET_SIZES) * len(COMMON_STACK_DEPTHS),
        "computed": 0,
        "failed": 0,
        "skipped": 0,
    }

    # This would integrate with the solver to generate strategies
    # For now, just log what would be computed
    for board in COMMON_FLOP_BOARDS[:10]:  # Limit for safety
        for bet_size in COMMON_BET_SIZES[:3]:
            for stack_depth in COMMON_STACK_DEPTHS[:2]:
                key = storage.make_strategy_key(
                    street="flop",
                    board_hash=board,
                    bet_size=bet_size,
                    stack_depth=stack_depth,
                )

                # Check if already exists
                existing = await storage.get_strategy(key)
                if existing:
                    results["skipped"] += 1
                    continue

                # In a real implementation, this would call the solver
                # For now, just log
                logger.info(f"Would pre-compute: {key}")
                results["computed"] += 1

    logger.info(f"Pre-computation complete: {results}")
    return results


# Global storage instance
_strategy_storage: Optional[StrategyStorageService] = None


async def get_strategy_storage() -> StrategyStorageService:
    """Get or create global strategy storage instance."""
    global _strategy_storage
    if _strategy_storage is None:
        _strategy_storage = await StrategyStorageService.get_instance()
    return _strategy_storage
