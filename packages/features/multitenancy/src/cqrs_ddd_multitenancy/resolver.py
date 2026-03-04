"""Tenant resolver protocols and strategies.

Provides multiple strategies for resolving the current tenant from
different sources: headers, JWT claims, subdomains, paths, etc.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

__all__ = [
    "ITenantResolver",
    "HeaderResolver",
    "JwtClaimResolver",
    "SubdomainResolver",
    "PathResolver",
    "CompositeResolver",
    "StaticResolver",
    "CallableResolver",
]


@runtime_checkable
class ITenantResolver(Protocol):
    """Protocol for tenant resolution strategies.

    Implementations extract tenant identifiers from various sources
    such as HTTP headers, JWT claims, subdomains, URL paths, etc.

    The resolve method receives the current message (command/query)
    or request context and returns the tenant ID if available.
    """

    async def resolve(self, message: Any) -> str | None:
        """Resolve the tenant ID from the given message/context.

        Args:
            message: The incoming message, request, or context object.
                     The type depends on where the resolver is used:
                     - CQRS middleware: Command or Query object
                     - FastAPI middleware: Request object
                     - Background jobs: Job context

        Returns:
            The resolved tenant ID, or None if it cannot be determined.
        """
        ...


class HeaderResolver:
    """Resolve tenant from HTTP headers.

    Reads the tenant ID from a specified header, typically X-Tenant-ID.

    Attributes:
        header_name: The name of the header containing the tenant ID.
        required: Whether to raise an error if the header is missing.

    Example:
        ```python
        resolver = HeaderResolver(header_name="X-Tenant-ID")
        tenant_id = await resolver.resolve(request)
        ```
    """

    __slots__ = ("_header_name", "_required")

    def __init__(
        self,
        header_name: str = "X-Tenant-ID",
        *,
        required: bool = False,
    ) -> None:
        self._header_name = header_name
        self._required = required

    @property
    def header_name(self) -> str:
        """The header name being used for resolution."""
        return self._header_name

    @property
    def required(self) -> bool:
        """Whether the header is required."""
        return self._required

    async def resolve(self, message: Any) -> str | None:
        """Resolve tenant from the configured header.

        Args:
            message: Object with headers attribute (dict-like or object).

        Returns:
            The tenant ID from the header, or None.
        """
        headers = self._extract_headers(message)
        if headers is None:
            return None

        tenant_id = self._get_header_value(headers, self._header_name)
        if tenant_id:
            return tenant_id.strip()

        return None

    def _extract_headers(self, message: Any) -> Any:
        """Extract headers from various message types."""
        # FastAPI/Starlette Request
        if hasattr(message, "headers"):
            return message.headers

        # Dict-like with headers key
        if isinstance(message, dict):
            headers = message.get("headers")
            if headers is not None:
                return headers
            # Check for direct header key
            return message

        # Object with metadata/attributes
        if hasattr(message, "metadata"):
            metadata = message.metadata
            if isinstance(metadata, dict):
                return metadata

        return None

    def _get_header_value(self, headers: Any, name: str) -> str | None:
        """Get header value, handling case-insensitivity."""
        if hasattr(headers, "get"):
            # Try exact match first
            value = headers.get(name)
            if value is not None:
                return str(value)
            # Try lowercase
            value = headers.get(name.lower())
            if value is not None:
                return str(value)
        return None


class JwtClaimResolver:
    """Resolve tenant from JWT claims or Principal object.

    This resolver integrates with the identity package by reading
    the tenant_id from a Principal object or JWT claims dictionary.

    Attributes:
        claim_name: The name of the JWT claim containing the tenant ID.
        principal_attribute: The attribute name on Principal (default: tenant_id).

    Example:
        ```python
        # From Principal object (requires identity package)
        resolver = JwtClaimResolver()

        # From raw JWT claims
        resolver = JwtClaimResolver(claim_name="custom_tenant")
        ```
    """

    __slots__ = ("_claim_name", "_principal_attribute")

    def __init__(
        self,
        claim_name: str = "tenant_id",
        *,
        principal_attribute: str = "tenant_id",
    ) -> None:
        self._claim_name = claim_name
        self._principal_attribute = principal_attribute

    @property
    def claim_name(self) -> str:
        """The JWT claim name being used."""
        return self._claim_name

    async def resolve(self, message: Any) -> str | None:
        """Resolve tenant from Principal or JWT claims.

        Args:
            message: Principal object, JWT claims dict, or object with
                     principal/claims attribute.

        Returns:
            The tenant ID from claims/principal, or None.
        """
        # Try Principal object first (from identity package)
        principal = self._get_principal(message)
        if principal is not None:
            tenant_id = getattr(principal, self._principal_attribute, None)
            if tenant_id is not None:
                return str(tenant_id)

        # Try claims dictionary
        claims = self._get_claims(message)
        if claims is not None:
            tenant_id = claims.get(self._claim_name) or claims.get("tenant")
            if tenant_id is not None:
                return str(tenant_id)

        return None

    def _get_principal(self, message: Any) -> Any:
        """Extract Principal from various sources."""
        # Direct Principal object
        if hasattr(message, self._principal_attribute):
            return message

        # Object with principal attribute
        if hasattr(message, "principal"):
            return message.principal

        # Dict with principal key
        if isinstance(message, dict) and "principal" in message:
            return message["principal"]

        return None

    def _get_claims(self, message: Any) -> dict[str, Any] | None:
        """Extract claims dictionary from various sources."""
        # Direct claims dict
        if isinstance(message, dict):
            # Check if it looks like claims (has typical claim keys OR the configured claim_name)
            typical_claim_keys = ("sub", "iss", "aud", "tenant_id")
            if (
                any(k in message for k in typical_claim_keys)
                or self._claim_name in message
            ):
                return message

        # Object with claims attribute
        if hasattr(message, "claims"):
            claims = message.claims
            if isinstance(claims, dict):
                return claims

        return None


class SubdomainResolver:
    """Resolve tenant from URL subdomain.

    Extracts the tenant ID from the first subdomain component.
    For example: tenant123.app.com → tenant123

    Attributes:
        domain_suffix: Expected domain suffix for validation (optional).
        pattern: Regex pattern for extracting subdomain.

    Example:
        ```python
        resolver = SubdomainResolver(domain_suffix=".app.com")
        # tenant.app.com → "tenant"
        # tenant-staging.app.com → "tenant-staging"
        ```
    """

    __slots__ = ("_domain_suffix", "_pattern")

    def __init__(
        self,
        domain_suffix: str | None = None,
        *,
        pattern: str | None = None,
    ) -> None:
        self._domain_suffix = domain_suffix
        # Pattern to extract first subdomain component
        self._pattern = pattern or r"^([a-zA-Z0-9][-a-zA-Z0-9]*)\."

    @property
    def domain_suffix(self) -> str | None:
        """The expected domain suffix."""
        return self._domain_suffix

    async def resolve(self, message: Any) -> str | None:
        """Resolve tenant from URL subdomain.

        Args:
            message: Request object with host/URL information.

        Returns:
            The tenant ID from subdomain, or None.
        """
        host = self._extract_host(message)
        if host is None:
            return None

        # Validate domain suffix if configured
        if self._domain_suffix and not host.endswith(self._domain_suffix):
            return None

        # Extract subdomain
        match = re.match(self._pattern, host)
        if match:
            subdomain = match.group(1)
            # Skip common non-tenant subdomains
            if subdomain not in ("www", "api", "app", "admin", "mail", "ftp"):
                return subdomain

        return None

    @staticmethod
    def _host_from_headers_obj(headers: Any) -> str | None:
        """Extract and strip port from a headers object (dict-like)."""
        host = headers.get("Host") or headers.get("host")
        return cast("str", host.split(":")[0]) if host else None

    @staticmethod
    def _host_from_dict(message: dict[str, Any]) -> str | None:
        """Extract host from a plain dict message (headers sub-key or direct key)."""
        headers = message.get("headers", {})
        host = headers.get("Host") or headers.get("host")
        if host:
            return cast("str", host.split(":")[0])
        host = message.get("host") or message.get("Host")
        return cast("str", host.split(":")[0]) if host else None

    def _extract_host(self, message: Any) -> str | None:
        """Extract host from various message types."""
        # FastAPI/Starlette Request: url.hostname takes priority
        if hasattr(message, "url") and message.url is not None:
            hostname = getattr(message.url, "hostname", None)
            if hostname:
                return cast("str", hostname)

        # Object with host attribute
        if hasattr(message, "host") and message.host is not None:
            return cast("str", message.host)

        # Object with headers attribute (e.g. Starlette Request without url match)
        if hasattr(message, "headers"):
            host = self._host_from_headers_obj(message.headers)
            if host:
                return host

        # Plain dict
        if isinstance(message, dict):
            return self._host_from_dict(message)

        return None


class PathResolver:
    """Resolve tenant from URL path.

    Extracts tenant ID from a path segment using a pattern.
    Default pattern: /tenants/{tenant_id}/...

    Attributes:
        pattern: Regex pattern with tenant_id capture group.
        prefix: URL prefix before tenant ID (e.g., "/tenants/").

    Example:
        ```python
        resolver = PathResolver(prefix="/tenants/")
        # /tenants/abc-123/orders → "abc-123"

        resolver = PathResolver(pattern=r"/t/([^/]+)")
        # /t/xyz-789/items → "xyz-789"
        ```
    """

    __slots__ = ("_pattern", "_prefix")

    def __init__(
        self,
        prefix: str = "/tenants/",
        *,
        pattern: str | None = None,
    ) -> None:
        self._prefix = prefix
        if pattern:
            self._pattern = re.compile(pattern)
        else:
            # Default pattern: prefix followed by tenant_id
            escaped_prefix = re.escape(prefix)
            self._pattern = re.compile(f"{escaped_prefix}([^/]+)")

    @property
    def prefix(self) -> str:
        """The URL prefix for tenant paths."""
        return self._prefix

    async def resolve(self, message: Any) -> str | None:
        """Resolve tenant from URL path.

        Args:
            message: Request object with path/URL information.

        Returns:
            The tenant ID from path, or None.
        """
        path = self._extract_path(message)
        if path is None:
            return None

        match = self._pattern.search(path)
        if match:
            return match.group(1)

        return None

    def _extract_path(self, message: Any) -> str | None:
        """Extract path from various message types."""
        # FastAPI/Starlette Request
        if hasattr(message, "url"):
            return cast("str", message.url.path)

        # Object with path attribute
        if hasattr(message, "path"):
            return cast("str", message.path)

        # Dict with path key
        if isinstance(message, dict):
            return cast("str | None", message.get("path"))

        return None


class CompositeResolver:
    """Resolve tenant by trying multiple resolvers in order.

    Returns the first non-None tenant ID from the configured resolvers.
    This allows fallback chains like: Header → JWT → Subdomain → Path.

    Attributes:
        resolvers: Sequence of resolvers to try in order.

    Example:
        ```python
        resolver = CompositeResolver([
            HeaderResolver("X-Tenant-ID"),
            JwtClaimResolver(),
            SubdomainResolver(".app.com"),
            PathResolver("/tenants/"),
        ])
        # Tries each in order until one returns a tenant ID
        ```
    """

    __slots__ = ("_resolvers",)

    def __init__(self, resolvers: Sequence[ITenantResolver]) -> None:
        if not resolvers:
            raise ValueError("CompositeResolver requires at least one resolver")
        self._resolvers = list(resolvers)

    @property
    def resolvers(self) -> list[ITenantResolver]:
        """The list of resolvers in priority order."""
        return list(self._resolvers)

    async def resolve(self, message: Any) -> str | None:
        """Try each resolver in order until one succeeds.

        Args:
            message: The message/request to resolve tenant from.

        Returns:
            The first non-None tenant ID, or None if all resolvers fail.
        """
        for resolver in self._resolvers:
            try:
                tenant_id = await resolver.resolve(message)
                if tenant_id is not None:
                    return tenant_id
            except Exception:
                # Continue to next resolver on error
                continue
        return None

    def add_resolver(self, resolver: ITenantResolver) -> CompositeResolver:
        """Add a resolver to the chain (returns new CompositeResolver).

        Args:
            resolver: The resolver to add at the end of the chain.

        Returns:
            A new CompositeResolver with the added resolver.
        """
        return CompositeResolver([*self._resolvers, resolver])


class StaticResolver:
    """Resolver that always returns a fixed tenant ID.

    Useful for testing, CLI tools, or single-tenant deployments.

    Attributes:
        tenant_id: The fixed tenant ID to return.

    Example:
        ```python
        resolver = StaticResolver("default-tenant")
        # Always returns "default-tenant"
        ```
    """

    __slots__ = ("_tenant_id",)

    def __init__(self, tenant_id: str) -> None:
        if not tenant_id:
            raise ValueError("tenant_id cannot be empty")
        self._tenant_id = tenant_id

    @property
    def tenant_id(self) -> str:
        """The fixed tenant ID."""
        return self._tenant_id

    async def resolve(self, message: Any) -> str | None:
        """Return the fixed tenant ID.

        Args:
            message: Ignored.

        Returns:
            The configured tenant ID.
        """
        return self._tenant_id


class CallableResolver:
    """Resolver that wraps a callable function.

    Allows custom resolution logic via a synchronous or async function.

    Attributes:
        resolver_func: The function to call for resolution.

    Example:
        ```python
        async def my_resolver(message: Any) -> str | None:
            # Custom logic here
            return message.get("custom_tenant")

        resolver = CallableResolver(my_resolver)
        ```
    """

    __slots__ = ("_resolver_func",)

    def __init__(
        self,
        resolver_func: Callable[[Any], Awaitable[str | None] | str | None],
    ) -> None:
        self._resolver_func = resolver_func

    @property
    def resolver_func(self) -> Callable[[Any], Awaitable[str | None] | str | None]:
        """The resolver function."""
        return self._resolver_func

    async def resolve(self, message: Any) -> str | None:
        """Call the resolver function.

        Args:
            message: Passed to the resolver function.

        Returns:
            The result of the resolver function.
        """
        result = self._resolver_func(message)
        if hasattr(result, "__await__"):
            return await cast("Awaitable[str | None]", result)
        return result
