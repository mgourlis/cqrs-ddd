"""MetricsMiddleware — Prometheus counters/histograms (optional [prometheus] extra).

Emits ``cqrs_message_duration_seconds`` and ``cqrs_message_total`` with labels
``{kind, message_type, outcome}`` where *kind* is ``command``, ``query``, or
``message`` (fallback).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from cqrs_ddd_core.ports.middleware import IMiddleware

_logger = logging.getLogger(__name__)


def _detect_kind(message: Any) -> str:
    """Classify a message as command, query, or generic message."""
    from cqrs_ddd_core.cqrs.command import Command
    from cqrs_ddd_core.cqrs.query import Query

    if isinstance(message, Command):
        return "command"
    if isinstance(message, Query):
        return "query"
    return "message"


class MetricsMiddleware(IMiddleware):
    """Records duration and outcome per message with kind discrimination.

    Prometheus metrics:
      - ``cqrs_message_duration_seconds{kind, message_type, outcome}``
      - ``cqrs_message_total{kind, message_type, outcome}``
    """

    def __init__(self) -> None:
        self._histogram = None
        self._counter = None
        try:
            from prometheus_client import Counter, Histogram

            self._histogram = Histogram(
                "cqrs_message_duration_seconds",
                "Handler duration",
                ["kind", "message_type", "outcome"],
            )
            self._counter = Counter(
                "cqrs_message_total",
                "Handler invocations",
                ["kind", "message_type", "outcome"],
            )
        except ImportError:
            pass

    async def __call__(self, message: Any, next_handler: Any) -> Any:
        if self._histogram is None or self._counter is None:
            return await next_handler(message)
        kind = _detect_kind(message)
        msg_type = type(message).__name__
        start = time.monotonic()
        outcome = "success"
        try:
            return await next_handler(message)
        except Exception:
            outcome = "error"
            raise
        finally:
            try:
                labels = {"kind": kind, "message_type": msg_type, "outcome": outcome}
                self._histogram.labels(**labels).observe(time.monotonic() - start)
                self._counter.labels(**labels).inc()
            except Exception:  # noqa: BLE001
                _logger.debug("Failed to emit metrics labels", exc_info=True)
