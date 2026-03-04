"""ABACClientConfig — configuration for the stateful-abac client."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal


@dataclass
class ABACClientConfig:
    """Configuration for the stateful-abac-policy-engine client.

    Supports both HTTP mode (production) and DB mode (testing/single-process).

    Parameters
    ----------
    realm:
        Static string or callable for dynamic per-request resolution.
        When using a callable for multi-tenant setups, ensure it returns a
        non-empty string — e.g.::

            from cqrs_ddd_identity.context import get_tenant_id

            def resolve_realm() -> str:
                tid = get_tenant_id()
                if not tid:
                    raise ValueError("No tenant in context — cannot resolve ABAC realm")
                return tid

        Do NOT use ``lambda: get_current_principal().tenant_id`` directly,
        as ``tenant_id`` is optional and may be ``None``.
    cache_enabled:
        Reserved for future use. The SDK does not yet implement client-side
        caching; this field has no effect.
    cache_ttl:
        Reserved for future use.
    cache_maxsize:
        Reserved for future use.
    """

    mode: Literal["http", "db"] = "http"
    base_url: str = ""
    realm: str | Callable[[], str] = ""
    timeout: int = 30
    chunk_size: int = 500
    max_concurrent: int = 5
    # Reserved — SDK does not yet support client-side caching.
    cache_enabled: bool = True
    cache_ttl: int = 300
    cache_maxsize: int = 1000

    def resolve_realm(self) -> str:
        """Resolve the realm name. Calls the callable if realm is dynamic.

        Raises
        ------
        ValueError
            If the resolved realm is empty or ``None``.
        """
        realm = self.realm() if callable(self.realm) else self.realm
        if not realm:
            raise ValueError(
                "ABAC realm resolved to an empty value. "
                "Ensure ABACClientConfig.realm is set to a non-empty string "
                "or a callable that returns one (e.g. the current tenant ID)."
            )
        return realm

    @classmethod
    def from_env(cls, prefix: str = "ABAC_") -> ABACClientConfig:
        """Create config from environment variables.

        Reads: ``{prefix}MODE``, ``{prefix}BASE_URL``, ``{prefix}REALM``,
        ``{prefix}TIMEOUT``, ``{prefix}CHUNK_SIZE``, ``{prefix}MAX_CONCURRENT``,
        ``{prefix}CACHE_ENABLED``, ``{prefix}CACHE_TTL``, ``{prefix}CACHE_MAXSIZE``.

        For dynamic realm resolution, set ``realm`` to a callable after
        construction.
        """
        return cls(
            mode=os.environ.get(f"{prefix}MODE", "http"),  # type: ignore[arg-type]
            base_url=os.environ.get(f"{prefix}BASE_URL", ""),
            realm=os.environ.get(f"{prefix}REALM", ""),
            timeout=int(os.environ.get(f"{prefix}TIMEOUT", "30")),
            chunk_size=int(os.environ.get(f"{prefix}CHUNK_SIZE", "500")),
            max_concurrent=int(os.environ.get(f"{prefix}MAX_CONCURRENT", "5")),
            cache_enabled=(
                os.environ.get(f"{prefix}CACHE_ENABLED", "true").lower() == "true"
            ),
            cache_ttl=int(os.environ.get(f"{prefix}CACHE_TTL", "300")),
            cache_maxsize=int(os.environ.get(f"{prefix}CACHE_MAXSIZE", "1000")),
        )
