"""Conflict Resolution Policies — strategies for merging concurrent edits."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, TypeVar

from cqrs_ddd_core.correlation import get_correlation_id
from cqrs_ddd_core.instrumentation import fire_and_forget_hook, get_hook_registry

from ..ports.conflict import IMergeStrategy

if TYPE_CHECKING:
    from collections.abc import Callable

T = TypeVar("T")


class MergeStrategyRegistry:
    """Registry for looking up merge strategies by name."""

    def __init__(self) -> None:
        self._strategies: dict[str, type[IMergeStrategy]] = {}

    def register(self, name: str, strategy_cls: type[IMergeStrategy]) -> None:
        """Register a merge strategy class."""
        self._strategies[name.lower()] = strategy_cls

    def get(self, name: str) -> type[IMergeStrategy] | None:
        """Get a strategy class by name."""
        return self._strategies.get(name.lower())

    def create(self, name: str, **kwargs: Any) -> IMergeStrategy | None:
        """Create an instance of a registered strategy."""
        strategy_cls = self.get(name)
        if strategy_cls:
            return strategy_cls(**kwargs)
        return None

    @staticmethod
    def get_stock_registry() -> MergeStrategyRegistry:
        """Get a registry pre-filled with the standard strategies."""
        registry = MergeStrategyRegistry()
        registry.register("last_wins", LastWinsStrategy)
        registry.register("field", FieldLevelMergeStrategy)
        registry.register("deep", DeepMergeStrategy)
        registry.register("timestamp", TimestampLastWinsStrategy)
        registry.register("union", UnionListMergeStrategy)
        return registry


class ConflictResolutionPolicy(str, Enum):
    """Policies for resolving conflicts when concurrent edits occur.

    When two aggregates (or commands) try to modify the same entity:
    - **FIRST_WINS**: The first update succeeds; second is rejected.
    - **LAST_WINS**: The most recent update overwrites previous.
    - **MERGE**: Attempt smart merge (field-level reconciliation).
    - **CUSTOM**: User-supplied callback decides the merge.
    """

    FIRST_WINS = "FIRST_WINS"
    LAST_WINS = "LAST_WINS"
    MERGE = "MERGE"
    CUSTOM = "CUSTOM"


# Merge strategies


class LastWinsStrategy(IMergeStrategy):
    """Simple strategy where the incoming change always wins."""

    def merge(self, _existing: Any, incoming: Any) -> Any:
        return incoming


class FieldLevelMergeStrategy(IMergeStrategy):
    """
    Merges dictionaries at the top level.

    If a key exists in both, incoming value overwrites existing unless
    'ignore_conflicts' is set to True (then existing wins).
    """

    def __init__(
        self,
        *,
        ignore_conflicts: bool = False,
        include_fields: set[str] | None = None,
        exclude_fields: set[str] | None = None,
    ) -> None:
        self.ignore_conflicts = ignore_conflicts
        self.include_fields = include_fields
        self.exclude_fields = exclude_fields

    def merge(
        self, existing: dict[str, Any], incoming: dict[str, Any]
    ) -> dict[str, Any]:
        merged = dict(existing)
        for key, value in incoming.items():
            if self.include_fields and key not in self.include_fields:
                continue
            if self.exclude_fields and key in self.exclude_fields:
                continue

            if key in merged and self.ignore_conflicts:
                continue
            merged[key] = value
        return merged


class DeepMergeStrategy(IMergeStrategy):
    """
    Recursively merges dictionaries.

    - Dicts are merged recursively.
    - Lists are replaced by default, or appended if 'append_lists' is True.
    - Primitives are overwritten by incoming.
    """

    def __init__(
        self,
        *,
        append_lists: bool = False,
        list_identity_key: str | Callable[[Any], Any] | None = "id",
    ) -> None:
        self.append_lists = append_lists
        self.list_identity_key = list_identity_key

    def merge(self, existing: Any, incoming: Any) -> Any:
        # Handle Pydantic models by converting to dict
        e_val = existing.model_dump() if hasattr(existing, "model_dump") else existing
        i_val = incoming.model_dump() if hasattr(incoming, "model_dump") else incoming

        if isinstance(e_val, dict) and isinstance(i_val, dict):
            return self._merge_dicts(e_val, i_val)

        if isinstance(e_val, list) and isinstance(i_val, list):
            return self._merge_lists(e_val, i_val)

        return incoming

    def _merge_dicts(self, d1: dict[str, Any], d2: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(d1)
        for k, v in d2.items():
            if k in result:
                result[k] = self.merge(result[k], v)
            else:
                result[k] = v
        return result

    def _merge_lists(self, l1: list[Any], l2: list[Any]) -> list[Any]:
        if not self.list_identity_key:
            return l1 + l2 if self.append_lists else l2

        # Merge by identity key
        result_map = {self._get_identity(item): item for item in l1}
        for item in l2:
            identity = self._get_identity(item)
            if identity in result_map:
                result_map[identity] = self.merge(result_map[identity], item)
            else:
                result_map[identity] = item

        return list(result_map.values())

    def _get_identity(self, item: Any) -> Any:
        if callable(self.list_identity_key):
            return self.list_identity_key(item)

        if isinstance(item, dict):
            return (
                item.get(self.list_identity_key) or id(item)
                if self.list_identity_key
                else id(item)
            )

        # FIX: Use local variable to help mypy narrow the type
        key = self.list_identity_key
        if isinstance(key, str) and hasattr(item, key):
            return getattr(item, key)
        return id(item)


class TimestampLastWinsStrategy(IMergeStrategy):
    """
    Wins based on a timestamp field (e.g., 'modified_at').
    Requires both objects to have this field.
    """

    def __init__(
        self,
        timestamp_field: str | Callable[[Any], datetime | None] = "modified_at",
        *,
        fallback_to_incoming: bool = False,
    ) -> None:
        self.timestamp_field = timestamp_field
        self.fallback_to_incoming = fallback_to_incoming

    def merge(self, existing: Any, incoming: Any) -> Any:
        e_ts = self._extract_timestamp(existing)
        i_ts = self._extract_timestamp(incoming)

        if e_ts is None or i_ts is None:
            return incoming if self.fallback_to_incoming else existing

        if i_ts >= e_ts:
            return incoming

        return existing

    def _extract_timestamp(self, obj: Any) -> datetime | None:
        if callable(self.timestamp_field):
            return self._parse_timestamp(self.timestamp_field(obj))

        # Convert to dict for easier access if they are Pydantic models
        d = obj.model_dump() if hasattr(obj, "model_dump") else obj
        if not isinstance(d, dict):
            return None

        return self._parse_timestamp(d.get(self.timestamp_field))

    def _parse_timestamp(self, value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                # Handle ISO format with Z or +00:00
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None


class UnionListMergeStrategy(IMergeStrategy):
    """
    Merges lists by taking the set union (deduplicating items).
    For non-list fields, it acts like Last Wins.
    """

    def __init__(self, identity_key: str | Callable[[Any], Any] | None = "id") -> None:
        self.identity_key = identity_key

    def merge(self, existing: Any, incoming: Any) -> Any:
        if isinstance(existing, list) and isinstance(incoming, list):
            if not self.identity_key:
                # Strict set union for hashable items
                try:
                    return list(dict.fromkeys(existing + incoming))
                except TypeError:
                    return existing + [x for x in incoming if x not in existing]

            # Identity-based union
            result_map = {self._get_identity(x): x for x in existing}
            for item in incoming:
                identity = self._get_identity(item)
                result_map[identity] = item  # Incoming wins for same identity

            return list(result_map.values())

        return incoming

    def _get_identity(self, item: Any) -> Any:
        if callable(self.identity_key):
            return self.identity_key(item)

        if isinstance(item, dict):
            return (
                item.get(self.identity_key) or id(item)
                if self.identity_key
                else id(item)
            )

        # FIX: Use local variable to help mypy narrow the type
        key = self.identity_key
        if isinstance(key, str) and hasattr(item, key):
            return getattr(item, key)
        return id(item)


class ConflictResolver:
    """
    Base resolver that uses a configurable strategy.

    Can be initialized with a specific strategy instance.
    """

    def __init__(self, strategy: IMergeStrategy | None = None) -> None:
        if strategy is None:
            strategy = LastWinsStrategy()
        self.strategy = strategy

    def merge(self, existing: Any, incoming: Any) -> Any:
        result = self.strategy.merge(existing, incoming)
        registry = get_hook_registry()
        strategy_name = type(self.strategy).__name__
        attrs = {
            "strategy.type": strategy_name,
            "correlation_id": get_correlation_id(),
        }
        fire_and_forget_hook(registry, f"conflict.resolve.{strategy_name}", attrs)
        fire_and_forget_hook(registry, f"merge_strategy.apply.{strategy_name}", attrs)
        return result


# Helper for backward compatibility or simple function calls
def field_level_merge(
    existing: dict[str, Any], incoming: dict[str, Any]
) -> dict[str, Any]:
    return FieldLevelMergeStrategy(ignore_conflicts=False).merge(existing, incoming)
