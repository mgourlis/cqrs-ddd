"""InMemoryOutboxStorage — list-backed fake for unit tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from cqrs_ddd_core.ports.outbox import IOutboxStorage, OutboxMessage


class InMemoryOutboxStorage(IOutboxStorage):
    """In-memory implementation of ``IOutboxStorage``.

    Stores outbox messages in a flat list.
    """

    def __init__(self) -> None:
        self._messages: list[OutboxMessage] = []

    async def save_messages(
        self,
        messages: list[OutboxMessage],
        uow: Any | None = None,  # noqa: ARG002
    ) -> None:
        self._messages.extend(messages)

    async def get_pending(
        self,
        limit: int = 100,
        uow: Any | None = None,  # noqa: ARG002
    ) -> list[OutboxMessage]:
        pending = [m for m in self._messages if m.published_at is None]
        pending.sort(key=lambda m: m.created_at)
        return pending[:limit]

    async def mark_published(
        self,
        message_ids: list[str],
        uow: Any | None = None,  # noqa: ARG002
    ) -> None:
        now = datetime.now(timezone.utc)
        for msg in self._messages:
            if msg.message_id in message_ids:
                msg.published_at = now

    async def mark_failed(
        self,
        message_id: str,
        error: str,
        uow: Any | None = None,  # noqa: ARG002
    ) -> None:
        for msg in self._messages:
            if msg.message_id == message_id:
                msg.error = error
                msg.retry_count += 1
                break

    # ── Test helpers ─────────────────────────────────────────────

    def clear(self) -> None:
        self._messages.clear()

    def __len__(self) -> int:
        return len(self._messages)
