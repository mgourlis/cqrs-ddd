"""InMemorySnapshotStore — in-memory snapshot store for tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from cqrs_ddd_advanced_core.ports.snapshots import ISnapshotStore

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.specification import ISpecification


class InMemorySnapshotStore(ISnapshotStore):
    """In-memory implementation of ISnapshotStore for unit tests.

    Keeps only the latest snapshot per (aggregate_type, aggregate_id).
    """

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], dict[str, Any]] = {}

    async def save_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: Any,
        snapshot_data: dict[str, Any],
        version: int,
        *,
        specification: ISpecification[Any] | None = None,  # noqa: ARG002
    ) -> None:
        key = (aggregate_type, str(aggregate_id))
        self._store[key] = {
            "snapshot_data": snapshot_data,
            "version": version,
            "created_at": datetime.now(timezone.utc),
        }

    async def get_latest_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: Any,
        *,
        specification: ISpecification[Any] | None = None,  # noqa: ARG002
    ) -> dict[str, Any] | None:
        key = (aggregate_type, str(aggregate_id))
        return self._store.get(key)

    async def delete_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: Any,
        *,
        specification: ISpecification[Any] | None = None,  # noqa: ARG002
    ) -> None:
        key = (aggregate_type, str(aggregate_id))
        self._store.pop(key, None)

    def clear(self) -> None:
        """Remove all snapshots (test helper)."""
        self._store.clear()
