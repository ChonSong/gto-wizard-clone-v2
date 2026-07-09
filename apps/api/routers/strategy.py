"""
Strategy storage API router.

Provides endpoints for:
- Storing GTO strategies in Redis
- Retrieving strategies by key
- Looking up strategies by parameters

Key format: nlh:2:{board}:{stack}:{bets}
Example: nlh:2:preflop:100:
"""

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from apps.api.services.redis_service import RedisService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/strategy", tags=["strategy"])


class StrategyAction(BaseModel):
    """Single action in a strategy."""
    hand: str
    action: str
    frequency: float = 1.0
    ev: float = 0.0


class StrategyStoreRequest(BaseModel):
    """Request model for storing a strategy."""
    game_type: str = "nlh"
    players: int = 2
    board: str = "preflop"
    stack_depth: int
    bet_sizes: List[float] = []
    strategy_data: List[Dict[str, Any]]
    pot_size: int = 100


class StrategyResponse(BaseModel):
    """Response model for strategy retrieval."""
    key: str
    game_type: str
    players: int
    board: str
    stack_depth: int
    bet_sizes: List[float]
    pot_size: int
    strategy_data: List[Dict[str, Any]]
    status: str = "found"


class StrategyKeyResponse(BaseModel):
    """Response model for key generation."""
    key: str
    message: str


class LookupQuery(BaseModel):
    """Query parameters for strategy lookup."""
    game_type: str = Query("nlh", description="Game type (nlh, plo)")
    players: int = Query(2, description="Number of players")
    board: str = Query("preflop", description="Board cards or 'preflop'")
    stack_depth: int = Query(100, description="Stack depth in big blinds")
    bet_sizes: List[float] = Query([], description="Bet sizes")


def make_strategy_key(
    game_type: str,
    players: int,
    board: str,
    bet_sizes: List[float],
    stack_depth: int,
) -> str:
    """Generate a strategy key.
    
    Format: {game_type}:{players}:{board}:{bet_sizes}:{stack_depth}
    Example: nlh:2:preflop:[]:100
    """
    bet_sizes_str = ",".join(map(str, sorted(bet_sizes))) if bet_sizes else ""
    return f"{game_type}:{players}:{board}:{bet_sizes_str}:{stack_depth}"


def parse_strategy_key(key: str) -> Dict[str, Any]:
    """Parse a strategy key into its components.
    
    Key format: {game_type}:{players}:{board}:{bet_sizes}:{stack_depth}
    Example: nlh:2:preflop::100
    Example with board: nlh:2:Kd:7h:2c::100
    Example with bet sizes: nlh:2:preflop:30,70:100
    
    Board may contain colons (e.g., 'Kd:7h:2c'), so we parse from the ends.
    """
    parts = key.split(":")
    if len(parts) < 5:
        raise ValueError(f"Invalid strategy key format: {key}")
    
    game_type = parts[0]
    players = int(parts[1])
    
    # Work from the end: stack_depth is last, bet_sizes_str is second-to-last
    # Everything in between is the board (which may contain colons)
    bet_sizes_str = parts[-2]
    stack_depth = int(parts[-1])
    
    # Board is everything from index 2 to -2
    board_parts = parts[2:-2]
    board = ":".join(board_parts)
    
    bet_sizes = []
    if bet_sizes_str:
        bet_sizes = [float(x) for x in bet_sizes_str.split(",") if x]
    
    return {
        "game_type": game_type,
        "players": players,
        "board": board,
        "stack_depth": stack_depth,
        "bet_sizes": bet_sizes,
    }


@router.post("", response_model=StrategyKeyResponse)
async def store_strategy(request: StrategyStoreRequest):
    """
    Store a GTO strategy in Redis.
    
    The strategy key format: {game_type}:{players}:{board}:{stack_depth}:{bet_sizes}
    Example: nlh:2:preflop:100:
    
    Returns the generated key for the stored strategy.
    """
    redis_service = RedisService.get_instance()
    
    # Generate strategy key
    key = make_strategy_key(
        request.game_type,
        request.players,
        request.board,
        request.bet_sizes,
        request.stack_depth,
    )
    
    # Prepare strategy data for storage
    strategy_record = {
        "key": key,
        "game_type": request.game_type,
        "players": request.players,
        "board": request.board,
        "stack_depth": request.stack_depth,
        "bet_sizes": request.bet_sizes,
        "pot_size": request.pot_size,
        "strategy_data": request.strategy_data,
    }
    
    try:
        # Store in Redis with 7 day TTL
        redis_service.client.set(
            f"strategy:{key}",
            json.dumps(strategy_record),
            ex=604800,  # 7 days
        )
        
        # Also add to index for lookup queries
        index_key = f"strategy:index:{request.game_type}:{request.players}:{request.board}"
        redis_service.client.zadd(index_key, {key: request.stack_depth})
        
        logger.info(f"Stored strategy: {key} with {len(request.strategy_data)} actions")
        
        return StrategyKeyResponse(
            key=key,
            message=f"Strategy stored successfully with {len(request.strategy_data)} actions",
        )
        
    except Exception as e:
        logger.error(f"Failed to store strategy {key}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to store strategy: {str(e)}")


