"""Specification pattern primitives."""

from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

from .aggregate import AggregateRoot

T = TypeVar("T", contravariant=True, bound=AggregateRoot[Any])


@runtime_checkable
class ISpecification(Protocol, Generic[T]):
    """
    Protocol for the Specification pattern.
    Used to encapsulate business rules for querying and filtering aggregates.
    """

    def is_satisfied_by(self, candidate: T) -> bool:
        """
        Check if the aggregate version of the specification is satisfied.
        Used primarily for in-memory filtering.
        """
        ...

    def to_dict(self) -> dict[str, Any]:
        """
        Return a dictionary representation of the specification.
        Useful for serializing criteria across process boundaries or to DB drivers.
        """
        ...
