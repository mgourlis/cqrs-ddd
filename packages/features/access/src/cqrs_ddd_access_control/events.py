"""Access-control domain events.

Request events are emitted by command handlers and processed by priority
event handlers in the same UoW transaction. Completion events are appended
to the event store by the priority handlers and drive undo/redo tracking.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from cqrs_ddd_core import DomainEvent

from .models import AccessRule

# ---------------------------------------------------------------------------
# Request events (command handler → priority handler)
# ---------------------------------------------------------------------------


class ACLGrantRequested(DomainEvent):
    """Request to grant access — processed by a priority event handler."""

    resource_type: str
    resource_id: str | None = None
    access_rules: list[AccessRule] = Field(default_factory=list)


class ACLRevokeRequested(DomainEvent):
    """Request to revoke access by compound key."""

    resource_type: str
    action: str
    principal_name: str | None = None
    role_name: str | None = None
    resource_id: str | None = None


class ResourceTypePublicSetRequested(DomainEvent):
    """Request to toggle type-level public access."""

    resource_type: str
    is_public: bool = True


# ---------------------------------------------------------------------------
# Completion events (priority handler → event store)
# ---------------------------------------------------------------------------


class ACLGranted(DomainEvent):
    """ACL grant completed — carries admin-port result for undo tracking."""

    resource_type: str
    action: str
    principal_name: str | None = None
    role_name: str | None = None
    resource_id: str | None = None
    acl_id: int | str | None = None
    conditions: dict[str, Any] | None = None
    specification_dsl: dict[str, Any] | None = None
    previous_state: dict[str, Any] | None = None


class ACLRevoked(DomainEvent):
    """ACL revoke completed — carries previous state for undo."""

    resource_type: str
    action: str
    principal_name: str | None = None
    role_name: str | None = None
    resource_id: str | None = None
    previous_state: dict[str, Any] | None = None


class ResourceTypePublicSet(DomainEvent):
    """Resource type public flag changed — carries previous value for undo."""

    resource_type: str
    is_public: bool
    previous_public: bool | None = None
