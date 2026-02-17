"""ValidationResult — structured validation errors."""

from __future__ import annotations

from dataclasses import dataclass, field


def default_errors_factory() -> dict[str, list[str]]:
    """Factory for mutable default dict in ValidationResult dataclass fields.

    Use this instead of dict() or {} to avoid dataclass default_factory issues.
    """
    return {}


@dataclass
class ValidationResult:
    """Collects field-level validation errors.

    Usage::

        result = ValidationResult.success()
        result = ValidationResult.failure({"name": ["is required"]})
    """

    errors: dict[str, list[str]] = field(default_factory=default_errors_factory)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    # ── Factory methods ──────────────────────────────────────────

    @classmethod
    def success(cls) -> ValidationResult:
        return cls()

    @classmethod
    def failure(cls, errors: dict[str, list[str]]) -> ValidationResult:
        return cls(errors=errors)

    # ── Merging ──────────────────────────────────────────────────

    def merge(self, other: ValidationResult) -> ValidationResult:
        """Merge another result into this one, combining all errors."""
        merged = dict(self.errors)
        for field_name, messages in other.errors.items():
            existing = merged.get(field_name, [])
            merged[field_name] = existing + messages
        return ValidationResult(errors=merged)

    def add_error(self, field_name: str, message: str) -> None:
        """Add a single error for *field_name*."""
        self.errors.setdefault(field_name, []).append(message)

    def __bool__(self) -> bool:
        return self.is_valid
