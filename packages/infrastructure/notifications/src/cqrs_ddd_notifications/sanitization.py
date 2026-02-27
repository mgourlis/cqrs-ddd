"""Metadata sanitization — prevents PII leakage into logs and provider dashboards."""

from __future__ import annotations

import hashlib
from typing import Any

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
        "ssn",
        "card_number",
        "cvv",
        # Note: email/phone are NOT in this list — they're needed for delivery
    }
)


class MetadataSanitizer:
    """
    Sanitizes notification metadata to prevent PII leakage.

    Unlike PayloadTracingMiddleware which redacts email/phone for tracing,
    notifications NEED email/phone for delivery. This sanitizer focuses on
    credentials and secrets that should never appear in provider dashboards.
    """

    def __init__(
        self,
        *,
        redact_fields: set[str] | None = None,
        hash_fields: set[str] | None = None,
        sensitive_fields: set[str] | None = None,
    ) -> None:
        self._redact_fields = {f.lower() for f in (redact_fields or set())}
        self._hash_fields = {f.lower() for f in (hash_fields or set())}
        sensitive = set(sensitive_fields or _DEFAULT_SENSITIVE_FIELDS)
        self._sensitive_fields = {f.lower() for f in sensitive}

    def sanitize(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Return a sanitized copy of metadata safe for logging/providers."""
        return self._sanitize_dict(metadata)

    def _sanitize_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in data.items():
            key_norm = str(key).lower()
            result[str(key)] = self._sanitize_value(value, key_norm)
        return result

    def _sanitize_value(self, value: Any, field_name: str | None = None) -> Any:
        if isinstance(value, dict):
            return self._sanitize_dict(value)
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


# Default instance for convenience
default_sanitizer = MetadataSanitizer()
