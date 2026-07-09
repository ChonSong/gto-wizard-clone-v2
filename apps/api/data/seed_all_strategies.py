#!/usr/bin/env python3
"""
Combined seed script: seeds both preflop and flop GTO strategies into PostgreSQL.

Runs seed_preflop_strategies.py and seed_flop_strategies.py in sequence.
Idempotent — safe to run multiple times.

Usage:
    python seed_all_strategies.py

Requires: asyncpg, access to the gto_wizard postgres database.
"""

import asyncio
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/gto_wizard",
)


async def run():
    # Import here so the script can be copied standalone if needed
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    # ── Seed preflop ──
    try:
        from seed_preflop_strategies import seed_strategies as seed_preflop

        for sd in [50, 100, 150, 200]:
            count = await seed_preflop(DATABASE_URL, stack_depth=sd)
            logger.info(f"Seeded {count} preflop strategies at {sd}bb")
    except Exception as e:
        logger.error(f"Prefop seed failed: {e}")
        raise

    # ── Seed flop ──
    try:
        from seed_flop_strategies import seed_flop_strategies

        for sd in [50, 100, 150, 200]:
            count = await seed_flop_strategies(DATABASE_URL, stack_depth=sd)
            logger.info(f"Seeded {count} flop strategies at {sd}bb")
    except Exception as e:
        logger.error(f"Flop seed failed: {e}")
        raise

    logger.info("All strategies seeded successfully.")


if __name__ == "__main__":
    asyncio.run(run())