@router.get("/lookup", response_model=StrategyResponse)
async def lookup_strategy(
    game_type: str = Query("nlh", description="Game type (nlh, plo)"),
    players: int = Query(2, description="Number of players"),
    board: str = Query("preflop", description="Board cards or 'preflop'"),
    stack_depth: int = Query(100, description="Stack depth in big blinds"),
    bet_sizes: str = Query("", description="Comma-separated bet sizes"),
):
    """
    Look up a strategy by its parameters.
    
    Query parameters:
    - game_type: Game type (nlh, plo)
    - players: Number of players
    - board: Board cards or 'preflop'
    - stack_depth: Stack depth in big blinds
    - bet_sizes: Comma-separated bet sizes (optional)
    """
    redis_service = RedisService.get_instance()
    
    # Parse bet sizes
    bet_sizes_list = []
    if bet_sizes:
        try:
            bet_sizes_list = [float(x.strip()) for x in bet_sizes.split(",")]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid bet_sizes format")
    
    # Build strategy key
    key = make_strategy_key(game_type, players, board, bet_sizes_list, stack_depth)
    
    try:
        data = redis_service.client.get(f"strategy:{key}")
        
        if not data:
            # Try to find closest match in index
            index_key = f"strategy:index:{game_type}:{players}:{board}"
            candidates = redis_service.client.zrangebyscore(
                index_key, stack_depth, stack_depth
            )
            
            if candidates:
                # Try first candidate
                key = candidates[0].decode() if isinstance(candidates[0], bytes) else candidates[0]
                data = redis_service.client.get(f"strategy:{key}")
            
            if not data:
                raise HTTPException(
                    status_code=404,
                    detail=f"Strategy not found for: game={game_type}, board={board}, stack={stack_depth}"
                )
        
        strategy = json.loads(data)
        
        return StrategyResponse(
            key=strategy["key"],
            game_type=strategy["game_type"],
            players=strategy["players"],
            board=strategy["board"],
            stack_depth=strategy["stack_depth"],
            bet_sizes=strategy["bet_sizes"],
            pot_size=strategy["pot_size"],
            strategy_data=strategy["strategy_data"],
            status="found",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to lookup strategy: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to lookup strategy: {str(e)}")


@router.get("/{key}", response_model=StrategyResponse)
async def get_strategy(key: str):
    """
    Retrieve a stored strategy by key.
    
    Key format: nlh:2:{board}:{stack_depth}:{bet_sizes}
    Example: nlh:2:preflop:100:
    """
    redis_service = RedisService.get_instance()
    
    try:
        # Parse key to validate format
        parse_strategy_key(key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        data = redis_service.client.get(f"strategy:{key}")
        
        if not data:
            raise HTTPException(status_code=404, detail=f"Strategy not found: {key}")
        
        strategy = json.loads(data)
        
        return StrategyResponse(
            key=strategy["key"],
            game_type=strategy["game_type"],
            players=strategy["players"],
            board=strategy["board"],
            stack_depth=strategy["stack_depth"],
            bet_sizes=strategy["bet_sizes"],
            pot_size=strategy["pot_size"],
            strategy_data=strategy["strategy_data"],
            status="found",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve strategy {key}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve strategy: {str(e)}")


@router.delete("/{key}")
async def delete_strategy(key: str):
    """Delete a stored strategy by key."""
    redis_service = RedisService.get_instance()
    
    try:
        parse_strategy_key(key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        data = redis_service.client.get(f"strategy:{key}")
        if not data:
            raise HTTPException(status_code=404, detail=f"Strategy not found: {key}")
        
        strategy = json.loads(data)
        
        # Delete strategy
        redis_service.client.delete(f"strategy:{key}")
        
        # Remove from index
        index_key = f"strategy:index:{strategy['game_type']}:{strategy['players']}:{strategy['board']}"
        redis_service.client.zrem(index_key, key)
        
        return {"status": "deleted", "key": key}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete strategy {key}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete strategy: {str(e)}")


@router.get("")
async def list_strategies(
    game_type: str = Query("nlh", description="Game type"),
    players: int = Query(2, description="Number of players"),
    board: str = Query("preflop", description="Board cards or 'preflop'"),
    limit: int = Query(10, description="Max results to return"),
):
    """List available strategies for given parameters."""
    redis_service = RedisService.get_instance()
    
    index_key = f"strategy:index:{game_type}:{players}:{board}"
    
    try:
        # Get strategies sorted by stack depth
        keys = redis_service.client.zrevrange(index_key, 0, limit - 1)
        
        strategies = []
        for k in keys:
            key = k.decode() if isinstance(k, bytes) else k
            data = redis_service.client.get(f"strategy:{key}")
            if data:
                strategies.append(json.loads(data))
        
        return {
            "game_type": game_type,
            "players": players,
            "board": board,
            "count": len(strategies),
            "strategies": strategies,
        }
        
    except Exception as e:
        logger.error(f"Failed to list strategies: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list strategies: {str(e)}")
