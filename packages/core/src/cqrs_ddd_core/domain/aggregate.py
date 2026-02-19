"""Aggregate Root base class with Generic ID support."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, PrivateAttr
from pydantic_core import PydanticUndefined
from typing_extensions import Self

from .mixins import AggregateRootMixin

if TYPE_CHECKING:
    from ..primitives.id_generator import IIDGenerator

ID = TypeVar("ID", str, int, UUID)


class AggregateRoot(AggregateRootMixin, BaseModel, Generic[ID]):
    """Base class for all Aggregate Roots.

    Generic over ``ID`` to support UUID, int, or str primary keys.
    Event collection and versioning are provided by :class:`.mixins.AggregateRootMixin`.
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

    @classmethod
    def reconstitute(cls, aggregate_id: ID, **data: Any) -> Self:
        """Create an aggregate instance for reconstitution (load/replay) only.

        Used by the event-sourcing loader to obtain a minimal instance before
        applying the event stream. Must not run domain validation; subclasses
        should not override with invariant checks. For domain creation (e.g.
        command side), use :meth:`create` instead.
        """
        return cls(id=aggregate_id, **data)

    @classmethod
    def create(
        cls,
        aggregate_id: ID | None = None,
        id_generator: IIDGenerator | None = None,
        **data: Any,
    ) -> Self:
        """Create an aggregate instance for domain use (command side).

        When ``aggregate_id`` is provided, it is used. When ``aggregate_id`` is
        not provided and ``id_generator`` is, the id is generated via
        ``id_generator.next_id()``. Override to enforce invariants or apply
        the first event. The loader uses :meth:`reconstitute`, not this method.
        """
        if aggregate_id is not None:
            return cls(id=aggregate_id, **data)
        if id_generator is not None:
            return cls(id_generator=id_generator, **data)
        return cls(**data)
