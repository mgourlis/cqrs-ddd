"""Response wrappers for command and query handlers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Generic, TypeVar, cast

if TYPE_CHECKING:
    from ..domain.events import DomainEvent

T = TypeVar("T")


@dataclass(frozen=True)
class CommandResponse(Generic[T]):
    """Wrapper returned by command handlers.

    Carries the result payload together with the domain events that were
    produced during the command execution plus tracing context.
    """

    result: T
    events: list[DomainEvent] = field(
        default_factory=lambda: cast("list[DomainEvent]", [])
    )
    success: bool = True
    correlation_id: str | None = None
    causation_id: str | None = None


@dataclass(frozen=True)
class QueryResponse(Generic[T]):
    """Wrapper returned by query handlers."""

    result: T
    success: bool = True
    correlation_id: str | None = None
    causation_id: str | None = None
