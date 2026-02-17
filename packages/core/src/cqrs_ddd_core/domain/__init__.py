"""Domain primitives: aggregates, events, value objects, mixins, registry."""

from __future__ import annotations

from .aggregate import AggregateRoot, Modification
from .event_registry import EventTypeRegistry
from .events import DomainEvent, enrich_event_metadata
from .mixins import ArchivableMixin, AuditableMixin
from .value_object import ValueObject

__all__ = [
    "AggregateRoot",
    "ArchivableMixin",
    "AuditableMixin",
    "DomainEvent",
    "EventTypeRegistry",
    "Modification",
    "ValueObject",
    "enrich_event_metadata",
]
