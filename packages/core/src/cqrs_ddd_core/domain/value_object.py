"""Immutable Value Object base class."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ValueObject(BaseModel):
    """Base class for Value Objects.

    Value objects are immutable and defined by their attributes.
    Equality is structural (all fields compared).
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, self.__class__):
            return False
        return self.model_dump() == other.model_dump()

    def __hash__(self) -> int:
        return hash(tuple(sorted(self.model_dump().items())))
