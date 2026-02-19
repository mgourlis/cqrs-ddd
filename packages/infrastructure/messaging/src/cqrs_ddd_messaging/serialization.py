"""EnvelopeSerializer — JSON roundtrip with EventTypeRegistry hydration."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from .envelope import MessageEnvelope
from .exceptions import MessagingSerializationError

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.event_registry import EventTypeRegistry


def _json_serializer(obj: Any) -> Any:
    """Serialize datetime and other non-JSON types."""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class EnvelopeSerializer:
    """Serialize/deserialize MessageEnvelope to/from JSON bytes.

    Uses EventTypeRegistry from core for type-safe payload hydration to domain events.
    """

    def __init__(self, registry: EventTypeRegistry | None = None) -> None:
        """Optionally pass a shared EventTypeRegistry for deserialization."""
        self._registry = registry

    def serialize(self, envelope: MessageEnvelope) -> bytes:
        """Encode envelope to JSON bytes."""
        try:
            data = envelope.model_dump(mode="json")
            return json.dumps(data, default=_json_serializer).encode("utf-8")
        except (TypeError, ValueError) as e:
            raise MessagingSerializationError(str(e)) from e

    def deserialize(self, raw: bytes) -> MessageEnvelope:
        """Decode JSON bytes to MessageEnvelope."""
        try:
            data = json.loads(raw.decode("utf-8"))
            ts = data.get("timestamp")
            if isinstance(ts, str):
                from datetime import datetime

                data["timestamp"] = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return MessageEnvelope.model_validate(data)
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            raise MessagingSerializationError(str(e)) from e

    def hydrate(self, envelope: MessageEnvelope) -> Any:
        """Hydrate envelope payload to a domain event using EventTypeRegistry.

        Returns the hydrated domain event, or the raw payload dict if no registry
        is set or the event type is not registered.
        """
        if not self._registry:
            return envelope.payload
        event = self._registry.hydrate(envelope.event_type, envelope.payload)
        if event is not None:
            return event
        return envelope.payload
