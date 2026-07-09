#!/usr/bin/env python3
"""
Seed preflop GTO strategies into the PostgreSQL strategies table.

Generates equity-based preflop ranges for 6 positions (UTG, HJ, CO, BTN, SB, BB)
at 100bb stack depth and stores them in the strategy-lookup PostgreSQL table.

Idempotent — safe to run multiple times (upserts on conflict key).

Usage:
    python seed_preflop_strategies.py

Requires: asyncpg, access to the gto_wizard postgres database.
"""

import asyncio
import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Database configuration ──
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:***@localhost:5432/gto_wizard",
).replace(":***@", ":postgres@")

# ── Preflop equities loaded from the API data directory ──
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_EQUITY_PATH = os.path.join(_DATA_DIR, "preflop_equities.json")

# Standard GTO RFI (raise-first-in) range widths by position at 100bb
# Based on solver-generated ranges from modern GTO sources
_PREFLOP_RANGES = {
    "UTG":  {"width": 0.155, "raise_actions": ["raise_2.5bb"], "call_actions": []},
    "HJ":   {"width": 0.21,  "raise_actions": ["raise_2.5bb"], "call_actions": []},
    "CO":   {"width": 0.28,  "raise_actions": ["raise_2.5bb"], "call_actions": []},
    "BTN":  {"width": 0.42,  "raise_actions": ["raise_2.5bb"], "call_actions": []},
    "SB":   {"width": 0.45,  "raise_actions": ["raise_3bb"],   "call_actions": []},
    "BB":   {"width": 0.0,   "raise_actions": [],              "call_actions": ["call"]},
}

_POSITIONS = ["UTG", "HJ", "CO", "BTN", "SB", "BB"]

RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]


def load_equities() -> dict:
    """Load precomputed preflop equities."""
    if os.path.exists(_EQUITY_PATH):
        with open(_EQUITY_PATH) as f:
            return json.load(f)
    logger.warning(f"Equity file not found at {_EQUITY_PATH}, using defaults")
    return {}


def load_or_generate_equities() -> dict:
    """Load equities, generating defaults for any missing hands."""
    equities = load_equities()
    hands_169 = []
    for i, r1 in enumerate(RANKS):
        for j, r2 in enumerate(RANKS):
            if i <= j:
                if r1 == r2:
                    hands_169.append(f"{r1}{r2}")
                else:
                    hands_169.append(f"{r1}{r2}s")
                    hands_169.append(f"{r1}{r2}o")
    for hand in hands_169:
        if hand not in equities:
            equities[hand] = 0.5
    return equities


def generate_hands_169() -> list:
    """Generate all 169 hand combinations in display order."""
    hands = []
    for i, r1 in enumerate(RANKS):
        for j, r2 in enumerate(RANKS):
            if i <= j:
                if r1 == r2:
                    hands.append(f"{r1}{r2}")
                else:
                    hands.append(f"{r1}{r2}s")
                    hands.append(f"{r1}{r2}o")
    return hands


def generate_position_range(position: str, stack_depth: int, equities: dict) -> list:
    """
    Generate preflop range data for a position using the equity-based model.

    Matches the logic in solver.py's _generate_range().
    Returns list of dicts with hand, action, frequency, ev.
    """
    hands_169 = generate_hands_169()
    config = _PREFLOP_RANGES.get(position, _PREFLOP_RANGES["UTG"])

    # Sort hands by equity descending
    hand_equities = [(hand, equities.get(hand, 0.5)) for hand in hands_169]
    hand_equities.sort(key=lambda x: -x[1])

    total = len(hand_equities)  # 169
    raise_count = int(total * config["width"])
    call_count = 0  # Preflop RFI models don't use calling ranges in this model
    fold_count = total - raise_count - call_count

    action_map = {}
    for i, (hand, eq) in enumerate(hand_equities):
        if i < raise_count:
            position_in_range = i / max(raise_count, 1)
            freq = max(0.5, 1.0 - position_in_range * 0.5)
            action = config["raise_actions"][0] if config["raise_actions"] else "raise"
            action_map[hand] = {
                "hand": hand,
                "action": action,
                "frequency": round(freq, 3),
                "equity": round(eq, 4),
            }
        else:
            action_map[hand] = {
                "hand": hand,
                "action": "fold",
                "frequency": 1.0,
                "equity": round(eq, 4),
            }

    # Return in display order (matrix order)
    return [action_map.get(hand, {"hand": hand, "action": "fold", "frequency": 0.0, "equity": 0.5})
            for hand in hands_169]


