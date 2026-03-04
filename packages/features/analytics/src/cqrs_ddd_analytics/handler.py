"""AnalyticsEventHandler — EventHandler that maps, buffers, and pushes rows."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cqrs_ddd_core.cqrs.handler import EventHandler
from cqrs_ddd_core.domain.events import DomainEvent

if TYPE_CHECKING:
    from .buffer import AnalyticsBuffer
    from .ports import IRowMapper

logger = logging.getLogger(__name__)


class AnalyticsEventHandler(EventHandler[DomainEvent]):
    """Domain event handler that maps events to rows and buffers them.

    Receives events from the ``EventDispatcher``, uses an ``IRowMapper``
    to convert them to tabular rows, and adds them to an
    ``AnalyticsBuffer`` for batched writing.

    Args:
        mapper: The row mapper to use for event-to-row conversion.
        buffer: The analytics buffer to accumulate rows.
        table: The target table name for rows.
    """

    def __init__(
        self,
        mapper: IRowMapper,
        buffer: AnalyticsBuffer,
        table: str,
    ) -> None:
        self._mapper = mapper
        self._buffer = buffer
        self._table = table

    async def handle(self, event: DomainEvent) -> None:
        """Map the event to row(s) and add to the buffer."""
        result = self._mapper.map(event)

        if result is None:
            return

        rows = [result] if isinstance(result, dict) else result

        for row in rows:
            await self._buffer.add(self._table, row)

        logger.debug(
            "Buffered %d row(s) for table '%s' from %s",
            len(rows),
            self._table,
            type(event).__name__,
        )
