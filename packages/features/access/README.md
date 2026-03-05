# cqrs-ddd-access-control

Authorization layer for CQRS-DDD applications — RBAC, ABAC, ACL, ownership, single-query auth, and undo support.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Ports (Protocols)](#ports-protocols)
  - [IAuthorizationPort](#iauthorizationport)
  - [IAuthorizationAdminPort](#iauthorizationadminport)
  - [IOwnershipResolver](#iownershipresolver)
  - [IPermissionCache](#ipermissioncache)
  - [IResourceTypeRegistry](#iresourcetyperegistry)
- [Evaluators](#evaluators)
  - [IPermissionEvaluator Protocol](#ipermissionevaluator-protocol)
  - [RBACEvaluator](#rbacevaluator)
  - [ACLEvaluator](#aclevaluator)
  - [OwnershipEvaluator](#ownershipevaluator)
  - [ABACConnector](#abacconnector)
  - [Custom Evaluators](#custom-evaluators)
- [Policy Enforcement Point (PEP)](#policy-enforcement-point-pep)
- [Commands & Events](#commands--events)
  - [Commands](#commands)
  - [Events](#events)
  - [Event Flow](#event-flow)
- [Middleware](#middleware)
  - [AuthorizationMiddleware](#authorizationmiddleware)
  - [SpecificationAuthMiddleware](#specificationauthmiddleware)
  - [PermittedActionsMiddleware](#permittedactionsmiddleware)
  - [DecoratorAuthorizationMiddleware](#decoratorauthorizationmiddleware)
  - [Middleware Chaining](#middleware-chaining)
- [Decorators](#decorators)
  - [@requires_permission](#requires_permission)
  - [@requires_role](#requires_role)
  - [@requires_owner](#requires_owner)
  - [@authorization](#authorization)
  - [Qualifier Semantics](#qualifier-semantics)
  - [Combining Decorators](#combining-decorators)
- [Authorizable Entities](#authorizable-entities)
- [Resource Synchronization](#resource-synchronization)
- [Permission Caching](#permission-caching)
- [Elevation (Step-Up Authentication)](#elevation-step-up-authentication)
  - [verify_elevation()](#verify_elevation)
  - [Step-Up Flow Overview](#step-up-flow-overview)
  - [Step-Up Commands](#step-up-commands)
  - [Step-Up Events](#step-up-events)
  - [Step-Up Handlers](#step-up-handlers)
  - [StepUpAuthenticationSaga](#stepupauthenticationsaga)
  - [serialize_command Utility](#serialize_command-utility)
  - [End-to-End Example](#end-to-end-example)
- [Undo / Redo](#undo--redo)
- [Multi-Tenant Isolation](#multi-tenant-isolation)
- [Bypass Roles](#bypass-roles)
- [Exceptions](#exceptions)
- [Contrib: Stateful-ABAC Adapter](#contrib-stateful-abac-adapter)
  - [Client Configuration](#client-configuration)
  - [Runtime Adapter](#runtime-adapter)
  - [Admin Adapter](#admin-adapter)
  - [ConditionConverter](#conditionconverter)
- [Configuration Reference](#configuration-reference)
- [Testing](#testing)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                       Presentation Layer                        │
│                    (FastAPI, CLI, GraphQL)                       │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                     Middleware Pipeline                          │
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐ ┌────────────────┐ │
│  │ Authorization     │  │ Specification    │ │ Permitted      │ │
│  │ Middleware        │  │ AuthMiddleware   │ │ Actions MW     │ │
│  └──────────────────┘  └──────────────────┘ └────────────────┘ │
│  ┌──────────────────┐                                           │
│  │ Decorator         │                                          │
│  │ AuthMiddleware    │                                          │
│  └──────────────────┘                                           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                     Application Layer                           │
│                                                                 │
│  ┌─────────┐  ┌──────────┐  ┌────────────────────────────────┐ │
│  │Commands  │  │Handlers  │  │Priority Event Handlers         │ │
│  │(Grant,   │  │(emit     │  │(persist ACLs inside same UoW, │ │
│  │ Revoke,  │  │ request  │  │ enforce tenant isolation)      │ │
│  │ SetPub)  │  │ events)  │  │                                │ │
│  └─────────┘  └──────────┘  └────────────────────────────────┘ │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ PolicyEnforcementPoint (PEP)                               │ │
│  │  ┌────────┐ ┌────────┐ ┌───────────┐ ┌──────────────────┐ │ │
│  │  │ RBAC   │ │ ACL    │ │ Ownership │ │ ABACConnector    │ │ │
│  │  │Evaluator│ │Evaluator│ │ Evaluator │ │ (external ABAC) │ │ │
│  │  └────────┘ └────────┘ └───────────┘ └──────────────────┘ │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                     Ports (Protocols)                            │
│                                                                 │
│  IAuthorizationPort   IAuthorizationAdminPort                   │
│  IOwnershipResolver   IPermissionCache   IResourceTypeRegistry  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                     Infrastructure                              │
│                                                                 │
│  ┌───────────────────┐ ┌────────────────┐ ┌──────────────────┐ │
│  │Stateful-ABAC      │ │Redis Cache     │ │Custom Adapters   │ │
│  │Adapter            │ │Adapter         │ │(OPA, Casbin)     │ │
│  └───────────────────┘ └────────────────┘ └──────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

**Key principles:**

- **Port-driven design** — all authorization communication goes through `@runtime_checkable` Protocol ports. Swap backends (stateful-abac, OPA, Casbin, in-memory stubs) without changing application code.
- **Deny-wins composition** — evaluators are composed by the PEP. An explicit deny from *any* evaluator overrides all allows. Abstain means "no opinion."
- **Same-transaction consistency** — ACL commands emit request events; priority event handlers persist them inside the same Unit of Work, guaranteeing atomicity.
- **Single-query authorization** — `SpecificationAuthMiddleware` merges authorization conditions into `QueryOptions.specification` so the database enforces access control in one SQL statement.
- **Undo/redo** — all ACL operations record `previous_state`, enabling full undo/redo through `cqrs-ddd-advanced-core`.

---

## Installation

```bash
pip install cqrs-ddd-access-control
```

### Optional dependencies

```bash
# Single-query auth via specifications
pip install cqrs-ddd-access-control[specifications]

# Undo/redo support
pip install cqrs-ddd-access-control[advanced]

# Redis-backed permission cache
pip install cqrs-ddd-access-control[redis]

# Stateful-ABAC policy engine
pip install cqrs-ddd-access-control[stateful-abac]

# All optional dependencies
pip install cqrs-ddd-access-control[all]
```

---

## Quick Start

### 1. Define an authorizable entity

```python
from cqrs_ddd_access_control import register_access_entity, FieldMapping

@register_access_entity(
    resource_type="order",
    field_mapping=FieldMapping(
        mappings={"status": "order_status", "region": "region"},
        external_id_field="id",
        external_id_cast=str,
    ),
    actions=["read", "update", "delete", "approve"],
    is_public=False,
)
class Order:
    id: str
    status: str
    region: str
    owner_id: str
```

### 2. Set up the PEP with evaluators

```python
from cqrs_ddd_access_control import (
    PolicyEnforcementPoint,
    RBACEvaluator,
    ACLEvaluator,
    OwnershipEvaluator,
)

rbac = RBACEvaluator(
    role_permissions={
        "admin": {"order:read", "order:update", "order:delete", "order:approve"},
        "editor": {"order:read", "order:update"},
        "viewer": {"order:read"},
    },
    role_hierarchy={"admin": {"editor"}, "editor": {"viewer"}},
)
acl = ACLEvaluator(authorization_port=my_auth_port)
ownership = OwnershipEvaluator(
    ownership_resolver=my_resolver,
    owner_actions={"read", "update"},
)

pep = PolicyEnforcementPoint(
    evaluators=[rbac, acl, ownership],
    cache=my_cache,              # optional
    bypass_roles=frozenset({"superadmin"}),
)
```

### 3. Wire middleware into the CQRS pipeline

```python
from cqrs_ddd_access_control import (
    AuthorizationMiddleware,
    AuthorizationConfig,
    SpecificationAuthMiddleware,
    SpecificationAuthConfig,
    PermittedActionsMiddleware,
    PermittedActionsConfig,
    ResourceTypeRegistry,
)

# Pre-check + post-filter middleware
auth_mw = AuthorizationMiddleware(
    authorization_port=my_auth_port,
    config=AuthorizationConfig(
        resource_type="order",
        required_actions=["read"],
        resource_id_attr="order_id",
        result_entities_attr="items",
        entity_id_attr="id",
    ),
)

# Single-query auth middleware
registry = ResourceTypeRegistry()
spec_mw = SpecificationAuthMiddleware(
    authorization_port=my_auth_port,
    config=SpecificationAuthConfig(resource_type="order", action="read"),
    resource_type_registry=registry,
)

# Enrichment middleware
pa_mw = PermittedActionsMiddleware(
    authorization_port=my_auth_port,
    config=PermittedActionsConfig(
        resource_type="order",
        result_entities_attr="items",
        entity_id_attr="id",
        permitted_actions_attr="permitted_actions",
        include_type_level=True,
    ),
)
```

### 4. Register ACL command handlers

```python
from cqrs_ddd_access_control import register_priority_acl_handlers

# Registers ACLGrantRequestedHandler, ACLRevokeRequestedHandler,
# ResourceTypePublicSetHandler as priority event handlers
register_priority_acl_handlers(
    event_handler_registry=event_registry,
    admin_port=my_admin_port,
)
```

### 5. Grant and revoke ACLs through commands

```python
from cqrs_ddd_access_control import GrantACL, RevokeACL

# Grant read access on orders to role "analyst"
grant = GrantACL(
    resource_type="order",
    action="read",
    role_name="analyst",
    conditions={"region": {"op": "eq", "val": "EU"}},
)
response = await mediator.send(grant)

# Revoke
revoke = RevokeACL(
    resource_type="order",
    action="read",
    role_name="analyst",
)
response = await mediator.send(revoke)
```

---

## Ports (Protocols)

All ports are `@runtime_checkable` Protocol classes defined in `ports.py`. Adapters **must** explicitly declare the protocol they implement.

### IAuthorizationPort

The primary runtime authorization interface. Called by middleware, evaluators, and the elevation helper.

```python
@runtime_checkable
class IAuthorizationPort(Protocol):

    async def check_access(
        self,
        access_token: str | None,
        resource_type: str,
        action: str,
        resource_ids: list[str] | None = None,
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> list[str]:
        """Return list of authorized resource IDs for the given action.

        When resource_ids is None, performs a type-level check — returns
        a non-empty list if the action is allowed at the type level.
        """
        ...

    async def check_access_batch(
        self,
        access_token: str | None,
        items: list[CheckAccessItem],
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> CheckAccessBatchResult:
        """Batch check: multiple resource-types/actions in one round-trip."""
        ...

    async def get_permitted_actions(
        self,
        access_token: str | None,
        resource_type: str,
        resource_ids: list[str] | None = None,
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> dict[str, list[str]]:
        """Return which actions are permitted per resource ID.

        Response: {"resource-id-1": ["read", "update"], ...}
        """
        ...

    async def get_permitted_actions_batch(
        self,
        access_token: str | None,
        items: list[GetPermittedActionsItem],
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> dict[str, dict[str, list[str]]]:
        """Batch: multiple resource types in one call.

        Response: {"orders": {"id1": ["read"], ...}, "docs": {...}}
        """
        ...

    async def get_type_level_permissions(
        self,
        access_token: str | None,
        resource_types: list[str],
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> dict[str, list[str]]:
        """Per-resource-type action lists (no specific resource IDs).

        Response: {"order": ["read", "create"], "document": ["read"]}
        """
        ...

    async def get_authorization_conditions(
        self,
        access_token: str | None,
        resource_type: str,
        action: str,
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> AuthorizationConditionsResult:
        """Return authorization conditions as DSL for single-query auth.

        Returns one of:
        - filter_type="granted_all" — no filtering needed
        - filter_type="denied_all"  — reject immediately
        - filter_type="conditions"  — conditions_dsl contains the DSL tree
        """
        ...

    async def get_authorization_filter(
        self,
        access_token: str | None,
        resource_type: str,
        action: str,
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
        field_mapping: FieldMapping | None = None,
    ) -> AuthorizationFilter:
        """Conditions → specification-based filter for single-query auth.

        When field_mapping is provided, converts the raw DSL into a
        BaseSpecification with mapped field names.
        """
        ...

    async def list_resource_types(self) -> list[str]: ...
    async def list_actions(self, resource_type: str) -> list[str]: ...
```

**Implementation notes:** `check_access` returns `list[str]` (authorized resource IDs), not `bool`. For type-level checks (no specific IDs), a non-empty list signals "allowed." The `auth_context` parameter passes request-scoped attributes (e.g., IP address, time of day) for ABAC evaluation. `role_names` enables injecting roles from the identity layer for backends that need explicit role info.

### IAuthorizationAdminPort

Administrative CRUD for managing the authorization engine — resource types, actions, resources, ACLs, principals, roles, and realm provisioning.

```python
@runtime_checkable
class IAuthorizationAdminPort(Protocol):

    # Resource type lifecycle
    async def create_resource_type(self, name: str, *, is_public: bool = False) -> dict[str, Any]: ...
    async def list_resource_types(self) -> list[dict[str, Any]]: ...
    async def delete_resource_type(self, name: str) -> dict[str, Any]: ...
    async def set_resource_type_public(self, name: str, is_public: bool) -> dict[str, Any]: ...

    # Action lifecycle
    async def create_action(self, name: str) -> dict[str, Any]: ...
    async def list_actions(self) -> list[dict[str, Any]]: ...
    async def delete_action(self, name: str) -> dict[str, Any]: ...

    # Resource registration
    async def register_resource(
        self, resource_type: str, resource_id: str,
        attributes: dict[str, Any] | None = None,
        geometry: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...
    async def sync_resources(self, resource_type: str, resources: list[dict[str, Any]]) -> dict[str, Any]: ...
    async def delete_resource(self, resource_type: str, resource_id: str) -> dict[str, Any]: ...

    # ACL CRUD
    async def create_acl(
        self, resource_type: str | None = None, action: str | None = None, *,
        principal_name: str | None = None, role_name: str | None = None,
        resource_external_id: str | None = None, conditions: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    async def create_acl_from_specification(
        self, resource_type: str, action: str, *,
        principal_name: str | None = None, role_name: str | None = None,
        resource_external_id: str | None = None,
        specification_dsl: dict[str, Any], field_mapping: FieldMapping | None = None,
    ) -> dict[str, Any]: ...

    async def list_acls(...) -> list[dict[str, Any]]: ...
    async def delete_acl(self, acl_id: int | str) -> dict[str, Any]: ...
    async def delete_acl_by_key(...) -> dict[str, Any]: ...

    # Principal/Role listing
    async def list_principals(self) -> list[dict[str, Any]]: ...
    async def list_roles(self) -> list[dict[str, Any]]: ...

    # Realm provisioning
    async def ensure_realm(self, idp_config: dict[str, Any] | None = None) -> dict[str, Any]: ...
    async def sync_realm(self) -> dict[str, Any]: ...
```

**Key method: `create_acl_from_specification`** — accepts a specification DSL dict and optional `FieldMapping` to translate app field names into ABAC attribute names before creating the ACL. This bridges the gap between the `cqrs-ddd-specifications` pattern and the authorization engine.

**Realm methods:** `ensure_realm()` provisions the realm (along with the `"elevation"` resource type and `"admin"` action). `sync_realm()` synchronizes realm state with the identity provider.

### IOwnershipResolver

Application-implemented resolver for resource ownership.

```python
@runtime_checkable
class IOwnershipResolver(Protocol):

    async def get_owner(
        self,
        resource_type: str,
        resource_id: str,
    ) -> str | list[str] | None:
        """Return owner user_id(s) for a resource, or None if unknown.

        Returning a list supports co-ownership: multiple users who
        all have owner-level access to the resource.
        """
        ...
```

**Example implementation:**

```python
class OrderOwnershipResolver:
    def __init__(self, order_repo: IOrderRepository):
        self._repo = order_repo

    async def get_owner(self, resource_type: str, resource_id: str) -> str | None:
        if resource_type != "order":
            return None
        order = await self._repo.get(resource_id)
        return order.owner_id if order else None
```

### IPermissionCache

Optional TTL-based cache for `AuthorizationDecision` objects. Sits between the PEP and evaluators to avoid redundant ABAC engine calls.

```python
@runtime_checkable
class IPermissionCache(Protocol):

    async def get(
        self,
        principal_id: str,
        resource_type: str,
        resource_id: str | None,
        action: str,
    ) -> AuthorizationDecision | None: ...

    async def set(
        self,
        principal_id: str,
        resource_type: str,
        resource_id: str | None,
        action: str,
        decision: AuthorizationDecision,
        ttl: int | None = None,
    ) -> None: ...

    async def invalidate(
        self, resource_type: str, resource_id: str | None = None
    ) -> None: ...
```

The package provides `PermissionDecisionCache`, a ready-to-use implementation that wraps `ICacheService` from `cqrs-ddd-core`. See [Permission Caching](#permission-caching).

### IResourceTypeRegistry

Registry that resolves `ResourceTypeConfig` by resource type name or entity class.

```python
@runtime_checkable
class IResourceTypeRegistry(Protocol):

    def register(self, config: ResourceTypeConfig) -> None: ...
    def get_config(self, resource_type: str) -> ResourceTypeConfig | None: ...
    def get_config_for_entity(self, entity_cls: type) -> ResourceTypeConfig | None: ...
    def list_types(self) -> list[str]: ...
```

The package provides `ResourceTypeRegistry` as the default implementation. Populate it at startup:

```python
from cqrs_ddd_access_control import ResourceTypeRegistry, get_access_config

registry = ResourceTypeRegistry()

# Auto-discover from decorated entities
for entity_cls in [Order, Document, Project]:
    config = get_access_config(entity_cls)
    if config is not None:
        registry.register(config)
```

---

## Evaluators

Evaluators implement `IPermissionEvaluator` and are composed by the PEP. Each evaluator returns one of three outcomes:

| Outcome | `allowed` | `reason` | Meaning |
|---------|-----------|----------|---------|
| **Allow** | `True` | descriptive | Grants access (can be overridden by a deny) |
| **Deny** | `False` | descriptive (not `"abstain"`) | Denies access (overrides all allows) |
| **Abstain** | `False` | `"abstain"` | No opinion — pass to next evaluator |

### IPermissionEvaluator Protocol

```python
@runtime_checkable
class IPermissionEvaluator(Protocol):
    async def evaluate(
        self,
        principal: Principal,
        context: AuthorizationContext,
    ) -> AuthorizationDecision: ...
```

`AuthorizationContext` carries:

| Field | Type | Description |
|-------|------|-------------|
| `resource_type` | `str` | e.g. `"order"` |
| `action` | `str` | e.g. `"read"`, `"delete"` |
| `resource_ids` | `list[str] \| None` | Specific IDs, or `None` for type-level |
| `resource_attributes` | `dict[str, Any]` | Entity attributes for ABAC evaluation |
| `auth_context` | `dict[str, Any]` | Request-scoped context (IP, time, etc.) |

### RBACEvaluator

Role-based access control with configurable permission mappings and optional role hierarchy.

```python
rbac = RBACEvaluator(
    role_permissions={
        "admin": {"order:read", "order:write", "order:delete"},
        "editor": {"order:read", "order:write"},
        "viewer": {"order:read"},
    },
    role_hierarchy={
        "admin": {"editor"},   # admin inherits editor's permissions
        "editor": {"viewer"},  # editor inherits viewer's permissions
    },
)
```

**How it works:**

1. Expand the principal's roles transitively through the hierarchy using BFS. If a principal has role `"admin"`, expansion yields `{"admin", "editor", "viewer"}`.
2. Collect all permissions from the expanded roles.
3. Construct the permission key as `"{resource_type}:{action}"` (e.g. `"order:read"`).
4. If the key is in the permission set → **Allow**. Otherwise → **Abstain** (not deny).

**Permission format:** `"{resource_type}:{action}"` — must match exactly. No wildcard support (use the hierarchy for inheritance patterns).

### ACLEvaluator

Per-resource access control list evaluation via `IAuthorizationPort.check_access()`.

```python
acl = ACLEvaluator(authorization_port=my_auth_port)
```

**How it works:**

1. Calls `check_access(access_token, resource_type, action, resource_ids)` on the authorization port.
2. **Type-level check** (no resource IDs): if the port returns any authorized IDs → **Allow**; otherwise → **Abstain**.
3. **Resource-level check**: if *all* requested resource IDs are in the authorized set → **Allow**. If any are explicitly denied → **Deny** (not abstain). Otherwise → **Abstain**.

The distinction between deny and abstain is important: the ACL evaluator produces an explicit deny when it receives a partial authorization (some IDs authorized, some not), signaling that the ABAC engine has made a definitive decision.

### OwnershipEvaluator

Grants access when `principal.user_id` matches the resource owner.

```python
ownership = OwnershipEvaluator(
    ownership_resolver=my_resolver,
    owner_actions={"read", "update", "delete"},  # None = all actions
)
```

**How it works:**

1. If `resource_ids` is empty/None → **Abstain** (ownership requires specific resources).
2. For each resource ID, call `ownership_resolver.get_owner(resource_type, resource_id)`.
3. If any owner is `None` → **Abstain** (unknown ownership, defer to other evaluators).
4. If `principal.user_id` is not in the owner list for any resource → **Abstain**.
5. If `owner_actions` is set and the requested action is not in the set → **Abstain**.
6. Otherwise → **Allow**.

**Co-ownership:** `get_owner()` can return `list[str]` for resources with multiple owners. The evaluator checks if `principal.user_id` is in that list.

### ABACConnector

Delegates evaluation to an external authorization engine (stateful-abac, OPA, Casbin, or any custom backend) via `IAuthorizationPort`.

```python
abac = ABACConnector(authorization_port=my_auth_port)
```

**How it works:**

1. Calls `check_access(access_token, resource_type, action, resource_ids)`.
2. **Type-level check**: if the port returns any results → **Allow**; otherwise → **Deny** (explicit deny, not abstain — the ABAC engine has made a decision).
3. **Resource-level check**: if all requested IDs are authorized → **Allow**; otherwise → **Deny**.

**Key difference from ACLEvaluator:** `ABACConnector` returns explicit deny (never abstain) because it assumes the external engine is authoritative. `ACLEvaluator` returns abstain when there are no matching ACL entries, deferring to subsequent evaluators.

### Custom Evaluators

Implement `IPermissionEvaluator` for any custom authorization logic:

```python
from cqrs_ddd_access_control import IPermissionEvaluator, AuthorizationContext, AuthorizationDecision
from cqrs_ddd_identity import Principal

class TimeBasedEvaluator(IPermissionEvaluator):
    """Deny write access outside business hours."""

    async def evaluate(self, principal: Principal, context: AuthorizationContext) -> AuthorizationDecision:
        import datetime
        now = datetime.datetime.now()

        if context.action in ("write", "delete") and not (9 <= now.hour < 17):
            return AuthorizationDecision(
                allowed=False,
                reason="Write operations restricted to business hours",
                evaluator="time_based",
            )
        return AuthorizationDecision(
            allowed=False,
            reason="abstain",
            evaluator="time_based",
        )

# Register in PEP
pep = PolicyEnforcementPoint(
    evaluators=[rbac, acl, TimeBasedEvaluator()],
)
```

**Guidelines for custom evaluators:**

- Return `reason="abstain"` when your evaluator has no opinion — do not deny by default.
- Return an explicit deny (descriptive reason ≠ `"abstain"`) only when your evaluator has enough information to make a definitive negative determination.
- Set `evaluator="your_name"` in all decisions for traceability.

---

## Policy Enforcement Point (PEP)

`PolicyEnforcementPoint` composes evaluators with **deny-wins** semantics.

```python
from cqrs_ddd_access_control import PolicyEnforcementPoint

pep = PolicyEnforcementPoint(
    evaluators=[rbac, acl, ownership, abac],
    cache=my_cache,                           # optional IPermissionCache
    bypass_roles=frozenset({"superadmin"}),    # optional
)
```

### Evaluation Algorithm

```
evaluate(principal, context):
  1. Bypass check: if principal has any bypass role → return Allow
  2. Cache check:  if cache hit exists → return cached decision
  3. For each evaluator (in order):
     a. decision = evaluator.evaluate(principal, context)
     b. If decision is DENY (reason ≠ "abstain" AND allowed=False):
        → cache + return DENY immediately (short-circuit)
     c. If decision is ALLOW and no candidate yet:
        → store as candidate
  4. If a candidate was found → cache + return candidate (ALLOW)
  5. Otherwise → cache + return DENY("No evaluator granted access")
```

**Key properties:**

- **Deny-wins:** A single explicit deny from any evaluator overrides all allows.
- **First-allow candidate:** The first evaluator to grant access becomes the candidate, but subsequent evaluators can still override with deny.
- **Short-circuit on deny:** Processing stops as soon as an explicit deny is encountered.
- **Abstain ≠ deny:** An abstain never triggers the deny short-circuit.
- **Order matters:** Evaluators are consulted in the order given. Place the most restrictive evaluators first to optimize short-circuit behavior.

### Batch Evaluation

```python
decisions = await pep.evaluate_batch(principal, [
    AuthorizationContext(resource_type="order", action="read"),
    AuthorizationContext(resource_type="order", action="delete", resource_ids=["ord-1"]),
    AuthorizationContext(resource_type="document", action="read"),
])
# Returns: list[AuthorizationDecision]
```

---

## Commands & Events

All ACL mutations follow the CQRS command → event → priority handler pipeline. Commands never call the admin port directly — they emit request events, which are processed by priority event handlers within the same Unit of Work.

### Commands

| Command | Fields | Description |
|---------|--------|-------------|
| `GrantACL` | `resource_type`, `action`, `principal_name`, `role_name`, `resource_id`, `conditions`, `specification_dsl` | Grant an ACL entry |
| `RevokeACL` | `resource_type`, `action`, `principal_name`, `role_name`, `resource_id` | Revoke an ACL entry |
| `SetResourcePublic` | `resource_type`, `is_public` | Set a resource type's public visibility |
| `GrantOwnershipACL` | `resource_type`, `action`, `principal_name`, `resource_id` | Grant owner-level ACL |

```python
from cqrs_ddd_access_control import GrantACL

grant = GrantACL(
    resource_type="document",
    action="read",
    role_name="analyst",
    conditions={"region": {"op": "eq", "val": "EU"}},
)
response = await mediator.send(grant)
```

### Events

**Request events** (emitted by command handlers):

| Event | Fields | Emitted by |
|-------|--------|------------|
| `ACLGrantRequested` | `resource_type`, `action`, `principal_name`, `role_name`, `resource_id`, `access_rules`, `conditions`, `specification_dsl` | `GrantACLHandler`, `GrantOwnershipACLHandler` |
| `ACLRevokeRequested` | `resource_type`, `action`, `principal_name`, `role_name`, `resource_id` | `RevokeACLHandler` |
| `ResourceTypePublicSetRequested` | `resource_type`, `is_public` | `SetResourcePublicHandler` |

**Completion events** (emitted by priority handlers after persisting):

| Event | Fields | Purpose |
|-------|--------|---------|
| `ACLGranted` | `resource_type`, `action`, `principal_name`, `role_name`, `resource_id`, `conditions`, `specification_dsl` | Confirms grant was persisted |
| `ACLRevoked` | `resource_type`, `action`, `principal_name`, `role_name`, `resource_id`, `previous_state` | Confirms revoke; carries `previous_state` for undo |
| `ResourceTypePublicSet` | `resource_type`, `is_public`, `previous_public` | Confirms public flag change; carries `previous_public` for undo |

### Event Flow

```
GrantACL command
  → GrantACLHandler.handle()
    → emits ACLGrantRequested event
      → ACLGrantRequestedHandler (priority handler, same UoW)
        → calls admin_port.create_acl() (or create_acl_from_specification)
        → injects tenant isolation conditions
        → persists ACLGranted to event store
```

---

## Middleware

### AuthorizationMiddleware

Two-phase middleware: **pre-check** resource IDs before the handler executes, **post-filter** unauthorized entities from the result.

```python
from cqrs_ddd_access_control import AuthorizationMiddleware, AuthorizationConfig

mw = AuthorizationMiddleware(
    authorization_port=my_auth_port,
    config=AuthorizationConfig(
        resource_type="order",                   # static type, or use resource_type_attr
        resource_type_attr=None,                 # message attribute for dynamic type
        required_actions=["read"],               # actions to check
        action_quantifier="all",                 # "all" | "any"
        list_quantifier="all",                   # "all" | "any"
        resource_id_attr="order_id",             # dotted path to extract IDs from message
        result_entities_attr="items",            # dotted path to entities in the result
        entity_id_attr="id",                     # ID attribute on result entities
        fail_silently=False,                     # True = silently drop denied items
        deny_anonymous=False,                    # True = reject unauthenticated requests
        auth_context_provider=None,              # Callable[[message], dict | None]
    ),
    bypass_roles=frozenset({"superadmin"}),
)
```

**Pre-check phase:**

1. Extract resource IDs from the message via `resource_id_attr` (supports dotted paths like `"payload.order_id"`).
2. Build `CheckAccessItem` objects for each required action.
3. Call `check_access_batch()` on the authorization port.
4. For each resource ID, call `batch_result.is_allowed()` with the configured `action_quantifier` (`"all"` = must have all actions, `"any"` = must have at least one).
5. If any ID is denied and `fail_silently=False` → raise `PermissionDeniedError`.

**Post-filter phase** (only if `result_entities_attr` is set):

1. Extract entities from the result via `result_entities_attr`.
2. Collect entity IDs via `entity_id_attr`.
3. Call `check_access_batch()` to verify each entity.
4. Filter out unauthorized entities.
5. Replace the entities list on the result (supports frozen Pydantic models via `model_copy`).

**Dotted attribute paths:** Both `resource_id_attr` and `result_entities_attr` support dotted paths (e.g. `"payload.items"`, `"result.data.entities"`). The middleware resolves these using `operator.attrgetter` for reads and `model_copy` chains for writes on frozen models.

### SpecificationAuthMiddleware

Merges authorization conditions into `QueryOptions.specification` so the database (via SQLAlchemy) enforces access control in a **single SQL query** — no post-filtering.

```python
from cqrs_ddd_access_control import SpecificationAuthMiddleware, SpecificationAuthConfig

mw = SpecificationAuthMiddleware(
    authorization_port=my_auth_port,
    config=SpecificationAuthConfig(
        resource_type="order",
        action="read",
        query_options_attr="query_options",
        auth_context_provider=None,
    ),
    resource_type_registry=registry,
    bypass_roles=frozenset({"superadmin"}),
)
```

**How it works:**

1. Look up the `ResourceTypeConfig` from the registry to get the `FieldMapping`.
2. Call `authorization_port.get_authorization_filter()` with the field mapping.
3. If the filter says `denied_all` → raise `PermissionDeniedError`.
4. If the filter says `granted_all` → pass through, no filtering needed.
5. If the filter has a `filter_specification`:
   - Get `query_options` from the message.
   - If `query_options.specification` already exists, **merge** the auth spec using `spec.merge(auth_spec)` (logical AND).
   - Otherwise, set the auth spec as the sole specification.
   - Update the message with the new `query_options` via `model_copy`.

**Result:** The repository's query automatically includes authorization WHERE clauses. No unauthorized rows ever leave the database.

**Requires:** `cqrs-ddd-specifications` (optional dependency).

### PermittedActionsMiddleware

Post-execution enrichment that attaches an array of permitted actions to each entity in the result.

```python
from cqrs_ddd_access_control import PermittedActionsMiddleware, PermittedActionsConfig

mw = PermittedActionsMiddleware(
    authorization_port=my_auth_port,
    config=PermittedActionsConfig(
        resource_type="order",
        result_entities_attr="items",
        entity_id_attr="id",
        permitted_actions_attr="permitted_actions",
        include_type_level=True,                  # merge type-level perms
        auth_context_provider=None,
    ),
    bypass_roles=frozenset({"superadmin"}),
)
```

**How it works:**

1. After the handler produces a result, extract entities from `result_entities_attr`.
2. Collect all entity IDs.
3. Call `get_permitted_actions_batch()` to get per-resource action lists.
4. Optionally call `get_type_level_permissions()` for type-level actions.
5. Merge resource-level and type-level actions, set on each entity as `permitted_actions_attr`.
6. Handles frozen Pydantic models by falling back to `model_copy`.

**Frontend integration:** The `permitted_actions` array drives UI conditional rendering — show/hide edit buttons, delete options, approve workflows based on what the current user can actually do with each resource.

### DecoratorAuthorizationMiddleware

Reads `@requires_permission`, `@requires_role`, `@requires_owner`, and `@authorization` metadata from handler classes and enforces the requirements **before** the handler executes.

```python
from cqrs_ddd_access_control import DecoratorAuthorizationMiddleware

mw = DecoratorAuthorizationMiddleware(
    handler_registry=handler_registry,      # HandlerRegistry from cqrs-ddd-core
    authorization_port=my_auth_port,        # optional, for @authorization
    ownership_resolver=my_resolver,         # optional, for @requires_owner
    bypass_roles=frozenset({"superadmin"}),
)
```

**How it works:**

1. Resolve the handler class for the incoming message type from the `HandlerRegistry`.
2. Inspect the class for decorator metadata (`__access_permission__`, `__access_role__`, `__access_owner__`, `__authorization_config__`).
3. For `@requires_permission`: check `principal.has_permission()` with the configured qualifier.
4. For `@requires_role`: check `principal.has_any_role()` / `principal.roles` with the configured qualifier.
5. For `@requires_owner`: use `IOwnershipResolver` to verify ownership.
6. For `@authorization`: delegate to `AuthorizationMiddleware` with the embedded config.

All checks happen in sequence. The handler only executes if all requirements pass.

### Middleware Chaining

Combine middleware for layered authorization. Registration order (priority) determines execution order:

```python
# Typical pipeline for a query handler:
#
# 1. DecoratorAuthorizationMiddleware (priority=5) — static role/permission checks
# 2. AuthorizationMiddleware (priority=10)         — pre-check resource IDs
# 3. Handler executes
# 4. SpecificationAuthMiddleware (priority=15)     — single-query auth
# 5. PermittedActionsMiddleware (priority=20)      — enrich with permitted actions
```

For write operations, typically only `AuthorizationMiddleware` or `DecoratorAuthorizationMiddleware` is needed:

```python
# Write pipeline:
# 1. DecoratorAuthorizationMiddleware — @requires_permission("order:write")
# 2. Handler executes (creates/updates the resource)
```

---

## Decorators

Class decorators that set authorization metadata on handler classes. The metadata is read at runtime by `DecoratorAuthorizationMiddleware`.

### @requires_permission

```python
from cqrs_ddd_access_control import requires_permission

# Single permission (default qualifier: "all")
@requires_permission("order:read")
class ListOrdersHandler:
    async def handle(self, query: ListOrders) -> OrderList: ...

# Multiple permissions — principal must have ALL
@requires_permission(["order:read", "order:export"])
class ExportOrdersHandler:
    async def handle(self, query: ExportOrders) -> bytes: ...

# Multiple permissions — principal must have AT LEAST ONE
@requires_permission(["order:write", "order:admin"], "any")
class UpdateOrderHandler:
    async def handle(self, command: UpdateOrder) -> None: ...

# Deny if principal HAS the permission
@requires_permission("order:restricted", "not")
class PublicOrderHandler:
    async def handle(self, query: ListPublicOrders) -> OrderList: ...
```

Stores a `PermissionRequirement(permissions=(...), qualifier="all"|"any"|"not")` on the handler class as `__access_permission__`.

### @requires_role

```python
from cqrs_ddd_access_control import requires_role

# Must have the role
@requires_role("admin")
class AdminDashboardHandler:
    async def handle(self, query: AdminDashboard) -> Dashboard: ...

# Must have any of these roles
@requires_role(["admin", "manager"], "any")
class ApproveOrderHandler:
    async def handle(self, command: ApproveOrder) -> None: ...

# Must NOT have this role (deny guests)
@requires_role("guest", "not")
class SensitiveDataHandler:
    async def handle(self, query: SensitiveData) -> Data: ...
```

Stores a `RoleRequirement(roles=(...), qualifier="all"|"any"|"not")` on the handler class as `__access_role__`.

### @requires_owner

```python
from cqrs_ddd_access_control import requires_owner

@requires_owner(resource_type="order", id_field="order_id")
class UpdateMyOrderHandler:
    async def handle(self, command: UpdateMyOrder) -> None: ...
```

The middleware extracts `command.order_id`, calls `IOwnershipResolver.get_owner("order", order_id)`, and verifies `owner == principal.user_id`. Raises `PermissionDeniedError` on mismatch.

Stores an `OwnershipRequirement(resource_type=..., id_field=...)` on the handler class as `__access_owner__`.

### @authorization

Full ABAC/ACL middleware configuration embedded in the handler class:

```python
from cqrs_ddd_access_control import authorization

@authorization(
    resource_type="order",
    required_actions=["read"],
    resource_id_attr="order_id",
    result_entities_attr="items",
    entity_id_attr="id",
)
class ListOrdersHandler:
    async def handle(self, query: ListOrders) -> OrderList: ...
```

This stores a full `AuthorizationConfig` on the handler class. When `DecoratorAuthorizationMiddleware` encounters this metadata, it instantiates an `AuthorizationMiddleware` inline and delegating the full pre-check + post-filter flow to it.

### Qualifier Semantics

The `qualifier` parameter controls how multiple permissions/roles are evaluated:

| Qualifier | Semantics | Example |
|-----------|-----------|---------|
| `"all"` (default) | Principal must have **every** listed permission/role | `@requires_permission(["order:read", "order:export"])` — must have both |
| `"any"` | Principal must have **at least one** | `@requires_role(["admin", "manager"], "any")` — either suffices |
| `"not"` | Principal must have **none** of them | `@requires_role("guest", "not")` — guests are denied |

### Combining Decorators

Multiple decorators can be stacked. All requirements are checked in sequence:

```python
@requires_role("editor")
@requires_permission("document:publish")
@requires_owner(resource_type="document", id_field="doc_id")
class PublishDocumentHandler:
    async def handle(self, command: PublishDocument) -> None: ...
```

This handler requires: role `"editor"` AND permission `"document:publish"` AND ownership of the document.

---

## Authorizable Entities

The `@register_access_entity` decorator marks domain entities for access control. It:

1. Builds and stores a `ResourceTypeConfig` on the class as `__access_config__`.
2. Adds `AuthorizableEntity` protocol methods to the class.
3. Makes the entity discoverable by `get_access_config()` for later registration.

```python
from cqrs_ddd_access_control import register_access_entity, FieldMapping

@register_access_entity(
    resource_type="document",
    field_mapping=FieldMapping(
        mappings={"category": "doc_category", "department": "dept"},
        external_id_field="id",
        external_id_cast=int,  # cast external IDs to int when converting ABAC conditions
    ),
    actions=["read", "write", "delete", "approve", "publish"],
    is_public=False,
    auto_register_resources=True,
)
class Document:
    id: int
    category: str
    department: str
    owner_id: str
```

**What the decorator adds:**

```python
Document.access_resource_type()     # → "document"
Document.access_field_mapping()     # → FieldMapping(...)
Document.access_syncable_fields()   # → ["category", "department"]
Document.access_valid_actions()     # → ["read", "write", ...]

doc = Document(...)
events = doc.grant_access([
    AccessRule(role_name="viewer", action="read"),
    AccessRule(principal_name="user-123", action="write", resource_id="doc-1"),
])
# Returns [ACLGrantRequested(...)]
```

**AuthorizableEntity protocol:**

```python
@runtime_checkable
class AuthorizableEntity(Protocol):
    @classmethod
    def access_resource_type(cls) -> str: ...
    @classmethod
    def access_field_mapping(cls) -> FieldMapping: ...
    @classmethod
    def access_syncable_fields(cls) -> list[str]: ...
    @classmethod
    def access_valid_actions(cls) -> list[str]: ...
    def grant_access(self, rules: list[AccessRule]) -> list[DomainEvent]: ...
```

**No global state:** `ResourceTypeRegistry` is application-owned. The decorator only stores metadata on the class for later discovery. The application decides when and how to register entities at startup.

---

## Resource Synchronization

`ResourceSyncService` provisions resource types, actions, and resource instances in the authorization engine.

```python
from cqrs_ddd_access_control import ResourceSyncService

sync = ResourceSyncService(
    admin_port=my_admin_port,
    registry=resource_type_registry,
)

# Provision a resource type and its actions
await sync.ensure_resource_type("order")

# Sync a resource instance with attributes and optional GeoJSON
await sync.sync_resource(
    resource_type="order",
    resource_id="ord-123",
    attributes={"status": "pending", "region": "EU"},
    geometry={"type": "Point", "coordinates": [2.3522, 48.8566]},
)

# Delete a resource
await sync.delete_resource("order", "ord-123")

# Provision all registered types at startup
await sync.sync_all_resource_types()
```

### Field Mapping

`FieldMapping` defines the bidirectional mapping between app entity field names and authorization engine attribute names:

```python
mapping = FieldMapping(
    mappings={
        "status": "order_status",   # app field → ABAC attribute
        "region": "region",         # same name, explicit for clarity
    },
    external_id_field="id",
    external_id_cast=str,  # how to cast external_id values
)

# Forward: app → ABAC
mapping.get_abac_attr("status")      # → "order_status"
mapping.get_abac_attr("region")      # → "region"
mapping.get_abac_attr("unknown")     # → "unknown" (passthrough)

# Reverse: ABAC → app
mapping.get_field("order_status")    # → "status"

# External ID casting
mapping.cast_external_id("123")      # → "123"
mapping.cast_external_id(["1", "2"]) # → ["1", "2"]
```

**Attribute transformation:** `sync_resource()` automatically transforms attributes using the field mapping before sending them to the engine:

```python
# App attributes
{"status": "pending", "region": "EU"}

# After transformation via mapping
{"order_status": "pending", "region": "EU"}
```

**GeoJSON support:** The `geometry` parameter passes spatial data for ABAC engines that support geospatial conditions (e.g., PostGIS-backed stateful-abac).

**Caching:** `ensure_resource_type()` caches which types have been provisioned to avoid duplicate `create_resource_type` calls.

---

## Permission Caching

`PermissionDecisionCache` wraps `ICacheService` from `cqrs-ddd-core` to cache `AuthorizationDecision` objects.

```python
from cqrs_ddd_access_control import PermissionDecisionCache

cache = PermissionDecisionCache(
    cache=my_cache_service,  # ICacheService from cqrs-ddd-core
    default_ttl=60,          # seconds
)
```

### Cache Key Format

```
authz:{principal_id}:{resource_type}:{resource_id or '*'}:{action}
```

Examples:
- `authz:user-123:order:ord-456:read` — resource-level
- `authz:user-123:order:*:create` — type-level (no specific resource)

### Storage Format

Decisions are serialized as JSON:

```json
{"allowed": true, "reason": "Role permission match: order:read", "evaluator": "rbac"}
```

### Invalidation

```python
# Invalidate all decisions for a specific resource
await cache.invalidate("order", "ord-456")

# Invalidate all decisions for a resource type
await cache.invalidate("order")
```

Invalidation uses `cache.clear_namespace()` with glob pattern `authz:*:{resource_type}:{resource_id or '*'}`.

### Integration with PEP

```python
pep = PolicyEnforcementPoint(
    evaluators=[rbac, acl, ownership],
    cache=cache,  # PEP automatically checks/updates cache
)
```

The PEP checks the cache *before* consulting evaluators and stores the final decision *after* evaluation. This means a cached deny also benefits from short-circuit — the evaluators are never called.

---

## Elevation (Step-Up Authentication)

The package provides two complementary tools for step-up authentication:

1. **`verify_elevation()`** — runtime check to confirm the current user holds an active elevation grant.
2. **Step-up commands, events, handlers, and saga** — a full orchestration layer for requesting, verifying, and automatically revoking temporary elevation grants.

### verify_elevation()

Checks if the current principal has step-up authentication for a sensitive action. Uses the `"elevation"` resource type in the ABAC engine.

```python
from cqrs_ddd_access_control import verify_elevation

# Mode 1: raise on failure (default)
await verify_elevation(
    authorization_port=my_auth_port,
    action="delete_tenant",
    on_fail="raise",
)
# Raises ElevationRequiredError if not elevated

# Mode 2: return bool
is_elevated = await verify_elevation(
    authorization_port=my_auth_port,
    action="approve_payment",
    on_fail="return",
)
if not is_elevated:
    return {"status": "elevation_required", "action": "approve_payment"}
```

**How it works:** Calls `check_access(access_token, resource_type="elevation", action=action)` on the authorization port. The ABAC engine maintains elevation grants that are time-limited and tied to successful step-up authentication (MFA re-verification, etc.).

---

### Step-Up Flow Overview

The step-up flow orchestrates MFA-gated re-authentication before allowing a sensitive operation to proceed. It integrates with the CQRS command pipeline and, optionally, the `StepUpAuthenticationSaga` for full saga-based orchestration.

```
 ┌─────────────────────────────────────────────────────────────┐
 │  1. Command handler detects elevation required              │
 │     → emits SensitiveOperationRequested                     │
 └────────────────────────┬────────────────────────────────────┘
                          │
 ┌────────────────────────▼────────────────────────────────────┐
 │  2. Identity / auth layer handles SensitiveOperationRequested│
 │     → sends MFA challenge to user (OTP, TOTP, push …)       │
 │  [Saga: SUSPENDED — 5-minute timeout]                       │
 └────────────────────────┬────────────────────────────────────┘
                          │
 ┌────────────────────────▼────────────────────────────────────┐
 │  3. User submits MFA code                                   │
 │     → identity layer emits MFAChallengeVerified             │
 │  [Saga: RESUME]                                             │
 └────────────────────────┬────────────────────────────────────┘
                          │
 ┌────────────────────────▼────────────────────────────────────┐
 │  4. Saga dispatches GrantTemporaryElevation                 │
 │     → ACLGrantRequested  → ABAC creates time-limited grant  │
 │     → TemporaryElevationGranted (audit)                     │
 └────────────────────────┬────────────────────────────────────┘
                          │
 ┌────────────────────────▼────────────────────────────────────┐
 │  5. Saga dispatches ResumeSensitiveOperation                │
 │     → original command is deserialized and re-dispatched    │
 │     → SensitiveOperationCompleted                           │
 └────────────────────────┬────────────────────────────────────┘
                          │
 ┌────────────────────────▼────────────────────────────────────┐
 │  6. Saga dispatches RevokeElevation → cleans up ACL grants  │
 │     → TemporaryElevationRevoked (audit)                     │
 │  [Saga: COMPLETED]                                          │
 └─────────────────────────────────────────────────────────────┘
```

**Timeout path:** If the user does not verify within 5 minutes, the saga dispatches `RevokeElevation` (removing any partial grants), runs compensation, and marks itself `FAILED`.

---

### Step-Up Commands

All commands are importable from `cqrs_ddd_access_control` directly.

#### `GrantTemporaryElevation`

Grants temporary elevated privileges for a specific action. Typically dispatched by the saga after `MFAChallengeVerified`.

```python
from cqrs_ddd_access_control import GrantTemporaryElevation

cmd = GrantTemporaryElevation(
    user_id="user-123",
    action="delete_tenant",
    ttl_seconds=300,       # default: 5 minutes
)
```

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | `str` | The user receiving the elevation |
| `action` | `str` | The ABAC action being elevated |
| `ttl_seconds` | `int` | TTL in seconds (default `300`) |

#### `RevokeElevation`

Revokes temporary elevated privileges. If `action` is `None`, revokes all elevation ACLs for the session (matched by `correlation_id`).

```python
from cqrs_ddd_access_control import RevokeElevation

# Revoke all elevations for this session
cmd = RevokeElevation(
    user_id="user-123",
    reason="completed",     # or "timeout", "saga_compensation"
)

# Revoke a specific action's elevation
cmd = RevokeElevation(
    user_id="user-123",
    action="delete_tenant",
    reason="completed",
)
```

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | `str` | The user whose elevation is revoked |
| `action` | `str \| None` | Specific action (`None` = all for session) |
| `reason` | `str` | Revocation reason (audit) |

#### `ResumeSensitiveOperation`

Signals that MFA is complete and the suspended operation may proceed. If `original_command_data` is provided, the handler deserializes and re-dispatches the original command automatically.

```python
from cqrs_ddd_access_control import ResumeSensitiveOperation

cmd = ResumeSensitiveOperation(
    operation_id="op-abc-123",
    original_command_data={
        "module_name": "myapp.application.commands",
        "type_name": "DeleteTenant",
        "data": {"tenant_id": "t-42"},
    },
)
```

| Field | Type | Description |
|-------|------|-------------|
| `operation_id` | `str` | The operation ID from `SensitiveOperationRequested` |
| `original_command_data` | `dict \| None` | Serialised original command for auto-replay |

---

### Step-Up Events

| Event | Emitted by | Purpose |
|-------|-----------|--------|
| `SensitiveOperationRequested` | Your command handler | Triggers MFA challenge delivery and saga suspension |
| `MFAChallengeVerified` | Identity / auth layer | Resumes the saga after successful MFA |
| `SensitiveOperationCompleted` | `ResumeSensitiveOperationHandler` | Signals saga to revoke elevation and complete |
| `TemporaryElevationGranted` | `GrantTemporaryElevationHandler` | Audit: elevation was granted |
| `TemporaryElevationRevoked` | `RevokeElevationHandler` | Audit: elevation was revoked |

#### `SensitiveOperationRequested`

```python
from cqrs_ddd_access_control import SensitiveOperationRequested, serialize_command
import uuid

event = SensitiveOperationRequested(
    user_id=command.user_id,
    operation_id=str(uuid.uuid4()),
    action="delete_tenant",
    original_command_data=serialize_command(command),  # for auto-replay
)
```

#### `MFAChallengeVerified`

Your identity/auth layer emits this after confirming the user's MFA code:

```python
from cqrs_ddd_access_control import MFAChallengeVerified

event = MFAChallengeVerified(
    user_id="user-123",
    method="totp",   # "email", "sms", "totp", "push", ...
)
```

---

### Step-Up Handlers

Register these with your mediator/command bus alongside your other handlers.

#### `GrantTemporaryElevationHandler`

Emits `ACLGrantRequested` (processed by the priority ACL handler to create the `"elevation"` ACL in the ABAC engine) and `TemporaryElevationGranted`.

```python
from cqrs_ddd_access_control import GrantTemporaryElevationHandler

mediator.register_handler(GrantTemporaryElevation, GrantTemporaryElevationHandler())
```

#### `RevokeElevationHandler`

Calls the undo service to reverse all ACL grants created during the elevated session, then emits `TemporaryElevationRevoked`.

```python
from cqrs_ddd_access_control import RevokeElevationHandler

mediator.register_handler(
    RevokeElevation,
    RevokeElevationHandler(undo_service=my_undo_service),  # undo_service optional
)
```

#### `ResumeSensitiveOperationHandler`

Deserializes and re-dispatches the original command (if `original_command_data` is set), then emits `SensitiveOperationCompleted`.

```python
from cqrs_ddd_access_control import ResumeSensitiveOperationHandler

mediator.register_handler(
    ResumeSensitiveOperation,
    ResumeSensitiveOperationHandler(mediator=mediator),
)
```

---

### StepUpAuthenticationSaga

Requires `cqrs-ddd-advanced-core` (`pip install cqrs-ddd-access-control[advanced]`).

```python
from cqrs_ddd_access_control import StepUpAuthenticationSaga, StepUpState
```

The saga orchestrates the full step-up flow automatically:

| Trigger | Saga action |
|---------|------------|
| `SensitiveOperationRequested` | Saves state, **suspends** with a 5-minute timeout |
| `MFAChallengeVerified` (matching user) | **Resumes**, dispatches `GrantTemporaryElevation` + `ResumeSensitiveOperation`, registers `RevokeElevation` as compensation |
| `SensitiveOperationCompleted` | Dispatches `RevokeElevation`, **completes** |
| Timeout | Dispatches `RevokeElevation`, runs compensation, **fails** |

**Registration:**

```python
from cqrs_ddd_advanced_core.sagas import SagaRegistry
from cqrs_ddd_access_control import StepUpAuthenticationSaga, StepUpState

registry = SagaRegistry()
registry.register(StepUpAuthenticationSaga, state_factory=StepUpState)
```

**Custom MFA TTL:**

```python
# Default: 5 minutes (300 s) — override via constructor
step_up_saga = StepUpAuthenticationSaga(
    state=StepUpState(),
    mfa_ttl_seconds=600,  # 10 minutes
)
```

**`StepUpState` fields:**

| Field | Type | Description |
|-------|------|-------------|
| `operation_id` | `str \| None` | ID of the pending operation |
| `user_id` | `str \| None` | The user being authenticated |
| `required_action` | `str \| None` | The action the user must be elevated for |
| `original_command_data` | `dict \| None` | Serialised command for auto-replay |

---

### serialize_command Utility

`serialize_command()` serialises any Pydantic-based `Command` to a JSON-safe dict so it can be stored in `SensitiveOperationRequested.original_command_data` and automatically replayed by `ResumeSensitiveOperationHandler`.

```python
from cqrs_ddd_access_control import serialize_command

data = serialize_command(my_command)
# {
#   "module_name": "myapp.application.commands",
#   "type_name": "DeleteTenant",
#   "data": {"tenant_id": "t-42", ...},  # model_dump, excludes IDs
# }
```

`command_id` and `correlation_id` are excluded from `data`; they are regenerated when the command is re-dispatched.

---

### End-to-End Example

```python
import uuid
from cqrs_ddd_access_control import (
    SensitiveOperationRequested,
    MFAChallengeVerified,
    GrantTemporaryElevationHandler,
    RevokeElevationHandler,
    ResumeSensitiveOperationHandler,
    GrantTemporaryElevation,
    RevokeElevation,
    ResumeSensitiveOperation,
    serialize_command,
    verify_elevation,
)
from cqrs_ddd_access_control import StepUpAuthenticationSaga, StepUpState

# --- 1. Register handlers ---
mediator.register_handler(GrantTemporaryElevation, GrantTemporaryElevationHandler())
mediator.register_handler(RevokeElevation, RevokeElevationHandler(undo_service=undo_svc))
mediator.register_handler(
    ResumeSensitiveOperation,
    ResumeSensitiveOperationHandler(mediator=mediator),
)

# --- 2. Register the saga ---
from cqrs_ddd_advanced_core.sagas import SagaRegistry
registry = SagaRegistry()
registry.register(StepUpAuthenticationSaga, state_factory=StepUpState)

# --- 3. Command handler emits SensitiveOperationRequested ---
class DeleteTenantHandler(CommandHandler):
    async def handle(self, command):
        # Check for elevation; if absent, request step-up
        is_elevated = await verify_elevation(
            auth_port, action="delete_tenant", on_fail="return"
        )
        if not is_elevated:
            event = SensitiveOperationRequested(
                user_id=command.user_id,
                operation_id=str(uuid.uuid4()),
                action="delete_tenant",
                original_command_data=serialize_command(command),
            )
            return CommandResponse(result=None, events=[event])

        # Elevation confirmed — proceed with deletion
        ...

# --- 4. Identity layer: user passes MFA → emit MFAChallengeVerified ---
event = MFAChallengeVerified(user_id="user-123", method="totp")
await event_dispatcher.dispatch(event)
# Saga resumes → grants elevation → re-dispatches DeleteTenant → revokes elevation
```

---

## Undo / Redo

All ACL completion events (`ACLGranted`, `ACLRevoked`, `ResourceTypePublicSet`) carry previous state for undo support. Requires `cqrs-ddd-advanced-core`.

### Undo Executors

| Executor | Event | Undo Action | Redo Action |
|----------|-------|-------------|-------------|
| `ACLGrantedUndoExecutor` | `ACLGranted` | Send `RevokeACL` | Send `GrantACL` |
| `ACLRevokedUndoExecutor` | `ACLRevoked` | Send `GrantACL` with `previous_state` conditions | Send `RevokeACL` |
| `ResourceTypePublicSetUndoExecutor` | `ResourceTypePublicSet` | Send `SetResourcePublic` with `previous_public` | Send `SetResourcePublic` with original value |

### Previous State Tracking

- `ACLRevoked.previous_state` — `dict` containing `conditions` and `specification_dsl` from before the revocation, allowing full restoration.
- `ResourceTypePublicSet.previous_public` — `bool | None`, the public flag before the change.

### Registration

```python
from cqrs_ddd_access_control.undo import register_acl_undo_executors

register_acl_undo_executors(
    undo_registry=undo_registry,  # IUndoExecutorRegistry from cqrs-ddd-advanced
    mediator=mediator,
)
```

This registers all three executors. Each executor uses the `Mediator` to send commands, meaning undo operations go through the same command → event → handler pipeline — same validation, same middleware, same audit trail.

### can_undo Checks

- `ACLGrantedUndoExecutor.can_undo()` — requires `resource_type` and `action` to be present.
- `ACLRevokedUndoExecutor.can_undo()` — requires `previous_state` to be present.
- `ResourceTypePublicSetUndoExecutor.can_undo()` — requires `previous_public` to be present.

---

## Multi-Tenant Isolation

The package enforces tenant isolation at the ACL level through two mechanisms:

### 1. Condition Injection (Priority Handlers)

`ACLGrantRequestedHandler` inspects the current principal's `tenant_id` and automatically injects it as a condition on all ACL grants:

```python
# In ACLGrantRequestedHandler.enforce_tenant_isolation():
# If principal.tenant_id is set, wraps conditions in:
{
    "op": "and",
    "conditions": [
        {"op": "eq", "attr": "tenant_id", "val": "<principal.tenant_id>"},
        <original_conditions>
    ]
}
```

This ensures that ACLs created by tenant `A` cannot accidentally grant access to tenant `B`'s resources. The injection happens transparently in the priority event handler.

### 2. Realm-Per-Tenant Isolation (Stateful-ABAC)

With the stateful-abac adapter, each tenant gets its own **realm** — a completely isolated namespace for resource types, actions, ACLs, and resources.

```python
from cqrs_ddd_access_control.contrib.stateful_abac import ABACClientConfig
from cqrs_ddd_identity.context import get_tenant_id

def _resolve_realm() -> str:
    tid = get_tenant_id()
    if not tid:
        raise ValueError("No tenant in context — cannot resolve ABAC realm")
    return tid

config = ABACClientConfig(
    mode="http",
    base_url="https://abac.example.com",
    realm=_resolve_realm,  # resolved lazily per request
)
```

The adapter caches one SDK client per realm. Each request resolves the realm at call time via `config.resolve_realm()`, selecting the correct isolated client.

> **Note:** Do not use `lambda: get_current_principal().tenant_id` directly — `tenant_id` is `str | None` on `Principal`. If `None`, the SDK factory will raise a cryptic `ValueError("realm is required")`. Use `get_tenant_id()` from `cqrs_ddd_identity.context` which safely returns `None` for unauthenticated/no-tenant requests, and guard explicitly.

---

## Bypass Roles

Certain roles can skip all authorization checks entirely. Configured in three ways (in priority order):

1. **Constructor parameter** (highest priority):
   ```python
   AuthorizationMiddleware(..., bypass_roles=frozenset({"superadmin", "system"}))
   ```

2. **Environment variable** `AUTH_BYPASS_ROLES` (fallback):
   ```bash
   export AUTH_BYPASS_ROLES="superadmin,system"
   ```

3. **Not specified** → empty set (no bypass).

The resolution logic in `_resolve_bypass_roles()`:
- If `bypass_roles` is passed (even as empty frozenset) → use it.
- Otherwise, read `AUTH_BYPASS_ROLES` from environment, split by comma, strip whitespace.

Bypass roles are checked in: `PolicyEnforcementPoint`, `AuthorizationMiddleware`, `SpecificationAuthMiddleware`, `PermittedActionsMiddleware`, and `DecoratorAuthorizationMiddleware`. When bypass activates:
- **PEP:** Returns `AuthorizationDecision(allowed=True, reason="Bypass role", evaluator="pep")`.
- **Middleware:** Calls `next_handler` directly, skipping all checks.
- **PermittedActionsMiddleware:** Returns result without enrichment (bypass users implicitly have all actions).

---

## Exceptions

All exceptions inherit from `AccessControlError → DomainError → CQRSDDDError`.

```
CQRSDDDError
└── DomainError
    └── AccessControlError (code="ACCESS_CONTROL_ERROR")
        ├── PermissionDeniedError (code="PERMISSION_DENIED")
        │   └── ElevationRequiredError (code="ELEVATION_REQUIRED")
        ├── InsufficientRoleError (code="INSUFFICIENT_ROLE")
        └── ACLError (code="ACL_ERROR")
```

### AccessControlError

Base exception for all access control errors.

```python
class AccessControlError(DomainError):
    def __init__(self, message: str = "Access control error", code: str = "ACCESS_CONTROL_ERROR",
                 details: dict[str, Any] | None = None): ...
```

### PermissionDeniedError

Raised when a principal lacks the required permission.

```python
raise PermissionDeniedError(
    resource_type="order",
    action="delete",
    resource_ids=["ord-123", "ord-456"],
    reason="ACL denied for resources",
)

# Access structured details:
except PermissionDeniedError as e:
    e.code          # "PERMISSION_DENIED"
    e.details       # {"resource_type": "order", "action": "delete",
                    #  "resource_ids": ["ord-123", "ord-456"]}
    e.reason        # "ACL denied for resources"
    str(e)          # "ACL denied for resources"
```

### ElevationRequiredError

Subclass of `PermissionDeniedError`. Raised by `verify_elevation()`.

```python
raise ElevationRequiredError(action="delete_tenant")

# e.code    → "ELEVATION_REQUIRED"
# e.details → {"resource_type": "elevation", "action": "delete_tenant"}
```

### InsufficientRoleError

```python
raise InsufficientRoleError(
    required_role="admin",
    message="Missing required role: admin",
)
# e.code    → "INSUFFICIENT_ROLE"
# e.details → {"required_role": "admin"}
```

### ACLError

For ACL-specific failures (creation, deletion, etc.).

```python
raise ACLError("Failed to create ACL entry", details={"resource_type": "order"})
```

---

## Contrib: Stateful-ABAC Adapter

Full adapter for the [stateful-abac-policy-engine](https://github.com/mgourlis/stateful-abac-policy-engine), implementing both `IAuthorizationPort` and `IAuthorizationAdminPort`.

```bash
pip install cqrs-ddd-access-control[stateful-abac]
```

### Client Configuration

```python
from cqrs_ddd_access_control.contrib.stateful_abac import ABACClientConfig

# HTTP mode (production)
config = ABACClientConfig(
    mode="http",
    base_url="https://abac.example.com",
    realm="my-tenant",               # static realm
    timeout=30,                       # forwarded to the HTTP client
    chunk_size=500,                   # batch processing chunk size
    max_concurrent=5,                 # max concurrent requests
)

# Dynamic realm (multi-tenant) — use get_tenant_id(), NOT get_current_principal().tenant_id
from cqrs_ddd_identity.context import get_tenant_id

def _resolve_realm() -> str:
    tid = get_tenant_id()
    if not tid:
        raise ValueError("No tenant in context — cannot resolve ABAC realm")
    return tid

config = ABACClientConfig(
    mode="http",
    base_url="https://abac.example.com",
    realm=_resolve_realm,
)

# DB mode (testing/single-process — bypasses HTTP, talks directly to the policy engine DB)
config = ABACClientConfig(mode="db", realm="test")

# From environment variables
config = ABACClientConfig.from_env(prefix="ABAC_")
# Reads: ABAC_MODE, ABAC_BASE_URL, ABAC_REALM, ABAC_TIMEOUT,
#         ABAC_CHUNK_SIZE, ABAC_MAX_CONCURRENT
# For dynamic realm, set realm to a callable after construction:
# config.realm = _resolve_realm
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mode` | `"http" \| "db"` | `"http"` | Connection mode |
| `base_url` | `str` | `""` | Base URL of the ABAC engine |
| `realm` | `str \| Callable[[], str]` | `""` | Static string or callable for dynamic realm |
| `timeout` | `int` | `30` | HTTP request timeout (seconds); forwarded to the SDK HTTP client |
| `chunk_size` | `int` | `500` | Batch processing chunk size |
| `max_concurrent` | `int` | `5` | Max concurrent HTTP requests per batch |
| `cache_enabled` | `bool` | `True` | **Reserved** — SDK does not yet implement client-side caching; has no effect |
| `cache_ttl` | `int` | `300` | **Reserved** — no effect |
| `cache_maxsize` | `int` | `1000` | **Reserved** — no effect |

### Runtime Adapter

```python
from cqrs_ddd_access_control.contrib.stateful_abac import StatefulABACAdapter

adapter = StatefulABACAdapter(config=config)

# adapter implements IAuthorizationPort
authorized_ids = await adapter.check_access(
    access_token="...",
    resource_type="order",
    action="read",
    resource_ids=["ord-1", "ord-2"],
)

# Single-query auth
auth_filter = await adapter.get_authorization_filter(
    access_token="...",
    resource_type="order",
    action="read",
    field_mapping=my_mapping,
)
# Returns AuthorizationFilter with filter_specification
```

**Per-realm client caching:** The adapter maintains a `dict[str, client]` cache. When `realm` is a callable, each unique realm value gets its own SDK client instance. This supports multi-tenant deployments where each tenant has an isolated ABAC realm.

### Admin Adapter

```python
from cqrs_ddd_access_control.contrib.stateful_abac import StatefulABACAdminAdapter

admin = StatefulABACAdminAdapter(config=config)

# admin implements IAuthorizationAdminPort
await admin.create_resource_type("order", is_public=False)
await admin.create_action("read")
await admin.register_resource("order", "ord-1", attributes={"status": "pending"})
await admin.create_acl(
    resource_type="order",
    action="read",
    role_name="viewer",
)

# Specification-based ACL
await admin.create_acl_from_specification(
    resource_type="order",
    action="read",
    role_name="analyst",
    specification_dsl={"op": "eq", "attr": "region", "val": "EU"},
    field_mapping=my_mapping,
)

# Realm provisioning (creates realm + "elevation" type + "admin" action)
await admin.ensure_realm(idp_config={"issuer": "https://idp.example.com"})
```

### ConditionConverter

Bidirectional conversion between ABAC condition DSL and `BaseSpecification` objects.

```python
from cqrs_ddd_access_control.contrib.stateful_abac import ConditionConverter

converter = ConditionConverter(field_mapping=my_mapping)
```

**DSL → Specification** (used by `get_authorization_filter`):

```python
conditions = AuthorizationConditionsResult(
    filter_type="conditions",
    conditions_dsl={
        "op": "and",
        "conditions": [
            {"op": "eq", "attr": "order_status", "val": "pending", "source": "resource"},
            {"op": "in", "attr": "external_id", "val": ["1", "2"], "source": "resource"},
        ],
    },
)
auth_filter = converter.dsl_to_specification(conditions)
# auth_filter.filter_specification:
#   And(Eq("status", "pending"), In("id", [1, 2]))
#   ↑ "order_status" → "status" (reverse mapping)
#   ↑ "external_id" → "id" (external_id_field)
#   ↑ values cast via external_id_cast
```

**Specification → DSL** (used by `create_acl_from_specification`):

```python
spec_dict = {"op": "eq", "attr": "status", "val": "pending"}
dsl = converter.specification_to_dsl(spec)
# {"op": "eq", "attr": "order_status", "val": "pending", "source": "resource"}
#   ↑ "status" → "order_status" (forward mapping)
#   ↑ "source": "resource" added for ABAC engine
```

**Conversion details:**

| Feature | DSL → Spec (reverse) | Spec → DSL (forward) |
|---------|---------------------|---------------------|
| Field names | ABAC attr → app field | app field → ABAC attr |
| `external_id` | Maps to `external_id_field`, casts values | Maps from `external_id_field` |
| `source` key | Stripped | Added as `"resource"` |
| Logical ops | Recursed, `source` stripped | Recursed |
| Spatial ops | `st_dwithin` → `dwithin` | `dwithin` → `st_dwithin` |

---

## Configuration Reference

### AuthorizationConfig

Used by `AuthorizationMiddleware`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `resource_type` | `str \| None` | `None` | Static resource type |
| `resource_type_attr` | `str \| None` | `None` | Dotted path to extract resource type from message |
| `required_actions` | `list[str]` | `[]` | Actions to check |
| `action_quantifier` | `"all" \| "any"` | `"all"` | How to combine action checks |
| `list_quantifier` | `"all" \| "any"` | `"all"` | How to combine list-level checks |
| `resource_id_attr` | `str \| None` | `None` | Dotted path to resource ID(s) in message |
| `query_options_attr` | `str \| None` | `None` | Dotted path to query options |
| `result_entities_attr` | `str \| None` | `None` | Dotted path to entities in result (enables post-filter) |
| `entity_id_attr` | `str` | `"id"` | ID attribute on result entities |
| `fail_silently` | `bool` | `False` | True = drop denied items silently instead of raising |
| `deny_anonymous` | `bool` | `False` | True = reject unauthenticated requests |
| `auth_context_provider` | `Callable \| None` | `None` | `(message) → dict \| None` for request context |

### SpecificationAuthConfig

Used by `SpecificationAuthMiddleware`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `resource_type` | `str` | `""` | Resource type |
| `action` | `str` | `"read"` | Action to check |
| `query_options_attr` | `str` | `"query_options"` | Attribute name on the message |
| `auth_context_provider` | `Callable \| None` | `None` | `(message) → dict \| None` |

### PermittedActionsConfig

Used by `PermittedActionsMiddleware`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `resource_type` | `str` | `""` | Resource type |
| `result_entities_attr` | `str` | `"items"` | Attribute on result containing entity list |
| `entity_id_attr` | `str` | `"id"` | ID attribute on entities |
| `permitted_actions_attr` | `str` | `"permitted_actions"` | Attribute to set on entities |
| `include_type_level` | `bool` | `False` | Merge type-level permissions into per-entity |
| `auth_context_provider` | `Callable \| None` | `None` | `(message) → dict \| None` |

### ResourceTypeConfig

Registration metadata for `@register_access_entity` / manual registry.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | required | Resource type name |
| `field_mapping` | `FieldMapping` | required | Field name mappings |
| `is_public` | `bool` | `False` | Default public visibility |
| `auto_register_resources` | `bool` | `True` | Auto-sync resources to engine |
| `entity_class` | `type \| None` | `None` | Entity class (set by decorator) |
| `actions` | `list[str]` | `[]` | Valid actions |

### FieldMapping

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mappings` | `dict[str, str]` | `{}` | App field → ABAC attribute |
| `external_id_field` | `str` | `"external_id"` | App field that maps to ABAC `external_id` |
| `external_id_cast` | `Callable` | `str` | How to cast external_id values |

---

## Testing

### In-memory testing

Use in-memory adapters for unit tests. Implement the ports with simple dict-backed storage:

```python
from cqrs_ddd_access_control import IAuthorizationPort, CheckAccessBatchResult, CheckAccessItem

class InMemoryAuthorizationPort(IAuthorizationPort):
    def __init__(self):
        self._acls: dict[tuple[str, str], set[str]] = {}

    async def check_access(self, access_token, resource_type, action,
                           resource_ids=None, auth_context=None, role_names=None) -> list[str]:
        key = (resource_type, action)
        allowed = self._acls.get(key, set())
        if resource_ids is None:
            return list(allowed) if allowed else []
        return [rid for rid in resource_ids if rid in allowed]

    # ... implement remaining methods
```

### Testing evaluators in isolation

```python
from cqrs_ddd_access_control import RBACEvaluator, AuthorizationContext
from cqrs_ddd_identity import Principal

async def test_rbac_allows_admin():
    rbac = RBACEvaluator(role_permissions={"admin": {"order:read"}})
    principal = Principal(user_id="u1", roles=frozenset({"admin"}))
    ctx = AuthorizationContext(resource_type="order", action="read")
    decision = await rbac.evaluate(principal, ctx)
    assert decision.allowed
    assert decision.evaluator == "rbac"

async def test_rbac_abstains_on_missing():
    rbac = RBACEvaluator(role_permissions={"admin": {"order:read"}})
    principal = Principal(user_id="u1", roles=frozenset({"viewer"}))
    ctx = AuthorizationContext(resource_type="order", action="delete")
    decision = await rbac.evaluate(principal, ctx)
    assert not decision.allowed
    assert decision.reason == "abstain"
```

### Testing PEP deny-wins

```python
from cqrs_ddd_access_control import PolicyEnforcementPoint

async def test_deny_wins():
    allow_eval = MockEvaluator(allowed=True, reason="ok")
    deny_eval = MockEvaluator(allowed=False, reason="denied explicitly")
    pep = PolicyEnforcementPoint(evaluators=[allow_eval, deny_eval])
    decision = await pep.evaluate(principal, context)
    assert not decision.allowed
    assert decision.reason == "denied explicitly"
```

### Testing middleware

```python
async def test_authorization_middleware_denies():
    port = InMemoryAuthorizationPort()
    mw = AuthorizationMiddleware(
        authorization_port=port,
        config=AuthorizationConfig(
            resource_type="order",
            required_actions=["read"],
            resource_id_attr="order_id",
        ),
    )
    message = MyCommand(order_id="ord-1")

    with pytest.raises(PermissionDeniedError) as exc_info:
        await mw(message, lambda m: m)

    assert exc_info.value.code == "PERMISSION_DENIED"
```

### Architecture tests

Use `pytest-archon` to enforce layer boundaries:

```python
def test_access_control_does_not_import_infrastructure():
    """Access control package must not depend on infrastructure packages."""
    from pytest_archon import archrule

    archrule("access_control_isolation")
        .match("cqrs_ddd_access_control.*")
        .should_not_import("sqlalchemy.*", "redis.*")
        .check("cqrs_ddd_access_control")
```
