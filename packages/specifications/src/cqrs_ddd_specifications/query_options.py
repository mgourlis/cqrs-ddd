"""
Query options for pagination, ordering, streaming, and grouping.

``QueryOptions`` wraps a specification with result-shaping parameters.
The specification defines *what* to filter; ``QueryOptions`` defines
*how* results are returned.

These options are consumed by the persistence layer (repository /
query handler), not by the specification itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
    from cqrs_ddd_core.domain.specification import ISpecification
except ImportError:  # pragma: no cover
    ISpecification = Any  # type: ignore[assignment,misc]


@dataclass(frozen=True)
class QueryOptions:
    """
    Immutable container for result-shaping parameters.

    Attributes:
        specification: The filter specification (optional; ``None`` = no filter).
        limit: Maximum number of results.
        offset: Number of results to skip.
        order_by: Field ordering list.
            Prefix with ``-`` for descending, e.g. ``["-created_at", "name"]``.
        distinct: If ``True``, return only distinct rows.
        group_by: Fields to group results by.
        select_fields: Specific fields/columns to select (projection).
    """

    specification: ISpecification[Any] | None = None
    limit: int | None = None
    offset: int | None = None
    order_by: list[str] = field(default_factory=list)
    distinct: bool = False
    group_by: list[str] = field(default_factory=list)
    select_fields: list[str] = field(default_factory=list)

    def with_specification(self, spec: ISpecification[Any]) -> QueryOptions:
        """Return a copy with the specification replaced."""
        return QueryOptions(
            specification=spec,
            limit=self.limit,
            offset=self.offset,
            order_by=list(self.order_by),
            distinct=self.distinct,
            group_by=list(self.group_by),
            select_fields=list(self.select_fields),
        )

    def with_pagination(
        self,
        limit: int | None = None,
        offset: int | None = None,
    ) -> QueryOptions:
        """Return a copy with updated pagination parameters."""
        return QueryOptions(
            specification=self.specification,
            limit=limit if limit is not None else self.limit,
            offset=offset if offset is not None else self.offset,
            order_by=list(self.order_by),
            distinct=self.distinct,
            group_by=list(self.group_by),
            select_fields=list(self.select_fields),
        )

    def with_ordering(self, *fields: str) -> QueryOptions:
        """Return a copy with updated ordering."""
        return QueryOptions(
            specification=self.specification,
            limit=self.limit,
            offset=self.offset,
            order_by=list(fields),
            distinct=self.distinct,
            group_by=list(self.group_by),
            select_fields=list(self.select_fields),
        )

    def merge(self, other: QueryOptions) -> QueryOptions:
        """
        Merge two ``QueryOptions`` instances.

        - Specifications are combined with AND.
        - ``other``'s limit/offset/distinct override ``self``'s if set.
        - Ordering and group_by lists are concatenated (``other`` appended).
        - select_fields are concatenated (``other`` appended).
        """
        from .base import AndSpecification

        merged_spec: ISpecification[Any] | None = self.specification
        if other.specification is not None:
            if merged_spec is not None:
                merged_spec = AndSpecification(merged_spec, other.specification)
            else:
                merged_spec = other.specification

        return QueryOptions(
            specification=merged_spec,
            limit=other.limit if other.limit is not None else self.limit,
            offset=other.offset if other.offset is not None else self.offset,
            order_by=list(self.order_by) + list(other.order_by),
            distinct=other.distinct or self.distinct,
            group_by=list(self.group_by) + list(other.group_by),
            select_fields=list(self.select_fields) + list(other.select_fields),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dictionary."""
        result: dict[str, Any] = {}
        if self.specification is not None:
            result["specification"] = self.specification.to_dict()
        if self.limit is not None:
            result["limit"] = self.limit
        if self.offset is not None:
            result["offset"] = self.offset
        if self.order_by:
            result["order_by"] = self.order_by
        if self.distinct:
            result["distinct"] = True
        if self.group_by:
            result["group_by"] = self.group_by
        if self.select_fields:
            result["select_fields"] = self.select_fields
        return result
