"""
SQLAlchemy models for Advanced Core features.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import BigInteger, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.models import Base
from ..core.types.json import JSONType


class SagaStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUSPENDED = "SUSPENDED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    COMPENSATING = "COMPENSATING"


class SagaStateModel(Base):
    """
    Persists the state of a Saga.
    """

    __tablename__ = "saga_state"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    correlation_id: Mapped[str] = mapped_column(String, index=True, unique=True)
    saga_type: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[SagaStatus] = mapped_column(Enum(SagaStatus), index=True)
    state: Mapped[dict[str, Any]] = mapped_column(JSONType)
    events: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )
    timeout_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0)

    __mapper_args__ = {
        "version_id_col": version,
        "version_id_generator": False,
    }


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class BackgroundJobModel(Base):
    """
    Persists Background Jobs.
    Maps to BaseBackgroundJob aggregate root.
    """

    __tablename__ = "background_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_type: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.PENDING, index=True
    )
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    processed_items: Mapped[int] = mapped_column(Integer, default=0)
    result_data: Mapped[dict[str, Any]] = mapped_column(JSONType)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    broker_message_id: Mapped[str | None] = mapped_column(String, nullable=True)

    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, default=0)

    __mapper_args__ = {
        "version_id_col": version,
        "version_id_generator": False,
    }

    job_metadata: Mapped[dict[str, Any]] = mapped_column(JSONType)
    correlation_id: Mapped[str | None] = mapped_column(
        String, nullable=True, index=True
    )


class ScheduledCommandModel(Base):
    """
    Persists Scheduled Commands.
    """

    __tablename__ = "scheduled_commands"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    command_type: Mapped[str] = mapped_column(String)
    command_payload: Mapped[dict[str, Any]] = mapped_column(JSONType)

    execute_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(
        String, default="PENDING", index=True
    )  # PENDING, EXECUTED, CANCELLED

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    description: Mapped[str | None] = mapped_column(String, nullable=True)


class SnapshotModel(Base):
    """
    Persists Aggregate Snapshots.
    """

    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(
        Integer().with_variant(BigInteger, "postgresql"),
        primary_key=True,
        autoincrement=True,
    )
    aggregate_id: Mapped[str] = mapped_column(String, index=True)
    aggregate_type: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot_data: Mapped[dict[str, Any]] = mapped_column(JSONType)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
