"""Shared helpers for normalising search criteria and extracting context."""

from __future__ import annotations

from typing import Any


def normalise_criteria(criteria: Any) -> tuple[Any, Any | None]:
    """Return ``(specification, options)`` from search criteria.

    Args:
        criteria: Either an object with a ``specification`` attribute
            (e.g. QueryOptions) or the specification itself.

    Returns:
        A tuple of ``(specification, options)`` where options may be None.
    """
    if hasattr(criteria, "specification"):
        return getattr(criteria, "specification", None), criteria
    return criteria, None


def extract_search_context(
    spec: Any, options: Any | None
) -> tuple[Any, Any, Any, Any]:
    """Extract order_by, limit, offset, fields from spec and options.

    Args:
        spec: Specification object (may have order_by, sort, limit, offset, etc.).
        options: Optional options object (may have order_by, sort, limit, etc.).

    Returns:
        A tuple ``(order_by, limit, offset, fields)``.
    """
    order_by = None
    limit = None
    offset = None
    fields = None
    if options is not None:
        order_by = getattr(options, "order_by", None) or getattr(
            options, "sort", None
        )
        limit = getattr(options, "limit", None)
        offset = getattr(options, "offset", None)
        fields = getattr(options, "select_fields", None) or getattr(
            options, "fields", None
        )
    if order_by is None and spec is not None:
        order_by = getattr(spec, "order_by", None) or getattr(spec, "sort", None)
    if limit is None and spec is not None:
        limit = getattr(spec, "limit", None)
    if offset is None and spec is not None:
        offset = getattr(spec, "offset", None)
    if fields is None and spec is not None:
        fields = getattr(spec, "select_fields", None) or getattr(
            spec, "fields", None
        )
    return order_by, limit, offset, fields
