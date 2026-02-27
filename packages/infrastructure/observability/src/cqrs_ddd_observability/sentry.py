"""SentryMiddleware — capture exceptions with context (optional [sentry] extra)."""

from __future__ import annotations

from typing import Any

from cqrs_ddd_core.correlation import get_correlation_id
from cqrs_ddd_core.ports.middleware import IMiddleware


class SentryMiddleware(IMiddleware):
    """Captures exceptions to Sentry with correlation_id and message type."""

    async def __call__(self, message: Any, next_handler: Any) -> Any:
        try:
            return await next_handler(message)
        except Exception as e:
            try:
                import sentry_sdk

                with sentry_sdk.configure_scope() as scope:
                    scope.set_tag("cqrs.message_type", type(message).__name__)
                    cid = get_correlation_id() or getattr(
                        message, "correlation_id", None
                    )
                    if cid:
                        scope.set_tag("correlation_id", cid)
                sentry_sdk.capture_exception(e)
            except ImportError:
                pass
            except Exception:  # noqa: BLE001
                pass  # do not let Sentry reporting failures mask the original error
            raise
