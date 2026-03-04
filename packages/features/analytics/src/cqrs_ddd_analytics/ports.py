"""Port definitions (protocols) for the analytics package."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.events import DomainEvent

    from .schema import AnalyticsSchema


@runtime_checkable
class IRowMapper(Protocol):
    """Protocol for mapping domain events to tabular row dicts.

    Returns ``None`` to indicate the event should be skipped.
    A single event may produce multiple rows by returning a list.
    """

    def map(
        self, event: DomainEvent
    ) -> dict[str, object] | list[dict[str, object]] | None:
        """Map a domain event to one or more row dicts, or None to skip."""
        ...


@runtime_checkable
class IAnalyticsSink(Protocol):
    """Protocol for analytics data sinks (e.g. Parquet files, in-memory store).

    Sinks receive batches of pre-mapped rows and persist them.
    """

    async def push_batch(self, table: str, rows: list[dict[str, object]]) -> int:
        """Push a batch of rows to the sink.

        Args:
            table: Target table/dataset name.
            rows: List of row dicts to persist.

        Returns:
            Number of rows successfully written.
        """
        ...

    async def initialize_dataset(self, schema: AnalyticsSchema) -> None:
        """Ensure the target dataset exists and is configured.

        Implementations should create directories, validate schemas, etc.
        """
        ...
