"""StructuredLoggingMiddleware — JSON log entries with correlation context."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from cqrs_ddd_core.correlation import get_correlation_id
from cqrs_ddd_core.ports.middleware import IMiddleware

from .metrics import _detect_kind

_log = logging.getLogger(__name__)


class StructuredLoggingMiddleware(IMiddleware):
    """Emits JSON log entries with kind, correlation_id, type, duration."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._log = logger or _log

    async def __call__(self, message: Any, next_handler: Any) -> Any:
        start = time.monotonic()
        kind = _detect_kind(message)
        msg_type = type(message).__name__
        outcome = "success"
        try:
            return await next_handler(message)
        except Exception:  # noqa: BLE001
            outcome = "error"
            raise
        finally:
            try:
                duration_ms = (time.monotonic() - start) * 1000
                entry = {
                    "kind": kind,
                    "message_type": msg_type,
                    "outcome": outcome,
                    "duration_ms": round(duration_ms, 2),
                    "correlation_id": get_correlation_id()
                    or getattr(message, "correlation_id", None),
                }
                self._log.info(json.dumps(entry))
            except Exception:  # noqa: BLE001
                _log.debug("Failed to emit structured log entry", exc_info=True)
