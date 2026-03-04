"""Database routing for database-per-tenant isolation.

Provides functionality to route queries to tenant-specific databases
with connection pool management and health checks.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from .context import get_current_tenant_or_none, is_system_tenant
from .exceptions import TenantIsolationError
from .isolation import IsolationConfig, TenantIsolationStrategy

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

__all__ = [
    "DatabaseRouter",
    "TenantConnectionPool",
    "with_tenant_database",
]

logger = logging.getLogger(__name__)

DEFAULT_POOL_SIZE: Final[int] = 5
DEFAULT_MAX_OVERFLOW: Final[int] = 10
DEFAULT_POOL_TIMEOUT: Final[float] = 30.0
DEFAULT_MAX_POOLS: Final[int] = 100


@dataclass
class TenantDatabaseConfig:
    """Configuration for a tenant database connection.

    Attributes:
        database_url: The database URL for the tenant.
        pool_size: Connection pool size.
        max_overflow: Maximum overflow connections.
        pool_timeout: Pool timeout in seconds.
        echo: Whether to echo SQL statements.
    """

    database_url: str
    pool_size: int = DEFAULT_POOL_SIZE
    max_overflow: int = DEFAULT_MAX_OVERFLOW
    pool_timeout: float = DEFAULT_POOL_TIMEOUT
    echo: bool = False


class TenantConnectionPool:
    """Manages connection pools for multiple tenant databases.

    This class maintains a cache of SQLAlchemy engines and session factories
    for each tenant, with LRU eviction for high tenant counts.

    Attributes:
        max_pools: Maximum number of pools to maintain.
        default_config: Default database configuration.

    Example:
        ```python
        pool = TenantConnectionPool(
            get_database_url=lambda tenant_id: f"postgresql://.../{tenant_id}",
            max_pools=50,
        )

        session_factory = await pool.get_session_factory("tenant-123")
        async with session_factory() as session:
            # Use session for tenant-123 database
            ...
        ```
    """

    __slots__ = (
        "_default_config",
        "_engine_factory",
        "_engines",
        "_get_database_url",
        "_lock",
        "_max_pools",
        "_session_factories",
    )

    def __init__(
        self,
        get_database_url: Callable[[str], str],
        *,
        max_pools: int = DEFAULT_MAX_POOLS,
        default_config: TenantDatabaseConfig | None = None,
        engine_factory: Callable[[str, TenantDatabaseConfig], AsyncEngine]
        | None = None,
    ) -> None:
        """Initialize the tenant connection pool.

        Args:
            get_database_url: Function to get database URL for a tenant.
            max_pools: Maximum number of connection pools to maintain.
            default_config: Default database configuration.
            engine_factory: Custom engine factory (for testing).
        """
        self._get_database_url = get_database_url
        self._max_pools = max_pools
        self._default_config = default_config
        self._engine_factory = engine_factory

        # LRU cache using OrderedDict
        self._engines: OrderedDict[str, AsyncEngine] = OrderedDict()
        self._session_factories: OrderedDict[str, async_sessionmaker[AsyncSession]] = (
            OrderedDict()
        )
        self._lock: Any = None  # asyncio.Lock, set lazily

    async def get_engine(self, tenant_id: str) -> AsyncEngine:
        """Get or create an engine for the tenant.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            The SQLAlchemy AsyncEngine for the tenant.
        """
        await self._ensure_lock()

        async with self._lock:
            # Check if engine exists
            if tenant_id in self._engines:
                # Move to end (most recently used)
                self._engines.move_to_end(tenant_id)
                if tenant_id in self._session_factories:
                    self._session_factories.move_to_end(tenant_id)
                return self._engines[tenant_id]

            # Evict oldest if at capacity
            await self._evict_if_needed()

            # Create new engine
            engine = await self._create_engine(tenant_id)
            self._engines[tenant_id] = engine

            logger.debug(
                "Created engine for tenant",
                extra={"tenant_id": tenant_id, "pool_count": len(self._engines)},
            )

            return engine

    async def get_session_factory(
        self, tenant_id: str
    ) -> async_sessionmaker[AsyncSession]:
        """Get or create a session factory for the tenant.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            The async_sessionmaker for the tenant.
        """
        await self._ensure_lock()

        async with self._lock:
            # Check if factory exists
            if tenant_id in self._session_factories:
                # Move to end (most recently used)
                self._engines.move_to_end(tenant_id)
                if tenant_id in self._session_factories:
                    self._session_factories.move_to_end(tenant_id)
                return self._session_factories[tenant_id]

            # Evict oldest if at capacity
            await self._evict_if_needed()

            # Get or create engine
            if tenant_id not in self._engines:
                self._engines[tenant_id] = await self._create_engine(tenant_id)

            # Create session factory
            factory = self._create_session_factory(self._engines[tenant_id])
            self._session_factories[tenant_id] = factory

            logger.debug(
                "Created session factory for tenant",
                extra={
                    "tenant_id": tenant_id,
                    "pool_count": len(self._session_factories),
                },
            )

            return factory

    async def close_engine(self, tenant_id: str) -> None:
        """Close and remove the engine for a tenant.

        Args:
            tenant_id: The tenant identifier.
        """
        await self._ensure_lock()

        async with self._lock:
            if tenant_id in self._engines:
                engine = self._engines.pop(tenant_id)
                self._session_factories.pop(tenant_id, None)
                await engine.dispose()

                logger.debug(
                    "Closed engine for tenant",
                    extra={"tenant_id": tenant_id, "pool_count": len(self._engines)},
                )

    async def close_all(self) -> None:
        """Close all engines and clear the cache."""
        await self._ensure_lock()

        async with self._lock:
            for tenant_id, engine in list(self._engines.items()):
                try:
                    await engine.dispose()
                except Exception as e:
                    logger.warning(
                        "Error disposing engine",
                        extra={"tenant_id": tenant_id, "error": str(e)},
                    )

            self._engines.clear()
            self._session_factories.clear()

            logger.info("Closed all tenant engines")

    async def health_check(self, tenant_id: str) -> bool:
        """Check if the tenant database is healthy.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            True if the database is healthy, False otherwise.
        """
        try:
            from sqlalchemy import text

            engine = await self.get_engine(tenant_id)
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.warning(
                "Tenant database health check failed",
                extra={"tenant_id": tenant_id, "error": str(e)},
            )
            return False

    async def _ensure_lock(self) -> None:
        """Ensure the asyncio lock is created."""
        if self._lock is None:
            import asyncio

            self._lock = asyncio.Lock()

    async def _evict_if_needed(self) -> None:
        """Evict oldest entries if at capacity."""
        while len(self._engines) >= self._max_pools:
            # Remove oldest (first) entry
            oldest_tenant, oldest_engine = next(iter(self._engines.items()))
            self._engines.pop(oldest_tenant)
            self._session_factories.pop(oldest_tenant, None)

            # Dispose engine
            try:
                await oldest_engine.dispose()
                logger.info(
                    "Evicted tenant engine (LRU)",
                    extra={
                        "tenant_id": oldest_tenant,
                        "pool_count": len(self._engines),
                    },
                )
            except Exception as e:
                logger.warning(
                    "Error disposing evicted engine",
                    extra={"tenant_id": oldest_tenant, "error": str(e)},
                )

    async def _create_engine(self, tenant_id: str) -> AsyncEngine:
        """Create a new engine for the tenant.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            A new AsyncEngine.
        """
        database_url = self._get_database_url(tenant_id)
        config = self._default_config or TenantDatabaseConfig(database_url=database_url)

        if self._engine_factory:
            return self._engine_factory(tenant_id, config)

        # Default engine creation
        from sqlalchemy.ext.asyncio import create_async_engine

        return create_async_engine(
            database_url,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
            pool_timeout=config.pool_timeout,
            echo=config.echo,
        )

    def _create_session_factory(
        self, engine: AsyncEngine
    ) -> async_sessionmaker[AsyncSession]:
        """Create a session factory for an engine.

        Args:
            engine: The SQLAlchemy AsyncEngine.

        Returns:
            An async_sessionmaker.
        """
        from sqlalchemy.ext.asyncio import async_sessionmaker

        return async_sessionmaker(
            engine,
            expire_on_commit=False,
            autoflush=False,
        )


class DatabaseRouter:
    """Routes database queries to tenant-specific databases.

    This router manages database connections for the database-per-tenant
    isolation strategy. Each tenant gets their own database connection pool.

    Attributes:
        config: The isolation configuration.
        connection_pool: The tenant connection pool manager.

    Example:
        ```python
        from cqrs_ddd_multitenancy import DatabaseRouter, IsolationConfig

        router = DatabaseRouter(
            config=IsolationConfig(
                strategy=TenantIsolationStrategy.DATABASE_PER_TENANT,
                database_prefix="tenant_",
            ),
            base_url="postgresql://user:pass@localhost:5432",
        )

        async with router.session_for_tenant("tenant-123") as session:
            # Use session for tenant-123 database
            ...
        ```
    """

    __slots__ = ("_base_url", "_config", "_connection_pool")

    def __init__(
        self,
        config: IsolationConfig,
        *,
        base_url: str,
        connection_pool: TenantConnectionPool | None = None,
        max_pools: int = DEFAULT_MAX_POOLS,
    ) -> None:
        """Initialize the database router.

        Args:
            config: The isolation configuration.
            base_url: Base database URL (without database name).
            connection_pool: Optional pre-configured connection pool.
            max_pools: Maximum number of connection pools (if creating new).
        """
        if config.strategy != TenantIsolationStrategy.DATABASE_PER_TENANT:
            raise ValueError(
                f"DatabaseRouter requires DATABASE_PER_TENANT strategy, got {config.strategy}"
            )

        self._config = config
        self._base_url = base_url.rstrip("/")

        if connection_pool:
            self._connection_pool = connection_pool
        else:
            self._connection_pool = TenantConnectionPool(
                get_database_url=self._get_database_url,
                max_pools=max_pools,
            )

    @property
    def config(self) -> IsolationConfig:
        """The isolation configuration."""
        return self._config

    @property
    def connection_pool(self) -> TenantConnectionPool:
        """The connection pool manager."""
        return self._connection_pool

    def _get_database_url(self, tenant_id: str) -> str:
        """Get the full database URL for a tenant.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            The database URL.
        """
        database_name = self._config.get_database_name(tenant_id)
        return f"{self._base_url}/{database_name}"

    def get_database_name(self, tenant_id: str) -> str:
        """Get the database name for a tenant.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            The database name.
        """
        return self._config.get_database_name(tenant_id)

    async def get_engine(self, tenant_id: str) -> AsyncEngine:
        """Get the engine for a tenant.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            The SQLAlchemy AsyncEngine for the tenant.
        """
        return await self._connection_pool.get_engine(tenant_id)

    async def get_session_factory(
        self, tenant_id: str
    ) -> async_sessionmaker[AsyncSession]:
        """Get the session factory for a tenant.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            The async_sessionmaker for the tenant.
        """
        return await self._connection_pool.get_session_factory(tenant_id)

    @asynccontextmanager
    async def session_for_tenant(
        self,
        tenant_id: str | None = None,
    ) -> AsyncIterator[AsyncSession]:
        """Context manager that provides a session for a tenant.

        Args:
            tenant_id: The tenant identifier (uses current context if None).

        Yields:
            An AsyncSession for the tenant database.

        Raises:
            TenantIsolationError: If tenant cannot be determined.
        """
        # Resolve tenant ID
        effective_tenant = tenant_id or get_current_tenant_or_none()

        if effective_tenant is None:
            if is_system_tenant():
                raise TenantIsolationError(
                    "System tenant requires explicit tenant_id for database routing",
                    strategy="DATABASE_PER_TENANT",
                )
            raise TenantIsolationError(
                "Cannot route to database: no tenant in context",
                strategy="DATABASE_PER_TENANT",
            )

        factory = await self.get_session_factory(effective_tenant)

        async with factory() as session:
            yield session

    @asynccontextmanager
    async def session_for_current_tenant(self) -> AsyncIterator[AsyncSession]:
        """Context manager that provides a session for the current tenant.

        Yields:
            An AsyncSession for the current tenant's database.

        Raises:
            TenantIsolationError: If tenant cannot be determined.
        """
        async with self.session_for_tenant() as session:
            yield session

    async def close_all(self) -> None:
        """Close all database connections."""
        await self._connection_pool.close_all()

    async def health_check(self, tenant_id: str) -> bool:
        """Check if a tenant database is healthy.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            True if healthy, False otherwise.
        """
        return await self._connection_pool.health_check(tenant_id)


@asynccontextmanager
async def with_tenant_database(
    router: DatabaseRouter,
    tenant_id: str | None = None,
) -> AsyncIterator[AsyncSession]:
    """Context manager for tenant database routing.

    Args:
        router: The database router.
        tenant_id: The tenant identifier (uses current context if None).

    Yields:
        An AsyncSession for the tenant database.
    """
    async with router.session_for_tenant(tenant_id) as session:
        yield session
