"""PayloadTracingMiddleware — OpenTelemetry payload events with sanitization."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, cast

from cqrs_ddd_core.correlation import get_correlation_id
from cqrs_ddd_core.ports.middleware import IMiddleware

_DEFAULT_SENSITIVE_FIELDS: frozenset[str] = frozenset(
    {
        "password",
        "passphrase",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "api_key",
        "private_key",
        "email",
        "phone",
        "address",
        "ssn",
        "card_number",
        "cvv",
    }
)
_logger = logging.getLogger(__name__)


class PayloadTracingMiddleware(IMiddleware):
    """Adds sanitized command/query payloads as OpenTelemetry span events.

    This middleware is intentionally conservative by default:
    - Sensitive fields are redacted.
    - Payloads are truncated to a maximum serialized size.
    - Raw sensitive fields are never emitted unless explicitly opted in.
    """

    def __init__(
        self,
        *,
        include_fields: set[str] | None = None,
        redact_fields: set[str] | None = None,
        hash_fields: set[str] | None = None,
        sensitive_fields: set[str] | None = None,
        max_payload_chars: int = 4096,
    ) -> None:
        self._trace_api = None
        try:
            trace_api = cast(
                "Any", __import__("opentelemetry.trace", fromlist=["trace"])
            )
            self._trace_api = trace_api.get_current_span
        except ImportError:
            pass

        self._include_fields = (
            {f.lower() for f in include_fields} if include_fields else None
        )
        self._redact_fields = {f.lower() for f in (redact_fields or set())}
        self._hash_fields = {f.lower() for f in (hash_fields or set())}
        sensitive = set(sensitive_fields or _DEFAULT_SENSITIVE_FIELDS)
        self._sensitive_fields = {f.lower() for f in sensitive}
        self._max_payload_chars = max_payload_chars

    async def __call__(self, message: Any, next_handler: Any) -> Any:
        span = self._get_active_span()
        if span is None:
            return await next_handler(message)

        msg_type = type(message).__name__
        try:
            payload = self._extract_payload(message)
            sanitized = self._sanitize_value(payload)
            payload_json = json.dumps(sanitized, default=str)
            truncated = len(payload_json) > self._max_payload_chars
            if truncated:
                payload_json = (
                    payload_json[: self._max_payload_chars] + "...<truncated>"
                )

            span.set_attribute("cqrs.command_type", msg_type)
            correlation_id = get_correlation_id() or getattr(
                message, "correlation_id", None
            )
            if correlation_id:
                span.set_attribute("cqrs.correlation_id", str(correlation_id))
            span.set_attribute("cqrs.payload_present", True)
            span.set_attribute("cqrs.payload_truncated", truncated)
            span.set_attribute("cqrs.payload_size", len(payload_json))
            span.add_event("cqrs.command_payload", {"payload": payload_json})
        except Exception as exc:  # noqa: BLE001
            # Payload tracing must never block command execution.
            _logger.debug("Payload tracing failed: %s", exc, exc_info=exc)

        return await next_handler(message)

    def _get_active_span(self) -> Any | None:
        """Return current recording span, or None when no active span exists."""
        if self._trace_api is None:
            return None
        try:
            span = self._trace_api()
        except Exception:  # noqa: BLE001
            return None
        if span is None:
            return None
        if hasattr(span, "is_recording") and not span.is_recording():
            return None
        if hasattr(span, "get_span_context"):
            try:
                if not span.get_span_context().is_valid:
                    return None
            except Exception:  # noqa: BLE001
                return None
        return span

    def _extract_payload(self, message: Any) -> Any:
        if hasattr(message, "model_dump"):
            return message.model_dump(mode="json")
        if isinstance(message, dict):
            return message
        if hasattr(message, "__dict__"):
            return vars(message)
        return {"raw": str(message)}

    def _sanitize_value(self, value: Any, field_name: str | None = None) -> Any:
        if isinstance(value, dict):
            output: dict[str, Any] = {}
            for key, item in value.items():
                key_norm = str(key).lower()
                if (
                    self._include_fields is not None
                    and key_norm not in self._include_fields
                ):
                    continue
                output[str(key)] = self._sanitize_value(item, key_norm)
            return output

        if isinstance(value, list):
            return [self._sanitize_value(item, field_name) for item in value]

        if field_name is None:
            return value

        if field_name in self._hash_fields:
            return self._hash_value(value)

        if field_name in self._redact_fields or field_name in self._sensitive_fields:
            return "***"

        return value

    def _hash_value(self, value: Any) -> str:
        payload = str(value).encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        return f"sha256:{digest}"
