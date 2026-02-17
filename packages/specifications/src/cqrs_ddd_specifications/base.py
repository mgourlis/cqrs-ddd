from typing import Any, Generic, TypeVar

from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.domain.specification import ISpecification

T = TypeVar("T", contravariant=True, bound=AggregateRoot[Any])


class BaseSpecification(Generic[T], ISpecification[T]):
    """Base class for specifications with logic operator support."""

    def __and__(self, other: ISpecification[T]) -> "AndSpecification[T]":
        return AndSpecification(self, other)

    def __or__(self, other: ISpecification[T]) -> "OrSpecification[T]":
        return OrSpecification(self, other)

    def __invert__(self) -> "NotSpecification[T]":
        return NotSpecification(self)

    def merge(self, other: ISpecification[T]) -> "AndSpecification[T]":
        """Merge with another specification using logical AND."""
        return AndSpecification(self, other)


class AndSpecification(BaseSpecification[T]):
    """Logical AND composite specification."""

    def __init__(self, *specifications: ISpecification[T]) -> None:
        self.specifications = specifications

    def is_satisfied_by(self, candidate: T) -> bool:
        return all(spec.is_satisfied_by(candidate) for spec in self.specifications)

    def to_dict(self) -> dict[str, Any]:
        return {
            "op": "and",
            "conditions": [spec.to_dict() for spec in self.specifications],
        }


class OrSpecification(BaseSpecification[T]):
    """Logical OR composite specification."""

    def __init__(self, *specifications: ISpecification[T]) -> None:
        self.specifications = specifications

    def is_satisfied_by(self, candidate: T) -> bool:
        return any(spec.is_satisfied_by(candidate) for spec in self.specifications)

    def to_dict(self) -> dict[str, Any]:
        return {
            "op": "or",
            "conditions": [spec.to_dict() for spec in self.specifications],
        }


class NotSpecification(BaseSpecification[T]):
    """Logical NOT composite specification."""

    def __init__(self, specification: ISpecification[T]) -> None:
        self.specification = specification

    def is_satisfied_by(self, candidate: T) -> bool:
        return not self.specification.is_satisfied_by(candidate)

    def to_dict(self) -> dict[str, Any]:
        return {
            "op": "not",
            "conditions": [self.specification.to_dict()],
        }
