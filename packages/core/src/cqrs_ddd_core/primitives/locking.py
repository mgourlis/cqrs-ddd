"""Multi-resource locking primitives for concurrency control."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ResourceIdentifier:
    """
    Identifies a single lockable resource.

    Examples:
        >>> ResourceIdentifier("User", "123")
        >>> ResourceIdentifier("Account", str(uuid4()))
        >>> ResourceIdentifier("global", "api_rate_limit")
    """

    resource_type: str
    resource_id: str  # Always store as string for consistent sorting
    lock_mode: Literal["read", "write"] = "write"

    def __lt__(self, other: ResourceIdentifier) -> bool:
        """
        Enable sorting for deterministic lock acquisition (prevents deadlocks).

        We sort by (resource_type, resource_id) as strings to ensure
        all resource IDs are comparable, regardless of underlying type.
        """
        # Use tuple comparison - both are strings so always sortable
        return (self.resource_type, self.resource_id) < (
            other.resource_type,
            other.resource_id,
        )

    def __hash__(self) -> int:
        """Make hashable for use in sets."""
        return hash((self.resource_type, self.resource_id, self.lock_mode))

    def __str__(self) -> str:
        mode = f":{self.lock_mode}" if self.lock_mode != "write" else ""
        return f"{self.resource_type}:{self.resource_id}{mode}"
