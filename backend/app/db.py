"""Database connectivity helpers."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings


async def check_database() -> None:
    """Raise when PostgreSQL cannot execute a minimal query."""

    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    finally:
        await engine.dispose()
