"""Access-control models — value objects, configs, and result types.

All frozen dataclasses or Pydantic models. These are the data structures
used across the access-control package — ports, middleware, evaluators.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from cqrs_ddd_specifications import BaseSpecification


# ---------------------------------------------------------------------------
# Authorization context & decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthorizationContext:
    """Describes what is being authorized."""

    resource_type: str
    action: str
    resource_ids: list[str] | None = None
    resource_attributes: dict[str, Any] = field(default_factory=dict)
    auth_context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AuthorizationDecision:
    """Outcome of a single evaluator check."""

    allowed: bool
    reason: str
    evaluator: str  # which evaluator produced this


# ---------------------------------------------------------------------------
# Batch check types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckAccessItem:
    """Single item for ``check_access_batch``."""

    resource_type: str
    action: str
    resource_ids: list[str] | None = None


@dataclass(frozen=True)
class GetPermittedActionsItem:
    """Single item for ``get_permitted_actions_batch``."""

    resource_type: str
    resource_ids: list[str] | None = None


@dataclass
class CheckAccessBatchResult:
    """Batch authorization result with per-resource+action access map."""

    access_map: dict[tuple[str | None, str], set[str]] = field(default_factory=dict)
    global_permissions: set[str] = field(default_factory=set)

    def is_allowed(
        self,
        resource_type: str,
        resource_id: str,
        actions: set[str],
        action_quantifier: Literal["all", "any"] = "all",
    ) -> bool:
        """Check if access is allowed, merging resource-specific and global."""
        resource_actions = (
            self.access_map.get((resource_type, resource_id), set())
            | self.global_permissions
        )
        if action_quantifier == "all":
            return actions <= resource_actions
        return bool(actions & resource_actions)


# ---------------------------------------------------------------------------
# Authorization conditions & filter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthorizationConditionsResult:
    """Raw authorization conditions from the engine."""

    filter_type: Literal["granted_all", "denied_all", "conditions"]
    conditions_dsl: dict[str, Any] | None = None
    has_context_refs: bool = False

    @property
    def granted_all(self) -> bool:
        return self.filter_type == "granted_all"

    @property
    def denied_all(self) -> bool:
        return self.filter_type == "denied_all"

    @property
    def has_conditions(self) -> bool:
        """True if authorization requires condition-based filtering."""
        return self.filter_type == "conditions" and self.conditions_dsl is not None


@dataclass(frozen=True)
class AuthorizationFilter:
    """Specification-based authorization filter ready for query merging."""

    granted_all: bool = False
    denied_all: bool = False
    filter_specification: BaseSpecification | None = None  # type: ignore[type-arg]
    has_context_refs: bool = False

    @property
    def has_filter(self) -> bool:
        return (
            self.filter_specification is not None
            and not self.granted_all
            and not self.denied_all
        )

    def __bool__(self) -> bool:
        """True if access is possible (granted_all or has filter)."""
        return self.granted_all or self.has_filter

    @classmethod
    def grant_all(cls) -> AuthorizationFilter:
        return cls(granted_all=True)

    @classmethod
    def deny_all(cls) -> AuthorizationFilter:
        return cls(denied_all=True)

    @classmethod
    def from_specification(cls, spec: BaseSpecification) -> AuthorizationFilter:  # type: ignore[type-arg]
        return cls(filter_specification=spec)


# ---------------------------------------------------------------------------
# Access rule
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccessRule:
    """A single permission grant, with optional conditions."""

    principal_name: str | None = None
    role_name: str | None = None
    action: str = ""
    resource_id: str | None = None
    conditions: dict[str, Any] | None = None
    specification_dsl: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Field mapping
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldMapping:
    """Maps between app entity field names and authorization engine attrs.

    The reverse mapping (engine→app) is computed at runtime.
    """

    mappings: dict[str, str] = field(default_factory=dict)
    external_id_field: str = "external_id"
    external_id_cast: Callable[[Any], Any] = str

    def get_field(self, abac_attr: str) -> str:
        """Get app field name for an ABAC attribute."""
        reverse = {v: k for k, v in self.mappings.items()}
        return reverse.get(abac_attr, abac_attr)

    def get_abac_attr(self, app_field: str) -> str:
        """Get ABAC attribute name for an app field."""
        return self.mappings.get(app_field, app_field)

    def cast_external_id(self, val: Any) -> Any:
        """Cast external_id value(s) using the configured cast function."""
        if isinstance(val, list):
            return [self.external_id_cast(v) for v in val]
        return self.external_id_cast(val)


# ---------------------------------------------------------------------------
# Resource type config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResourceTypeConfig:
    """Registration metadata for an authorizable resource type."""

    name: str
    field_mapping: FieldMapping
    is_public: bool = False
    auto_register_resources: bool = True
    entity_class: type | None = None
    actions: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Middleware configs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthorizationConfig:
    """Configuration for ``AuthorizationMiddleware``."""

    resource_type: str | None = None
    resource_type_attr: str | None = None
    required_actions: list[str] = field(default_factory=list)
    action_quantifier: Literal["all", "any"] = "all"
    list_quantifier: Literal["all", "any"] = "all"
    resource_id_attr: str | None = None
    query_options_attr: str | None = None
    result_entities_attr: str | None = None
    entity_id_attr: str = "id"
    fail_silently: bool = False
    deny_anonymous: bool = False
    auth_context_provider: Callable[[Any], dict[str, Any] | None] | None = None


@dataclass(frozen=True)
class SpecificationAuthConfig:
    """Configuration for ``SpecificationAuthMiddleware``."""

    resource_type: str = ""
    action: str = "read"
    query_options_attr: str = "query_options"
    auth_context_provider: Callable[[Any], dict[str, Any] | None] | None = None


@dataclass(frozen=True)
class PermittedActionsConfig:
    """Configuration for ``PermittedActionsMiddleware``."""

    resource_type: str = ""
    result_entities_attr: str = "items"
    entity_id_attr: str = "id"
    permitted_actions_attr: str = "permitted_actions"
    include_type_level: bool = False
    auth_context_provider: Callable[[Any], dict[str, Any] | None] | None = None


# ---------------------------------------------------------------------------
# Bypass roles helper
# ---------------------------------------------------------------------------


def _resolve_bypass_roles(
    bypass_roles: frozenset[str] | None = None,
) -> frozenset[str]:
    """Resolve bypass roles from constructor param or ``AUTH_BYPASS_ROLES`` env."""
    if bypass_roles is not None:
        return bypass_roles
    env = os.environ.get("AUTH_BYPASS_ROLES", "")
    if env:
        return frozenset(r.strip() for r in env.split(",") if r.strip())
    return frozenset()
