"""Tenant-aware health check utilities.

This module provides utilities for performing health checks across tenant-isolated
infrastructure, ensuring each tenant's resources are accessible and healthy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from ..context import get_current_tenant

__all__ = [
    "HealthStatus",
    "TenantHealthCheckResult",
    "TenantHealthChecker",
]

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health check status values."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class TenantHealthCheckResult:
    """Result of a health check for a specific tenant.

    Attributes:
        tenant_id: The tenant ID.
        status: Health status.
        component: Component name (e.g., "database", "cache", "queue").
        message: Human-readable status message.
        timestamp: When the check was performed.
        details: Additional details about the health check.
        latency_ms: Time taken to perform the check in milliseconds.
    """

    tenant_id: str
    status: HealthStatus
    component: str
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict[str, Any] = field(default_factory=dict)
    latency_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "tenant_id": self.tenant_id,
            "status": self.status.value,
            "component": self.component,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
            "latency_ms": self.latency_ms,
        }


class TenantHealthChecker:
    """Base class for tenant-aware health checks.

    This class provides utilities for performing health checks on tenant-isolated
    infrastructure components. Subclasses implement specific health check logic.

    Usage:
        ```python
        class DatabaseHealthChecker(TenantHealthChecker):
            async def check_health(self, tenant_id: str) -> TenantHealthCheckResult:
                # Check database connectivity for this tenant
                ...
        ```
    """

    def __init__(self, component_name: str) -> None:
        """Initialize the health checker.

        Args:
            component_name: Name of the component being checked (e.g., "database").
        """
        self.component_name = component_name

    async def check_current_tenant(self) -> TenantHealthCheckResult:
        """Perform health check for the current tenant.

        Returns:
            Health check result for current tenant.

        Raises:
            TenantContextMissingError: If no tenant context is set.
        """
        tenant_id = get_current_tenant()
        return await self.check_health(tenant_id)

    async def check_health(self, tenant_id: str) -> TenantHealthCheckResult:
        """Perform health check for a specific tenant.

        Subclasses must implement this method.

        Args:
            tenant_id: The tenant ID to check.

        Returns:
            Health check result.
        """
        raise NotImplementedError("Subclasses must implement check_health()")

    async def check_multiple_tenants(
        self, tenant_ids: list[str]
    ) -> list[TenantHealthCheckResult]:
        """Perform health checks for multiple tenants.

        Args:
            tenant_ids: List of tenant IDs to check.

        Returns:
            List of health check results.
        """
        results = []
        for tenant_id in tenant_ids:
            try:
                result = await self.check_health(tenant_id)
                results.append(result)
            except Exception as e:
                logger.error(
                    f"Health check failed for tenant {tenant_id}: {e}",
                    exc_info=True,
                )
                results.append(
                    TenantHealthCheckResult(
                        tenant_id=tenant_id,
                        status=HealthStatus.UNKNOWN,
                        component=self.component_name,
                        message=f"Health check failed: {e}",
                        details={"error": str(e)},
                    )
                )
        return results


class CompositeTenantHealthChecker:
    """Aggregates multiple health checkers for comprehensive tenant health monitoring.

    Usage:
        ```python
        composite = CompositeTenantHealthChecker()
        composite.add_checker("database", DatabaseHealthChecker())
        composite.add_checker("cache", CacheHealthChecker())

        results = await composite.check_all(tenant_id)
        ```
    """

    def __init__(self) -> None:
        """Initialize composite health checker."""
        self._checkers: dict[str, TenantHealthChecker] = {}

    def add_checker(self, name: str, checker: TenantHealthChecker) -> None:
        """Add a health checker.

        Args:
            name: Name for the checker.
            checker: The health checker instance.
        """
        self._checkers[name] = checker

    def remove_checker(self, name: str) -> None:
        """Remove a health checker.

        Args:
            name: Name of the checker to remove.
        """
        self._checkers.pop(name, None)

    async def check_all(self, tenant_id: str) -> dict[str, TenantHealthCheckResult]:
        """Run all health checks for a tenant.

        Args:
            tenant_id: The tenant ID to check.

        Returns:
            Dict mapping component names to health check results.
        """
        results = {}
        for name, checker in self._checkers.items():
            try:
                result = await checker.check_health(tenant_id)
                results[name] = result
            except Exception as e:
                logger.error(
                    f"Health checker '{name}' failed for tenant {tenant_id}: {e}",
                    exc_info=True,
                )
                results[name] = TenantHealthCheckResult(
                    tenant_id=tenant_id,
                    status=HealthStatus.UNKNOWN,
                    component=name,
                    message=f"Health check failed: {e}",
                    details={"error": str(e)},
                )
        return results

    async def check_current_tenant(self) -> dict[str, TenantHealthCheckResult]:
        """Run all health checks for the current tenant.

        Returns:
            Dict mapping component names to health check results.

        Raises:
            TenantContextMissingError: If no tenant context is set.
        """
        tenant_id = get_current_tenant()
        return await self.check_all(tenant_id)

    def get_overall_status(
        self, results: dict[str, TenantHealthCheckResult]
    ) -> HealthStatus:
        """Determine overall health status from individual component results.

        Args:
            results: Health check results for all components.

        Returns:
            Overall health status (most severe status across all components).
        """
        if not results:
            return HealthStatus.UNKNOWN

        # Priority: UNHEALTHY > DEGRADED > HEALTHY > UNKNOWN
        status_priority = {
            HealthStatus.UNHEALTHY: 4,
            HealthStatus.DEGRADED: 3,
            HealthStatus.HEALTHY: 2,
            HealthStatus.UNKNOWN: 1,
        }

        max_priority = 0
        overall_status = HealthStatus.UNKNOWN

        for result in results.values():
            priority = status_priority.get(result.status, 0)
            if priority > max_priority:
                max_priority = priority
                overall_status = result.status

        return overall_status
