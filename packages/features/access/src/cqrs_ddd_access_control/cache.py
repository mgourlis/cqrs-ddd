"""Permission decision cache wrapping ``ICacheService`` from core."""

from __future__ import annotations

import json
import logging
from typing import Any

from .models import AuthorizationDecision
from .ports import IPermissionCache

logger = logging.getLogger(__name__)


class PermissionDecisionCache(IPermissionCache):
    """TTL-based authorization decision cache.

    Wraps ``ICacheService`` from ``cqrs-ddd-core``.

    Cache key format:
        ``authz:{principal_id}:{resource_type}:{resource_id or '*'}:{action}``

    Parameters
    ----------
    cache:
        ``ICacheService`` instance from ``cqrs-ddd-core``.
    default_ttl:
        Default TTL in seconds (default: 60).
    """

    def __init__(self, cache: Any, default_ttl: int = 60) -> None:
        self._cache = cache
        self._default_ttl = default_ttl

    def _key(
        self,
        principal_id: str,
        resource_type: str,
        resource_id: str | None,
        action: str,
    ) -> str:
        rid = resource_id or "*"
        return f"authz:{principal_id}:{resource_type}:{rid}:{action}"

    async def get(
        self,
        principal_id: str,
        resource_type: str,
        resource_id: str | None,
        action: str,
    ) -> AuthorizationDecision | None:
        key = self._key(principal_id, resource_type, resource_id, action)
        raw = await self._cache.get(key)
        if raw is None:
            return None
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            return AuthorizationDecision(**data)
        except Exception:  # noqa: BLE001 - intentional broad catch for malformed cache
            logger.debug("Cache parse error for key %s", key)
            return None

    async def set(
        self,
        principal_id: str,
        resource_type: str,
        resource_id: str | None,
        action: str,
        decision: AuthorizationDecision,
        ttl: int | None = None,
    ) -> None:
        key = self._key(principal_id, resource_type, resource_id, action)
        data = json.dumps(
            {
                "allowed": decision.allowed,
                "reason": decision.reason,
                "evaluator": decision.evaluator,
            }
        )
        await self._cache.set(key, data, ttl=ttl or self._default_ttl)

    async def invalidate(
        self,
        resource_type: str,
        resource_id: str | None = None,
    ) -> None:
        namespace = f"authz:*:{resource_type}:{resource_id or '*'}"
        try:
            await self._cache.clear_namespace(namespace)
        except Exception:  # noqa: BLE001 - intentional broad catch for backend errors
            logger.debug("Cache invalidation error for namespace %s", namespace)