def make_strategy_key(street: str, board_hash: str, bet_size: float, stack_depth: int,
                      game_type: str = "nlh", players: int = 2) -> str:
    """Generate strategy key matching StrategyStorageService.make_strategy_key()."""
    return f"{game_type}:{players}:{street}:{board_hash}:{bet_size}:{stack_depth}"


async def seed_strategies(db_url: str, stack_depth: int = 100):
    """Seed preflop strategies for all positions."""
    try:
        import asyncpg
    except ImportError:
        logger.error("asyncpg not installed. Install with: pip install asyncpg")
        sys.exit(1)

    equities = load_or_generate_equities()
    hands_169 = generate_hands_169()

    conn = await asyncpg.connect(db_url)
    try:
        # Ensure strategies table exists
        await conn.execute("""
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
        """)

        total = 0
        for position in _POSITIONS:
            # Use position-encoded key by putting position in a field
            # Since the strategy-lookup key schema doesn't include position natively,
            # we encode it in the board_hash field.
            # This way, lookups by position can pass the position as board_hash.
            key = make_strategy_key(
                street="preflop",
                board_hash=position.lower(),
                bet_size=0.5,
                stack_depth=stack_depth,
            )

            hands = generate_position_range(position, stack_depth, equities)

            # Also include an "actions" format for transform_strategy_for_heatmap compatibility
            strategy_data = {
                "position": position,
                "stack_depth": stack_depth,
                "actions": hands,
                "hands": {h["hand"]: {
                    "action": h["action"],
                    "frequency": h["frequency"],
                    "ev": h["equity"],
                } for h in hands},
            }

            # Upsert: insert or update on key conflict
            # asyncpg requires str for JSONB columns, use json.dumps()
            await conn.execute("""
                INSERT INTO strategies
                    (key, game_type, players, street, board_hash, bet_size,
                     stack_depth, strategy_data)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (key) DO UPDATE SET
                    strategy_data = EXCLUDED.strategy_data,
                    updated_at = NOW()
            """, key, "nlh", 2, "preflop", position.lower(), 0.5, stack_depth,
                json.dumps(strategy_data))

            total += 1
            logger.info(f"  ✓ {position}: {key} ({len(hands)} hands)")

        # Also seed a default preflop entry with board_hash="" for backward compatibility
        # This is the key format the strategy-lookup endpoint generates for preflop
        default_key = make_strategy_key(
            street="preflop",
            board_hash="",
            bet_size=0.5,
            stack_depth=stack_depth,
        )
        default_hands = generate_position_range("UTG", stack_depth, equities)
        default_data = {
            "position": "default",
            "stack_depth": stack_depth,
            "actions": default_hands,
            "hands": {h["hand"]: {
                "action": h["action"],
                "frequency": h["frequency"],
                "ev": h["equity"],
            } for h in default_hands},
        }
        await conn.execute("""
            INSERT INTO strategies
                (key, game_type, players, street, board_hash, bet_size,
                 stack_depth, strategy_data)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (key) DO UPDATE SET
                strategy_data = EXCLUDED.strategy_data,
                updated_at = NOW()
        """, default_key, "nlh", 2, "preflop", "", 0.5, stack_depth,
            json.dumps(default_data))
        total += 1
        logger.info(f"  ✓ default: {default_key} ({len(default_hands)} hands)")

        logger.info(f"\nSeeded {total} preflop strategies at {stack_depth}bb")
        return total

    finally:
        await conn.close()


async def main():
    stack_depth = 100
    if len(sys.argv) > 1:
        try:
            stack_depth = int(sys.argv[1])
        except ValueError:
            print(f"Usage: {sys.argv[0]} [stack_depth]")
            sys.exit(1)

    logger.info(f"Seeding preflop GTO strategies at {stack_depth}bb...")
    logger.info(f"Database: {DATABASE_URL}")

    count = await seed_strategies(DATABASE_URL, stack_depth)

    # Verify
    try:
        import asyncpg
        conn = await asyncpg.connect(DATABASE_URL)
        row = await conn.fetchrow("SELECT count(*) as cnt FROM strategies WHERE street = 'preflop'")
        logger.info(f"Total preflop strategies in DB: {row['cnt']}")
        await conn.close()
    except Exception as e:
        logger.error(f"Verification failed: {e}")

    logger.info("Done! Try: curl 'http://localhost:8000/api/v1/strategy-lookup?board=preflop&stack_depth=100&position=UTG'")


if __name__ == "__main__":
    asyncio.run(main())
