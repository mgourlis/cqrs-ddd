"""Query base class — immutable request for data."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Generic

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import TypeVar

if TYPE_CHECKING:
    from ..primitives.locking import ResourceIdentifier

TResult = TypeVar("TResult", default=None)


class Query(BaseModel, Generic[TResult]):
    """Base class for all Queries.

    Queries represent a request for data and **must** be immutable.
    Each query carries tracing metadata for correlation.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    query_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str | None = None

    def get_critical_resources(self) -> list[ResourceIdentifier]:
        """
        Declare resources that need locking for this query.

        Most queries should NOT need locking. Only override if you need:
        - Read locks (to prevent concurrent writes)
        - Write locks (for query-side effects like counters)

        Returns:
            List of resources to lock. Empty list = no locking (default).

        Example (read lock):
            ```python
            def get_critical_resources(self) -> list[ResourceIdentifier]:
                return [
                    ResourceIdentifier("Report", str(self.report_id), lock_mode="read"),
                ]
            ```
        """
        return []
