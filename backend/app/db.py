"""Database connectivity helpers."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Base class for all persistent domain models."""


engine = create_async_engine(get_settings().database_url)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def check_database() -> None:
    """Raise when PostgreSQL cannot execute a minimal query."""

    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
