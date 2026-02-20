"""QueryStringBuilder — spec + options -> query string (HATEOAS links)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

if TYPE_CHECKING:
    from .parser import QueryOptions


class QueryStringBuilder:
    """Build query string from specification and QueryOptions."""

    def build(
        self,
        *,
        spec: Any = None,
        options: QueryOptions | None = None,
        filter_key: str = "filter",
        sort_key: str = "sort",
        limit_key: str = "limit",
        offset_key: str = "offset",
        fields_key: str = "fields",
    ) -> str:
        """Produce query string (e.g. for pagination links)."""
        params: dict[str, str | int] = {}
        if options is not None:
            if options.limit is not None:
                params[limit_key] = options.limit
            if options.offset is not None:
                params[offset_key] = options.offset
            if options.sort:
                params[sort_key] = ",".join(
                    f"-{f}" if d == "desc" else f for f, d in options.sort
                )
            if options.fields:
                params[fields_key] = ",".join(options.fields)
        if spec is not None and hasattr(spec, "to_dict"):
            # Simplified: we don't reverse-engineer spec to colon form here
            _ = filter_key
        return urlencode(params) if params else ""
