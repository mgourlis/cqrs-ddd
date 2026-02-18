"""Reusable domain mixins."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel, Field, PrivateAttr

from ..primitives.exceptions import InvariantViolationError

if TYPE_CHECKING:
    from geojson_pydantic.geometries import Geometry as GeoJSONGeometryType

    from .events import DomainEvent

GeoJSONGeometry: type[GeoJSONGeometryType] | None = None
try:
    from geojson_pydantic.geometries import Geometry as _GeoJSONGeometry

    GeoJSONGeometry = cast("Any", _GeoJSONGeometry)
    HAS_GEO = True
except ImportError:
    HAS_GEO = False
    GeoJSONGeometry = None


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


if HAS_GEO and GeoJSONGeometry is not None:

    class SpatialMixin(BaseModel):
        """Mixin for aggregates (or entities) that have a geographic location.

        Stores location as a GeoJSON geometry (validated by geojson-pydantic).
        The persistence layer (e.g. SQLAlchemy + GeoAlchemy2) can map this to a
        geom column.
        """

        geom: GeoJSONGeometryType | None = Field(
            default=None,
            description="GeoJSON geometry (validated by geojson-pydantic)",
        )
else:
    SpatialMixin = None  # type: ignore[misc, assignment]


class AggregateRootMixin(BaseModel):
    """Mixin that provides event collection and versioning for aggregate roots.

    Use together with :class:`AggregateRoot` or as the base for custom aggregate-like
    entities that need to record domain events and track a persistence-managed version.
    """

    _version: int = PrivateAttr(default=0)
    _domain_events: list[DomainEvent] = PrivateAttr(
        default_factory=lambda: cast("list[DomainEvent]", [])
    )

    def add_event(self, event: DomainEvent) -> None:
        """Record a domain event to be dispatched later."""
        self._domain_events.append(event)

    def collect_events(self) -> list[DomainEvent]:
        """Return all recorded events and clear the internal list."""
        events = list(self._domain_events)
        self._domain_events.clear()
        return events

    @property
    def version(self) -> int:
        """Read-only version, managed by the persistence layer."""
        return self._version
