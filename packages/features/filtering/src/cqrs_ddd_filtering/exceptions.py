"""Filtering package exceptions."""

from __future__ import annotations

from cqrs_ddd_core.primitives.exceptions import ValidationError


class FilterParseError(ValidationError):
    """Raised when query string or filter structure is invalid."""


class FieldNotAllowedError(ValidationError):
    """Raised when a field is not in the whitelist or operator is disallowed."""


class SecurityConstraintError(ValidationError):
    """Raised when security constraint injection fails (e.g. missing tenant)."""
