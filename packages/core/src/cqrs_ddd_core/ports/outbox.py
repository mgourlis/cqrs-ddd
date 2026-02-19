"""IOutboxStorage — transactional outbox protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import uuid4

from ..utils import default_dict_factory

if TYPE_CHECKING:
    from ..ports.unit_of_work import UnitOfWork


@dataclass
class OutboxMessage:
    """A message waiting in the transactional outbox."""

    message_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = ""
    payload: dict[str, object] = field(default_factory=default_dict_factory)
    metadata: dict[str, object] = field(default_factory=default_dict_factory)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    published_at: datetime | None = None
    error: str | None = None
    retry_count: int = 0
    correlation_id: str = field(default="", metadata={"description": "Traces entire request chain"})
    causation_id: str | None = field(default=None, metadata={"description": "Direct parent message ID"})


@runtime_checkable
class IOutboxStorage(Protocol):
    """Protocol for the transactional outbox pattern."""

    async def save_messages(
        self, messages: list[OutboxMessage], uow: UnitOfWork | None = None
    ) -> None:
        """
        Persist outbox messages in the same transaction as aggregate.

        Args:
            messages: Messages to save to outbox
            uow: Optional UnitOfWork for transactional consistency.
                 If None, may use ambient context or create new transaction.
        """
        ...

    async def get_pending(
        self, limit: int = 100, uow: UnitOfWork | None = None
    ) -> list[OutboxMessage]:
        """Retrieve unpublished messages, ordered by creation time."""
        ...

    async def mark_published(
        self, message_ids: list[str], uow: UnitOfWork | None = None
    ) -> None:
        """
        Mark messages as successfully published.

        Args:
            message_ids: IDs of messages to mark as published
            uow: Optional UnitOfWork for transactional consistency
        """
        ...

    async def mark_failed(
        self, message_id: str, error: str, uow: UnitOfWork | None = None
    ) -> None:
        """
        Record a publication failure for retry logic.

        Args:
            message_id: ID of the failed message
            error: Error description
            uow: Optional UnitOfWork for transactional consistency
        """
        ...
