"""Aggregate Root base class with Generic ID support."""

from __future__ import annotations

from typing import TYPE_CHECKING, Generic, TypeVar, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, PrivateAttr
from pydantic_core import PydanticUndefined

if TYPE_CHECKING:
    from ..primitives.id_generator import IIDGenerator
    from .events import DomainEvent

ID = TypeVar("ID", str, int, UUID)


class AggregateRoot(BaseModel, Generic[ID]):
    """Base class for all Aggregate Roots.

    Generic over ``ID`` to support UUID, int, or str primary keys.
    Includes logic for collecting domain events and versioning.
    Supports ID generation via IIDGenerator at initialization time.

    Usage::

        class Order(AggregateRoot[UUID]):
            status: OrderStatus = OrderStatus.PENDING

        # ID generated automatically with generator
        order = Order(id_generator=generator, status=OrderStatus.PENDING)

        # ID provided explicitly
        order = Order(id=some_id, status=OrderStatus.PENDING)
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: ID
    _version: int = PrivateAttr(default=0)
    _domain_events: list[DomainEvent] = PrivateAttr(
        default_factory=lambda: cast("list[DomainEvent]", [])
    )
    _id_generator: IIDGenerator | None = PrivateAttr(default=None)

    def __init__(
        self, id_generator: IIDGenerator | None = None, **data: object
    ) -> None:
        """
        Initialize an Aggregate Root.

        Args:
            id_generator: Optional ID generator strategy. If provided and 'id'
                         is not in data, ID will be auto-generated.
            **data: Aggregate attributes. Must include 'id' OR have
                id_generator provided.

        Raises:
            ValueError: If neither 'id' is provided nor id_generator is supplied.
        """
        # Auto-generate ID if not provided
        if "id" not in data and id_generator is not None:
            data = {**data, "id": id_generator.next_id()}
        elif "id" not in data:
            # Check if there is a default or default_factory for 'id'
            # to avoid breaking subclasses like BaseBackgroundJob that use
            # Field(default_factory=...)  # noqa: ERA001
            field_info = self.__class__.model_fields.get("id")
            # In Pydantic v2, we check both default and default_factory
            has_default = field_info and (
                (field_info.default is not PydanticUndefined)
                or (field_info.default_factory is not None)
            )
            if not has_default:
                raise ValueError(
                    "Either 'id' must be provided or 'id_generator' must be supplied "
                    "to auto-generate the ID at initialization time."
                )

        super().__init__(**data)
        object.__setattr__(self, "_domain_events", [])
        version = data.get("_version", 0)
        object.__setattr__(self, "_version", version)
        object.__setattr__(self, "_id_generator", id_generator)

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


class Modification(Generic[ID]):
    """DTO bundling an entity with its collected domain events.

    Returned by command handlers to carry both the mutated aggregate
    and the events it produced.
    """

    entity: AggregateRoot[ID]
    events: list[DomainEvent]

    def __init__(
        self, entity: AggregateRoot[ID], events: list[DomainEvent] | None = None
    ) -> None:
        self.entity = entity
        self.events = events if events is not None else entity.collect_events()
