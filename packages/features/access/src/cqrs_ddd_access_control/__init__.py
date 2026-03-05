"""cqrs-ddd-access-control — authorization layer for cqrs-ddd applications.

Public API re-exports for convenient usage::

    from cqrs_ddd_access_control import (
        AuthorizationMiddleware,
        PermissionDeniedError,
        PolicyEnforcementPoint,
        ...
    )
"""

from __future__ import annotations

from contextlib import suppress

# ---------------------------------------------------------------------------
# Priority Event Handlers
# ---------------------------------------------------------------------------
from .acl_handlers import (
    ACLGrantRequestedHandler,
    ACLRevokeRequestedHandler,
    register_priority_acl_handlers,
)
from .acl_handlers import (
    ResourceTypePublicSetHandler as ResourceTypePublicSetEventHandler,
)

# ---------------------------------------------------------------------------
# Authorizable Entity
# ---------------------------------------------------------------------------
from .authorizable import (
    AuthorizableEntity,
    ResourceTypeRegistry,
    get_access_config,
    register_access_entity,
)

# ---------------------------------------------------------------------------
# Sync, Decorators, Cache, Elevation
# ---------------------------------------------------------------------------
from .cache import PermissionDecisionCache

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
from .commands import GrantACL, GrantOwnershipACL, RevokeACL, SetResourcePublic
from .decorators import (
    OwnershipRequirement,
    PermissionRequirement,
    Qualifier,
    RoleRequirement,
    authorization,
    get_authorization_config,
    get_ownership_requirement,
    get_permission_requirement,
    get_role_requirement,
    requires_owner,
    requires_permission,
    requires_role,
)
from .elevation import verify_elevation

# ---------------------------------------------------------------------------
# Evaluators
# ---------------------------------------------------------------------------
from .evaluators import IPermissionEvaluator
from .evaluators.abac import ABACConnector
from .evaluators.acl import ACLEvaluator
from .evaluators.ownership import OwnershipEvaluator
from .evaluators.rbac import RBACEvaluator

# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
from .events import (
    ACLGranted,
    ACLGrantRequested,
    ACLRevoked,
    ACLRevokeRequested,
    ResourceTypePublicSet,
    ResourceTypePublicSetRequested,
)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
from .exceptions import (
    AccessControlError,
    ACLError,
    ElevationRequiredError,
    InsufficientRoleError,
    PermissionDeniedError,
)

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
from .handlers import (
    GrantACLHandler,
    GrantOwnershipACLHandler,
    RevokeACLHandler,
    SetResourcePublicHandler,
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
from .middleware import (
    AuthorizationMiddleware,
    DecoratorAuthorizationMiddleware,
    PermittedActionsMiddleware,
    SpecificationAuthMiddleware,
)

# ---------------------------------------------------------------------------
# Models / Value Objects
# ---------------------------------------------------------------------------
from .models import (
    AccessRule,
    AuthorizationConditionsResult,
    AuthorizationConfig,
    AuthorizationContext,
    AuthorizationDecision,
    AuthorizationFilter,
    CheckAccessBatchResult,
    CheckAccessItem,
    FieldMapping,
    GetPermittedActionsItem,
    PermittedActionsConfig,
    ResourceTypeConfig,
    SpecificationAuthConfig,
)

# ---------------------------------------------------------------------------
# Policy Enforcement Point
# ---------------------------------------------------------------------------
from .pep import PolicyEnforcementPoint

# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------
from .ports import (
    IAuthorizationAdminPort,
    IAuthorizationPort,
    IOwnershipResolver,
    IPermissionCache,
    IResourceTypeRegistry,
)

# ---------------------------------------------------------------------------
# Step-up Authentication
# ---------------------------------------------------------------------------
from .step_up import (
    GrantTemporaryElevation,
    GrantTemporaryElevationHandler,
    GrantTemporaryElevationResult,
    MFAChallengeVerified,
    ResumeSensitiveOperation,
    ResumeSensitiveOperationHandler,
    ResumeSensitiveOperationResult,
    RevokeElevation,
    RevokeElevationHandler,
    RevokeElevationResult,
    SensitiveOperationCompleted,
    SensitiveOperationRequested,
    TemporaryElevationGranted,
    TemporaryElevationRevoked,
    serialize_command,
)
from .sync import ResourceSyncService

with suppress(ImportError):
    from .step_up import StepUpAuthenticationSaga, StepUpState

__all__ = [
    # Exceptions
    "AccessControlError",
    "PermissionDeniedError",
    "InsufficientRoleError",
    "ACLError",
    "ElevationRequiredError",
    # Models
    "AuthorizationContext",
    "AuthorizationDecision",
    "CheckAccessItem",
    "GetPermittedActionsItem",
    "CheckAccessBatchResult",
    "AuthorizationConditionsResult",
    "AuthorizationFilter",
    "AccessRule",
    "FieldMapping",
    "ResourceTypeConfig",
    "AuthorizationConfig",
    "SpecificationAuthConfig",
    "PermittedActionsConfig",
    # Ports
    "IAuthorizationPort",
    "IAuthorizationAdminPort",
    "IOwnershipResolver",
    "IPermissionCache",
    "IResourceTypeRegistry",
    # Evaluators
    "IPermissionEvaluator",
    "RBACEvaluator",
    "ACLEvaluator",
    "OwnershipEvaluator",
    "ABACConnector",
    # PEP
    "PolicyEnforcementPoint",
    # Authorizable
    "AuthorizableEntity",
    "ResourceTypeRegistry",
    "register_access_entity",
    "get_access_config",
    # Commands
    "GrantACL",
    "RevokeACL",
    "SetResourcePublic",
    "GrantOwnershipACL",
    # Events
    "ACLGrantRequested",
    "ACLRevokeRequested",
    "ResourceTypePublicSetRequested",
    "ACLGranted",
    "ACLRevoked",
    "ResourceTypePublicSet",
    # Handlers
    "GrantACLHandler",
    "RevokeACLHandler",
    "SetResourcePublicHandler",
    "GrantOwnershipACLHandler",
    # Priority Event Handlers
    "ACLGrantRequestedHandler",
    "ACLRevokeRequestedHandler",
    "ResourceTypePublicSetEventHandler",
    "register_priority_acl_handlers",
    # Middleware
    "AuthorizationMiddleware",
    "DecoratorAuthorizationMiddleware",
    "SpecificationAuthMiddleware",
    "PermittedActionsMiddleware",
    # Sync, Decorators, Cache, Elevation
    "ResourceSyncService",
    "PermissionDecisionCache",
    "requires_permission",
    "requires_role",
    "requires_owner",
    "authorization",
    "PermissionRequirement",
    "RoleRequirement",
    "OwnershipRequirement",
    "Qualifier",
    "get_permission_requirement",
    "get_role_requirement",
    "get_ownership_requirement",
    "get_authorization_config",
    "verify_elevation",
    # Step-up Authentication
    "SensitiveOperationRequested",
    "MFAChallengeVerified",
    "SensitiveOperationCompleted",
    "TemporaryElevationGranted",
    "TemporaryElevationRevoked",
    "GrantTemporaryElevation",
    "RevokeElevation",
    "ResumeSensitiveOperation",
    "GrantTemporaryElevationResult",
    "RevokeElevationResult",
    "ResumeSensitiveOperationResult",
    "GrantTemporaryElevationHandler",
    "RevokeElevationHandler",
    "ResumeSensitiveOperationHandler",
    "serialize_command",
    "StepUpAuthenticationSaga",
    "StepUpState",
]
