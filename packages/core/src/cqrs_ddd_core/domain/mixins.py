"""Reusable domain mixins."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from ..primitives.exceptions import InvariantViolationError


class AuditableMixin(BaseModel):
    """Mixin that adds created_at / updated_at timestamps.

    **No soft-delete fields.** Use explicit domain Status enums
    (``OrderStatus.CANCELLED``) instead of ``is_deleted`` flags.
    """

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        """Update the ``updated_at`` timestamp to *now*."""
        object.__setattr__(self, "updated_at", datetime.now(timezone.utc))


class ArchivableMixin(BaseModel):
    """Mixin for aggregates that support archival.

    Provides ``archived_at`` / ``archived_by`` and archive/restore transitions.
    Use together with a domain Status enum for the main lifecycle
    (e.g. ``OrderStatus.ARCHIVED``).
    """

    archived_at: datetime | None = None
    archived_by: str | None = None

    @property
    def is_archived(self) -> bool:
        """Return True if the aggregate has been archived."""
        return self.archived_at is not None

    def archive(self, by: str | None = None) -> None:
        """Mark as archived. Raises if already archived."""
        if self.archived_at is not None:
            raise InvariantViolationError("Already archived")
        object.__setattr__(self, "archived_at", datetime.now(timezone.utc))
        if by is not None:
            object.__setattr__(self, "archived_by", by)

    def restore(self) -> None:
        """Clear archival. Raises if not archived."""
        if self.archived_at is None:
            raise InvariantViolationError("Not archived")
        object.__setattr__(self, "archived_at", None)
        object.__setattr__(self, "archived_by", None)
