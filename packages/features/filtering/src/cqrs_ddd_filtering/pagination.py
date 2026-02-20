"""PaginationParser — offset/limit and cursor-based from query params."""

from __future__ import annotations

import base64
import contextlib
import json
from typing import Any, NamedTuple


class PaginationResult(NamedTuple):
    offset: int | None
    limit: int | None
    cursor: dict[str, Any] | None


class PaginationParser:
    """Parse offset/limit and cursor from query params."""

    def parse(
        self,
        query_params: dict[str, Any],
        *,
        offset_key: str = "offset",
        limit_key: str = "limit",
        cursor_key: str = "cursor",
        default_limit: int = 20,
        max_limit: int = 100,
    ) -> PaginationResult:
        offset = query_params.get(offset_key)
        if offset is not None:
            try:
                offset = max(0, int(offset))
            except (TypeError, ValueError):
                offset = 0
        limit = query_params.get(limit_key)
        if limit is not None:
            try:
                limit = min(max_limit, max(1, int(limit)))
            except (TypeError, ValueError):
                limit = default_limit
        else:
            limit = default_limit
        cursor_raw = query_params.get(cursor_key)
        cursor = None
        if cursor_raw:
            with contextlib.suppress(Exception):
                cursor = json.loads(base64.b64decode(cursor_raw).decode("utf-8"))
        return PaginationResult(offset=offset, limit=limit, cursor=cursor)

    @staticmethod
    def encode_cursor(data: dict[str, Any]) -> str:
        """Encode cursor dict to base64 string."""
        encoded = base64.b64encode(
            json.dumps(data, sort_keys=True).encode("utf-8")
        )
        return encoded.decode("ascii")
