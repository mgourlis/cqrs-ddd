"""ObservabilityContext — ContextVar for trace_id, span_id, correlation_id."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from cqrs_ddd_core.correlation import get_correlation_id

_observability_ctx: ContextVar[dict[str, Any] | None] = ContextVar(
    "observability_ctx",
    default=None,
)


class ObservabilityContext:
    """ContextVar-backed storage for trace_id, span_id, correlation_id."""

    @staticmethod
    def get() -> dict[str, Any]:
        return dict(_observability_ctx.get() or {})

    @staticmethod
    def set(**kwargs: Any) -> None:
        if not kwargs:
            _observability_ctx.set({})
            return
        ctx = dict(_observability_ctx.get() or {})
        ctx.update(kwargs)
        _observability_ctx.set(ctx)

    @staticmethod
    def get_correlation_id() -> str | None:
        # Delegate to core to avoid dual correlation sources.
        return get_correlation_id()

    @staticmethod
    def get_trace_id() -> str | None:
        return (_observability_ctx.get() or {}).get("trace_id")

    @staticmethod
    def get_span_id() -> str | None:
        return (_observability_ctx.get() or {}).get("span_id")
