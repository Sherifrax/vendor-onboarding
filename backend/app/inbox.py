"""Manual and Gmail-shaped inbox sources for the intake service."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol

from app.schemas import IncomingEmail


class InboxSource(Protocol):
    """A source that yields every currently available incoming email."""

    async def fetch(self) -> list[IncomingEmail]:
        """Return the complete available batch, not only the first message."""


class ManualSource:
    """Primary demo source; one API submission becomes one inbox item."""

    def __init__(self, emails: Sequence[IncomingEmail]) -> None:
        self.emails = list(emails)

    async def fetch(self) -> list[IncomingEmail]:
        return list(self.emails)


class GmailClient(Protocol):
    """Minimal adapter surface for a Gmail API client configured elsewhere."""

    async def list_unread(self, label: str) -> list[IncomingEmail]:
        """Return all unread messages for the supplied label."""


class GmailSource:
    """Gmail label source that deliberately returns every unread message in a poll."""

    def __init__(self, client: GmailClient, label: str = "vendor-requests") -> None:
        self.client = client
        self.label = label

    async def fetch(self) -> list[IncomingEmail]:
        return await self.client.list_unread(self.label)

    async def poll_once(
        self, processor: Callable[[IncomingEmail], Awaitable[object]]
    ) -> list[object]:
        """Process every unread email currently carrying the configured label."""

        return await process_all(self, processor)

    async def poll_forever(
        self,
        processor: Callable[[IncomingEmail], Awaitable[object]],
        interval_seconds: int = 60,
    ) -> None:
        """Poll Gmail once per minute when enabled by the inbox runtime configuration."""

        while True:
            await self.poll_once(processor)
            await asyncio.sleep(interval_seconds)


async def process_all(
    source: InboxSource, processor: Callable[[IncomingEmail], Awaitable[object]]
) -> list[object]:
    """Process all messages in a poll; never silently stop after one item."""

    return [await processor(email) for email in await source.fetch()]
