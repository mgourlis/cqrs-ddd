"""MessageEnvelope — standard immutable wrapper for transport."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class MessageEnvelope(BaseModel):
    """Immutable wrapper for messages over the wire.

    Carries payload, tracing IDs, and retry metadata.
    """

    model_config = ConfigDict(frozen=True)

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = Field(..., description="Registry key, e.g. 'OrderCreated'")
    payload: dict[str, object] = Field(default_factory=dict)
    correlation_id: str | None = None
    causation_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    headers: dict[str, str] = Field(default_factory=dict)
    attempt: int = Field(default=1, ge=1, description="Retry attempt count")
