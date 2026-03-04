"""InMemorySink — test fake for analytics assertions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .ports import IAnalyticsSink

if TYPE_CHECKING:
    from .schema import AnalyticsSchema

logger = logging.getLogger(__name__)


class InMemorySink(IAnalyticsSink):
    """In-memory analytics sink for testing.

    Stores rows in a plain dict keyed by table name.
    Provides ``get_rows()`` for test assertions.
    """

    def __init__(self) -> None:
        self._data: dict[str, list[dict[str, object]]] = {}
        self._schemas: dict[str, AnalyticsSchema] = {}

    # ── IAnalyticsSink ───────────────────────────────────────────

    async def initialize_dataset(self, schema: AnalyticsSchema) -> None:
        """Store the schema and prepare an empty row list."""
        self._schemas[schema.table_name] = schema
        self._data.setdefault(schema.table_name, [])

    async def push_batch(self, table: str, rows: list[dict[str, object]]) -> int:
        """Append rows to in-memory storage."""
        buf = self._data.setdefault(table, [])
        buf.extend(rows)
        logger.debug("InMemorySink: pushed %d rows to '%s'", len(rows), table)
        return len(rows)

    # ── Test helpers ─────────────────────────────────────────────

    def get_rows(self, table: str) -> list[dict[str, object]]:
        """Return all rows stored for the given table."""
        return list(self._data.get(table, []))

    def row_count(self, table: str) -> int:
        """Return the number of rows stored for the given table."""
        return len(self._data.get(table, []))

    def get_schema(self, table: str) -> AnalyticsSchema | None:
        """Return the stored schema for the given table, if any."""
        return self._schemas.get(table)

    def clear(self, table: str | None = None) -> None:
        """Clear stored rows (and optionally schemas).

        If ``table`` is provided, only that table's data is cleared.
        Otherwise all data is cleared.
        """
        if table is not None:
            self._data.pop(table, None)
        else:
            self._data.clear()

    @property
    def tables(self) -> list[str]:
        """Return the list of tables with stored data."""
        return list(self._data.keys())
