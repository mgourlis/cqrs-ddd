"""
In-memory operator implementations.

Provides concrete MemoryOperator subclasses for each SpecificationOperator
and a factory function to create registries.

Usage::

    from cqrs_ddd_specifications.operators_memory import build_default_registry

    registry = build_default_registry()
    result = registry.evaluate(SpecificationOperator.EQ, actual, expected)
"""

from __future__ import annotations

from ..evaluator import MemoryOperatorRegistry
from .fts import (
    FtsOperator,
    FtsPhraseOperator,
)
from .geometry import (
    BboxIntersectsOperator,
    ContainsGeomOperator,
    CrossesOperator,
    DisjointOperator,
    DistanceLtOperator,
    DWithinOperator,
    GeomEqualsOperator,
    IntersectsOperator,
    OverlapsOperator,
    TouchesOperator,
    WithinOperator,
)
from .jsonb import (
    JsonContainedByOperator,
    JsonContainsOperator,
    JsonHasAllOperator,
    JsonHasAnyOperator,
    JsonHasKeyOperator,
    JsonPathExistsOperator,
)
from .null import (
    IsEmptyOperator,
    IsNotEmptyOperator,
    IsNotNullOperator,
    IsNullOperator,
)
from .set import (
    AllOperator,
    BetweenOperator,
    InOperator,
    NotBetweenOperator,
    NotInOperator,
)
from .standard import (
    EqualOperator,
    GreaterEqualOperator,
    GreaterThanOperator,
    LessEqualOperator,
    LessThanOperator,
    NotEqualOperator,
)
from .string import (
    ContainsOperator,
    EndsWithOperator,
    IContainsOperator,
    IEndsWithOperator,
    ILikeOperator,
    IRegexOperator,
    IStartsWithOperator,
    LikeOperator,
    NotLikeOperator,
    RegexOperator,
    StartsWithOperator,
)


def build_default_registry() -> MemoryOperatorRegistry:
    """
    Create a registry with all built-in operators.
    
    This factory function creates a fresh MemoryOperatorRegistry instance
    populated with all built-in operators. Use this to create registries
    for dependency injection.
    
    Returns:
        MemoryOperatorRegistry: A new registry instance with all operators.
    
    Example:
        >>> registry = build_default_registry()
        >>> registry.evaluate(SpecificationOperator.EQ, "active", "active")
        True
    """
    registry = MemoryOperatorRegistry()
    registry.register_all(
        # Standard comparison
        EqualOperator(),
        NotEqualOperator(),
        GreaterThanOperator(),
        LessThanOperator(),
        GreaterEqualOperator(),
        LessEqualOperator(),
        # Set
        InOperator(),
        NotInOperator(),
        AllOperator(),
        BetweenOperator(),
        NotBetweenOperator(),
        # String
        LikeOperator(),
        NotLikeOperator(),
        ILikeOperator(),
        ContainsOperator(),
        IContainsOperator(),
        StartsWithOperator(),
        IStartsWithOperator(),
        EndsWithOperator(),
        IEndsWithOperator(),
        RegexOperator(),
        IRegexOperator(),
        # Null / empty
        IsNullOperator(),
        IsNotNullOperator(),
        IsEmptyOperator(),
        IsNotEmptyOperator(),
        # JSON
        JsonContainsOperator(),
        JsonContainedByOperator(),
        JsonHasKeyOperator(),
        JsonHasAnyOperator(),
        JsonHasAllOperator(),
        JsonPathExistsOperator(),
        # Full-text search
        FtsOperator(),
        FtsPhraseOperator(),
        # Geometry
        IntersectsOperator(),
        WithinOperator(),
        ContainsGeomOperator(),
        TouchesOperator(),
        CrossesOperator(),
        OverlapsOperator(),
        DisjointOperator(),
        GeomEqualsOperator(),
        DWithinOperator(),
        DistanceLtOperator(),
        BboxIntersectsOperator(),
    )
    return registry


__all__ = [
    "build_default_registry",
    "MemoryOperatorRegistry",
]
