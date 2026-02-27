"""Keycloak Identity Provider adapter.

Implements IIdentityProvider for Keycloak authentication using
python-keycloak for OpenID Connect operations and joserfc for JWT handling.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

from joserfc import jwt
from joserfc.errors import (
    BadSignatureError,
    DecodeError,
    ExpiredTokenError,
    InvalidClaimError,
    MissingClaimError,
)
from joserfc.jwk import import_key
from keycloak import KeycloakOpenID

from ..exceptions import AuthenticationError, InvalidTokenError
from ..ports import IIdentityProvider, TokenResponse
from ..principal import Principal

# ═══════════════════════════════════════════════════════════════
# KEYCLOAK-SPECIFIC ENUMS
# ═══════════════════════════════════════════════════════════════


class GroupPathStrategy(Enum):
    """How to convert Keycloak group paths to role names.

    Example group path: /web/admin/editor

    Strategies:
        - FULL_PATH: → "web/admin/editor" (default, preserves hierarchy)
        - LAST_SEGMENT: → "editor" (simple, loses context)
        - ALL_SEGMENTS: → ["web", "admin", "editor"] (flexible, adds multiple roles)
    """

    FULL_PATH = "full_path"
    LAST_SEGMENT = "last_segment"
    ALL_SEGMENTS = "all_segments"


# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class KeycloakConfig:
    """Configuration for Keycloak adapter.

    Attributes:
        server_url: Keycloak server URL (e.g., "https://keycloak.example.com").
        realm: Keycloak realm name.
        client_id: OAuth2 client ID.
        client_secret: OAuth2 client secret (optional for public clients).
        username_claim: Claim to use for username (default: preferred_username).
        email_claim: Claim to use for email (default: email).
        groups_claim: Claim containing groups (default: groups).
        tenant_id_claim: Custom claim for tenant ID (default: tenant_id).
        use_realm_as_tenant: Use realm name as tenant ID fallback.
        phone_number_claim: Claim for phone number.
        verify: Verify SSL certificates.
        merge_groups_as_roles: Convert groups to roles.
        group_path_strategy: How to convert group paths to role names.
        group_prefix: Optional prefix for group-derived roles.
    """

    server_url: str
    realm: str
    client_id: str
    client_secret: str | None = None

    # Claim mapping
    username_claim: str = "preferred_username"
    email_claim: str = "email"
    groups_claim: str = "groups"
    tenant_id_claim: str = "tenant_id"
    use_realm_as_tenant: bool = False
    phone_number_claim: str = "phone_number"

    # Token validation
    verify: bool = True

    # Group handling (role unification)
    merge_groups_as_roles: bool = True
    group_path_strategy: GroupPathStrategy = GroupPathStrategy.FULL_PATH
    group_prefix: str = ""


# ═══════════════════════════════════════════════════════════════
# KEYCLOAK IDENTITY PROVIDER
# ═══════════════════════════════════════════════════════════════


class KeycloakIdentityProvider(IIdentityProvider):
    """Keycloak implementation of IIdentityProvider.

    Uses python-keycloak for OpenID Connect operations and
    joserfc for JWT validation.

    Example:
        ```python
        config = KeycloakConfig(
            server_url="https://keycloak.example.com",
            realm="my-realm",
            client_id="my-app",
            client_secret="secret",
        )
        provider = KeycloakIdentityProvider(config)

        # Direct grant authentication
        tokens = await provider.authenticate("user", "password")

        # Resolve token to Principal
        principal = await provider.resolve(tokens.access_token)
        ```
    """

    def __init__(self, config: KeycloakConfig) -> None:
        """Initialize Keycloak adapter.

        Args:
            config: Keycloak configuration.
        """
        self.config = config
        self._keycloak = KeycloakOpenID(
            server_url=config.server_url,
            realm_name=config.realm,
            client_id=config.client_id,
            client_secret_key=config.client_secret,
            verify=config.verify,
        )
        self._public_key_pem: str | None = None
        self._public_key_jwk: Any = None  # joserfc Key (RSAKey) for decode

    async def authenticate(self, username: str, password: str) -> TokenResponse:
        """Authenticate user with username/password via direct grant.

        Args:
            username: User's username or email.
            password: User's password.

        Returns:
            TokenResponse with access/refresh tokens.

        Raises:
            AuthenticationError: If credentials are invalid.
        """
        try:
            token_data = self._keycloak.token(username, password)

            return TokenResponse(
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token"),
                token_type=token_data.get("token_type", "Bearer"),
                expires_in=token_data.get("expires_in", 3600),
                scope=token_data.get("scope"),
                id_token=token_data.get("id_token"),
            )
        except Exception as e:
            raise AuthenticationError(str(e)) from e

    async def resolve(self, token: str) -> Principal:
        """Resolve a JWT access token to a Principal.

        Args:
            token: JWT access token.

        Returns:
            Principal value object with user identity.

        Raises:
            InvalidTokenError: If token is invalid or expired.
        """
        try:
            public_key = self._get_public_key()

            decoded = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
            )
            # joserfc: validate exp (required); optionally validate aud when present
            claims_registry = jwt.JWTClaimsRegistry(exp={"essential": True})
            claims_registry.validate(decoded.claims)
            aud = decoded.claims.get("aud")
            if aud is not None:
                allowed = [self.config.client_id, "account"]
                token_auds = [aud] if isinstance(aud, str) else aud
                if not any(a in token_auds for a in allowed):
                    # Strict: require client_id when aud is present
                    if self.config.client_id not in token_auds:
                        raise InvalidTokenError("audience not allowed")
            payload = decoded.claims

            principal = self._payload_to_principal(payload)
            # When the token omits preferred_username (e.g. some admin-cli configs), fill
            # from userinfo so principal.username is set
            if not principal.username:
                try:
                    user_info = await self.get_user_info(token)
                    if isinstance(user_info, bytes):
                        user_info = json.loads(user_info.decode("utf-8"))
                    ui_username = (
                        user_info.get("preferred_username")
                        or user_info.get("username")
                        or user_info.get("email")
                        or user_info.get("sub")
                        or principal.user_id
                    )
                    ui_user_id = user_info.get("sub") or principal.user_id
                    if ui_username or ui_user_id:
                        principal = Principal(
                            user_id=principal.user_id or str(ui_user_id or ""),
                            username=str(
                                ui_username or principal.user_id or ui_user_id or ""
                            ),
                            roles=principal.roles,
                            permissions=principal.permissions,
                            claims=principal.claims,
                            tenant_id=principal.tenant_id,
                            mfa_verified=principal.mfa_verified,
                            auth_method=principal.auth_method,
                            session_id=principal.session_id,
                            expires_at=principal.expires_at,
                        )
                except Exception:
                    pass
            return principal

        except (DecodeError, BadSignatureError) as e:
            raise InvalidTokenError(str(e)) from e
        except (ExpiredTokenError, InvalidClaimError, MissingClaimError) as e:
            raise InvalidTokenError(str(e)) from e
        except Exception as e:
            raise InvalidTokenError(str(e)) from e

    async def refresh(self, refresh_token: str) -> TokenResponse:
        """Refresh tokens using a refresh token.

        Args:
            refresh_token: Valid refresh token.

        Returns:
            New TokenResponse with fresh tokens.

        Raises:
            AuthenticationError: If refresh token is invalid/expired.
        """
        try:
            token_data = self._keycloak.refresh_token(refresh_token)

            return TokenResponse(
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token"),
                token_type=token_data.get("token_type", "Bearer"),
                expires_in=token_data.get("expires_in", 3600),
                scope=token_data.get("scope"),
                id_token=token_data.get("id_token"),
            )
        except Exception as e:
            raise AuthenticationError(str(e)) from e

    async def logout(self, token: str) -> None:
        """Terminate the IdP session by revoking the refresh token.

        Args:
            token: Refresh token to invalidate.
        """
        try:
            self._keycloak.logout(token)
        except Exception:
            # Logout is best-effort
            pass

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        """Get user info from Keycloak's userinfo endpoint.

        Args:
            access_token: Valid access token.

        Returns:
            User profile information.

        Raises:
            InvalidTokenError: If token is invalid.
        """
        try:
            return cast("dict[str, Any]", self._keycloak.userinfo(access_token))
        except Exception as e:
            raise InvalidTokenError(str(e)) from e

    def _get_public_key(self) -> Any:
        """Get Keycloak's public key for JWT verification (joserfc Key for decode)."""
        if self._public_key_jwk is None:
            if self._public_key_pem is None:
                public_key_raw = self._keycloak.public_key()
                if public_key_raw is None:
                    raise InvalidTokenError("Failed to retrieve Keycloak public key")
                self._public_key_pem = (
                    "-----BEGIN PUBLIC KEY-----\n"
                    + public_key_raw
                    + "\n-----END PUBLIC KEY-----"
                )
            self._public_key_jwk = import_key(self._public_key_pem, "RSA")
        return self._public_key_jwk

    def _payload_to_principal(self, payload: dict[str, Any]) -> Principal:
        """Convert JWT payload to Principal.

        Handles Keycloak-specific claim names, structures, and
        role unification (groups as roles).
        """
        # Extract roles from realm_access and resource_access
        roles: set[str] = set()

        # 1. Realm roles from realm_access
        realm_access = payload.get("realm_access", {})
        for role_name in realm_access.get("roles", []):
            roles.add(str(role_name))

        # 2. Client roles from resource_access
        resource_access = payload.get("resource_access", {})
        for client, client_data in resource_access.items():
            for role_name in client_data.get("roles", []):
                # Include client prefix in name if not our client
                if client == self.config.client_id:
                    roles.add(str(role_name))
                else:
                    roles.add(f"{client}:{role_name}")

        # 3. Groups - both as raw groups and optionally as roles
        raw_groups: list[str] = payload.get("groups", [])

        if self.config.merge_groups_as_roles:
            for group_path in raw_groups:
                group_roles = self._group_path_to_roles(
                    group_path,
                    strategy=self.config.group_path_strategy,
                    prefix=self.config.group_prefix,
                )
                roles.update(group_roles)

        # 4. Resolve Tenant ID
        tenant_id = payload.get(self.config.tenant_id_claim)
        if not tenant_id and self.config.use_realm_as_tenant:
            tenant_id = self.config.realm

        # 5. Build attributes and ensure tenant_id is included
        attributes = payload.copy()
        if tenant_id:
            attributes["tenant_id"] = tenant_id

        # Extract username (Keycloak may use preferred_username, username, or email)
        username = (
            payload.get(self.config.username_claim)
            or payload.get("preferred_username")
            or payload.get("username")
            or payload.get("email")
            or payload.get("sub", "")
        )

        return Principal(
            user_id=payload.get("sub", ""),
            username=str(username) if username else "",
            roles=frozenset(roles),
            permissions=frozenset(),  # Permissions derived from roles
            claims=attributes,
            tenant_id=str(tenant_id) if tenant_id else None,
            mfa_verified=payload.get("acr", "") == "mfa",
            auth_method="oauth2",
        )

    def _group_path_to_roles(
        self,
        group_path: str,
        strategy: GroupPathStrategy,
        prefix: str = "",
    ) -> set[str]:
        """Convert Keycloak group path to one or more roles.

        Args:
            group_path: Full group path, e.g., "/web/admin/editor".
            strategy: How to handle the path.
            prefix: Optional prefix for role names.

        Returns:
            Set of role names.
        """
        path = group_path.strip("/")
        segments = path.split("/") if path else []

        if not segments:
            return set()

        roles: set[str] = set()

        if strategy == GroupPathStrategy.FULL_PATH:
            # /web/admin/editor → "web/admin/editor"
            name = f"{prefix}{path}" if prefix else path
            roles.add(name)

        elif strategy == GroupPathStrategy.LAST_SEGMENT:
            # /web/admin/editor → "editor"
            name = f"{prefix}{segments[-1]}" if prefix else segments[-1]
            roles.add(name)

        elif strategy == GroupPathStrategy.ALL_SEGMENTS:
            # /web/admin/editor → ["web", "admin", "editor"]
            for segment in segments:
                name = f"{prefix}{segment}" if prefix else segment
                roles.add(name)

        return roles

    def clear_key_cache(self) -> None:
        """Clear cached public key. Call this if keys are rotated."""
        self._public_key_pem = None
        self._public_key_jwk = None

    def requires_otp(self, claims: dict[str, Any]) -> bool:
        """Check if Keycloak requires OTP based on token claims.

        Note: In Keycloak, this can be detected if the 'acr' claim
        is not at the level required by the policy, or if specific
        MFA flags are present in the access token.
        """
        # Check acr claim or otp_required flag
        return claims.get("acr") == "mfa" or claims.get("otp_required") is True
