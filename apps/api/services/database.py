"""
Async database session management.
Falls back to SQLite if PostgreSQL is not available.
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)

# Try PostgreSQL first, fall back to SQLite
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    _sqlite_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "gto_wizard.db")
    DATABASE_URL = f"sqlite+aiosqlite:///{os.path.abspath(_sqlite_path)}"
    logger.info(f"No DATABASE_URL set, using SQLite: {_sqlite_path}")


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        kwargs = {"echo": False}
        if "sqlite" not in DATABASE_URL:
            kwargs["pool_size"] = 5
            kwargs["max_overflow"] = 10
            kwargs["pool_pre_ping"] = True
        _engine = create_async_engine(DATABASE_URL, **kwargs)
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Initialize database tables."""
    logger.info("Initializing database tables...")
    engine = get_engine()

    # Import all models so their metadata gets registered
    from apps.api.models.spots import CommunitySpot, SpotComment, SpotLike
    from apps.api.models.course_models import Course, Lesson, UserProgress
    from apps.api.models.hh_models import HandHistory, HandTag, HandAction
    from apps.api.models.study_progress import StudyProgress
    from apps.api.services.quiz_models import QuizSpot, QuizSubmission, UserStats, ReviewSpot

    # Import models from services/models.py as well
    from apps.api.services.models import Strategy, Base as ModelsBase

    try:
        async with engine.begin() as conn:
            # Create tables from both base classes since models inherit from different ones
            await conn.run_sync(ModelsBase.metadata.create_all)
            from apps.api.services.database import Base as DbBase

            await conn.run_sync(DbBase.metadata.create_all)
        logger.info("Database tables initialized")
    except Exception as e:
        error_str = str(e)
        if "JSONB" in error_str or "can't render element" in error_str:
            logger.warning(
                "JSONB columns not supported in SQLite. Trying incremental table creation..."
            )
            logger.warning(
                "JSONB columns not supported in SQLite. Trying incremental table creation..."
            )
            # Get all registered tables
            from sqlalchemy import Table, MetaData

            tables_to_create = list(Base.metadata.tables.values())
            created_count = 0
            failed_tables = []

            for table in tables_to_create:
                try:
                    async with engine.begin() as conn:
                        await conn.run_sync(table.create, checkfirst=True)
                    created_count += 1
                except Exception as table_err:
                    failed_tables.append(table.name)
                    logger.warning(f"Could not create table '{table.name}': {table_err}")

            if created_count > 0:
                logger.info(f"Created {created_count} tables. Failed: {failed_tables}")
            else:
                logger.warning(f"No tables could be created. All failed: {failed_tables}")
        else:
            logger.error(f"Database initialization failed: {e}")
            raise


async def close_db():
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
