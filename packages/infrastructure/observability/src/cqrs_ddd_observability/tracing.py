"""TracingMiddleware — OpenTelemetry spans (optional [opentelemetry] extra)."""

from __future__ import annotations

import contextlib
from typing import Any, cast

from cqrs_ddd_core.correlation import get_correlation_id
from cqrs_ddd_core.ports.middleware import IMiddleware


class TracingMiddleware(IMiddleware):
    """Creates a span per message; records command_type,
    handler, correlation_id, outcome, duration."""

    def __init__(self) -> None:
        self._tracer = None
        try:
            trace_api = cast(
                "Any", __import__("opentelemetry.trace", fromlist=["trace"])
            )

            self._tracer = trace_api.get_tracer("cqrs-ddd-observability", "0.1.0")
        except ImportError:
            pass

    async def __call__(self, message: Any, next_handler: Any) -> Any:
        if self._tracer is None:
            return await next_handler(message)
        msg_type = type(message).__name__
        with self._tracer.start_as_current_span(f"cqrs.{msg_type}") as span:
            try:
                span.set_attribute("cqrs.command_type", msg_type)
                correlation_id = get_correlation_id() or getattr(
                    message, "correlation_id", None
                )
                if correlation_id:
                    span.set_attribute("cqrs.correlation_id", str(correlation_id))
                result = await next_handler(message)
                span.set_attribute("cqrs.outcome", "success")
                return result
            except Exception as e:
                span.set_attribute("cqrs.outcome", "error")
                with contextlib.suppress(Exception):
                    span.record_exception(e)
                raise
