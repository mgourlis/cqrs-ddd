"""AnalyticsBuffer — batches rows before pushing to sink."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING

from cqrs_ddd_core.ports.background_worker import IBackgroundWorker

from .exceptions import BufferFlushError

if TYPE_CHECKING:
    from .ports import IAnalyticsSink

logger = logging.getLogger(__name__)


class AnalyticsBuffer(IBackgroundWorker):
    """Accumulates analytics rows and flushes when thresholds are reached.

    Rows are flushed when either ``batch_size`` rows are buffered *or*
    ``flush_interval`` seconds have elapsed since the last flush.

    Implements :class:`~cqrs_ddd_core.ports.background_worker.IBackgroundWorker`
    so the periodic flush timer can be managed alongside other workers.

    Args:
        sink: The analytics sink to push rows to.
        batch_size: Number of rows that triggers an immediate flush.
        flush_interval: Maximum seconds between flushes.
    """

    def __init__(
        self,
        sink: IAnalyticsSink,
        *,
        batch_size: int = 1000,
        flush_interval: float = 30.0,
    ) -> None:
        self._sink = sink
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._buffers: dict[str, list[dict[str, object]]] = {}
        self._last_flush: float = time.monotonic()
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task[None] | None = None
        self._running = False

    # ── IBackgroundWorker ────────────────────────────────────────

    async def start(self) -> None:
        """Start the periodic flush timer."""
        if self._running:
            return
        self._running = True
        self._last_flush = time.monotonic()
        self._flush_task = asyncio.create_task(self._periodic_flush())

    async def stop(self) -> None:
        """Stop the flush timer and flush remaining rows."""
        self._running = False
        if self._flush_task is not None:
            self._flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._flush_task
            self._flush_task = None
        # Final flush of remaining data
        await self.flush_all()

    # ── Public API ───────────────────────────────────────────────

    async def add(self, table: str, row: dict[str, object]) -> None:
        """Add a single row to the buffer for the given table.

        If ``batch_size`` is reached, the buffer for that table is
        flushed immediately.
        """
        async with self._lock:
            buf = self._buffers.setdefault(table, [])
            buf.append(row)
            if len(buf) >= self._batch_size:
                await self._flush_table(table)

    async def flush_all(self) -> None:
        """Flush all buffered rows across all tables."""
        async with self._lock:
            tables = list(self._buffers.keys())
            for table in tables:
                if self._buffers.get(table):
                    await self._flush_table(table)
            self._last_flush = time.monotonic()

    @property
    def pending_count(self) -> int:
        """Return the total number of rows currently buffered."""
        return sum(len(rows) for rows in self._buffers.values())

    # ── Internal ─────────────────────────────────────────────────

    async def _flush_table(self, table: str) -> None:
        """Flush rows for a single table. Must be called under ``self._lock``."""
        rows = self._buffers.pop(table, [])
        if not rows:
            return
        try:
            pushed = await self._sink.push_batch(table, rows)
            logger.info("Flushed %d rows to table '%s'", pushed, table)
        except Exception as exc:
            # Re-add rows to buffer so they aren't lost
            existing = self._buffers.setdefault(table, [])
            existing[:0] = rows  # Prepend to preserve order
            raise BufferFlushError(
                f"Failed to flush {len(rows)} rows to table '{table}': {exc}"
            ) from exc

    async def _periodic_flush(self) -> None:
        """Background loop that flushes on the interval timer."""
        while self._running:
            try:
                await asyncio.sleep(self._flush_interval)
                elapsed = time.monotonic() - self._last_flush
                if elapsed >= self._flush_interval:
                    await self.flush_all()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Error during periodic analytics flush")
