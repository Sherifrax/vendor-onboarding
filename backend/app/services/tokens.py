"""Single-use, hashed action tokens."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActionToken


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create(
    session: AsyncSession,
    tracking_id: str,
    purpose: str,
    payload: dict | None = None,
    ttl_hours: int = 168,
) -> str:
    """Create a random token while storing only its SHA-256 digest."""

    raw = secrets.token_urlsafe(32)
    session.add(
        ActionToken(
            token_hash=_hash(raw),
            tracking_id=tracking_id,
            purpose=purpose,
            expires_at=datetime.now(UTC) + timedelta(hours=ttl_hours),
            payload=payload or {},
        )
    )
    await session.flush()
    return raw


async def verify(session: AsyncSession, raw: str, purpose: str) -> ActionToken | None:
    """Return a valid, unconsumed token for its intended purpose, if any."""

    token = await session.get(ActionToken, _hash(raw))
    if (
        token is None
        or token.purpose != purpose
        or token.used_at is not None
        or token.expires_at <= datetime.now(UTC)
    ):
        return None
    return token


async def consume(session: AsyncSession, raw: str, purpose: str) -> ActionToken | None:
    """Atomically mark a valid decision token used in the current transaction."""

    token = await verify(session, raw, purpose)
    if token is None:
        return None
    token.used_at = datetime.now(UTC)
    await session.flush()
    return token
