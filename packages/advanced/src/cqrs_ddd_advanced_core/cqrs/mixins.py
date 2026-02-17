from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from cqrs_ddd_advanced_core.conflict.resolution import ConflictResolutionPolicy


class RetryPolicy(BaseModel, ABC):
    """Base class for retry policies."""

    max_retries: int = 3
    jitter: bool = True

    @abstractmethod
    def calculate_delay(self, attempt: int) -> int:
        """Return delay in milliseconds for the given attempt."""
        ...


class FixedRetryPolicy(RetryPolicy):
    """Retries with a fixed delay between attempts."""

    delay_ms: int = 100

    def calculate_delay(self, _attempt: int) -> int:
        return self.delay_ms


class ExponentialBackoffPolicy(RetryPolicy):
    """Retries with increasing delay (exponential backoff)."""

    initial_delay_ms: int = 100
    multiplier: float = 2.0
    max_delay_ms: int = 5000

    def calculate_delay(self, attempt: int) -> int:
        delay = self.initial_delay_ms * (self.multiplier**attempt)
        return min(int(delay), self.max_delay_ms)


class ConflictConfig(BaseModel):
    """Configuration for conflict resolution."""

    policy: ConflictResolutionPolicy = ConflictResolutionPolicy.FIRST_WINS

    # Explicit strategy name (e.g. "deep", "field", "timestamp")
    # If provided, this overrides the inferred strategy from policy.
    strategy_name: str | None = None

    # Path to custom resolver class or function if policy is CUSTOM
    resolver_path: str | None = None

    # Configuration for built-in merge strategies
    ignore_conflicts: bool = False  # For FieldLevelMerge
    include_fields: set[str] | None = None  # For FieldLevelMerge
    exclude_fields: set[str] | None = None  # For FieldLevelMerge

    append_lists: bool = False  # For DeepMerge
    list_identity_key: str | Callable[[Any], Any] | None = (
        "id"  # For DeepMerge / UnionListMerge
    )

    timestamp_field: str | Callable[[Any], Any] = "modified_at"  # For TimestampLastWins
    fallback_to_incoming: bool = True  # For TimestampLastWins

    # Generic extensibility for custom strategies
    strategy_kwargs: dict[str, Any] = Field(default_factory=dict)


class Retryable(BaseModel):
    """Mixin for commands that should be retried on failure."""

    retry_policy: RetryPolicy = Field(default_factory=ExponentialBackoffPolicy)


class ConflictResilient(BaseModel):
    """Mixin for commands that support conflict resolution."""

    conflict_config: ConflictConfig = Field(default_factory=ConflictConfig)
