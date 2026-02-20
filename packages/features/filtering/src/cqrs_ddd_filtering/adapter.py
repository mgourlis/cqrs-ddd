"""IFilterAdapter — protocol for backend-specific translation."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IFilterAdapter(Protocol):
    """Translate enriched specification to backend-specific query.

    Examples include MongoDB filter docs or SQL WHERE constructs.
    """

    def to_backend_query(self, spec: Any, options: Any) -> Any:
        """Return backend-native query structure."""
        ...
