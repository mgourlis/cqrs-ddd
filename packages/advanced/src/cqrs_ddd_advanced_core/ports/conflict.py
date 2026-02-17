"""Conflict Resolution Policies — strategies for merging concurrent edits."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IMergeStrategy(ABC):
    """Abstract base class for merge strategies."""

    @abstractmethod
    def merge(self, existing: Any, incoming: Any) -> Any:
        """Merge two conflicting versions of data.

        Args:
            existing: The persisted (current) version.
            incoming: The new version attempting to be saved.

        Returns:
            Merged data.
        """
        ...
