"""Domain primitives: aggregates, events, value objects, mixins, registry."""

from __future__ import annotations

from .aggregate import AggregateRoot
from .event_registry import EventTypeRegistry
from .events import DomainEvent, enrich_event_metadata
from .mixins import (
    HAS_GEO,
    AggregateRootMixin,
    ArchivableMixin,
    AuditableMixin,
)
from .value_object import ValueObject

__all__: list[str] = [
    "AggregateRoot",
    "AggregateRootMixin",
    "ArchivableMixin",
    "AuditableMixin",
    "DomainEvent",
    "EventTypeRegistry",
    "HAS_GEO",
    "ValueObject",
    "enrich_event_metadata",
]

if HAS_GEO:
    from .mixins import SpatialMixin  # noqa: F401

    __all__.append("SpatialMixin")
