import enum
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import BigInteger, DateTime, Enum, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .types.json import JSONType


class Base(DeclarativeBase):
    pass


class OutboxStatus(str, enum.Enum):
    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class OutboxMessage(Base):
    """
    Model for the Outbox pattern.
    Captures domain events to be published asynchronously.
    """

    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(
        Integer().with_variant(BigInteger, "postgresql"),
        primary_key=True,
        autoincrement=True,
    )
    event_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String)  # e.g. "OrderPlaced"
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType)  # Dialect-agnostic JSON
    status: Mapped[OutboxStatus] = mapped_column(
        Enum(OutboxStatus), default=OutboxStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=True)


class StoredEventModel(Base):
    """
    Model for the Event Store.
    Persists domain events for event sourcing and audit logs.
    """

    __tablename__ = "event_store"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    event_type: Mapped[str] = mapped_column(String, index=True)
    aggregate_id: Mapped[str] = mapped_column(String, index=True)
    aggregate_type: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    correlation_id: Mapped[str | None] = mapped_column(
        String, nullable=True, index=True
    )
    causation_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
