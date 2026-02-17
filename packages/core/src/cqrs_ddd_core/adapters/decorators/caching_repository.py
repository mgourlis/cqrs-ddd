"""CachingRepository - Decorator for IRepository with read-through caching."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import UUID

from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.ports.repository import IRepository

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from cqrs_ddd_core.domain.specification import ISpecification
    from cqrs_ddd_core.ports.cache import ICacheService
    from cqrs_ddd_core.ports.search_result import SearchResult
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

T = TypeVar("T", bound=AggregateRoot[Any])  # Aggregate Root
ID = TypeVar("ID", str, int, UUID)  # ID Type

logger = logging.getLogger("cqrs_ddd.caching")


class CachingRepository(IRepository[T, ID]):
    """
    Decorator that adds read-through caching to any IRepository.

    Pattern:
    - get(id): Check cache -> Delegate to inner -> Cache result
    - add(entity): Delegate to inner -> Invalidate cache
    - delete(id): Delegate to inner -> Invalidate cache
    """

    def __init__(
        self,
        inner: IRepository[T, ID],
        cache: ICacheService,
        entity_name: str,
        entity_cls: type[T] | None = None,
        ttl: int = 300,
    ) -> None:
        self._inner: IRepository[T, ID] = inner
        self._cache = cache
        self._entity_name = entity_name
        self._entity_cls = entity_cls
        self._ttl = ttl

    def _key(self, entity_id: Any) -> str:
        return f"{self._entity_name}:{entity_id}"

    async def get(self, entity_id: ID, uow: UnitOfWork | None = None) -> T | None:
        """Retrieve entity with read-through caching."""
        key = self._key(entity_id)

        # 1. Try Cache
        try:
            cached = await self._cache.get(key, cls=self._entity_cls)
            if cached:
                return cached  # type: ignore[no-any-return] # serialization/deserialization handled by cache service
        except Exception as e:  # noqa: BLE001
            logger.warning("Cache get failed for key %s: %s", key, e)

        # 2. Delegate to Inner
        entity = await self._inner.get(entity_id, uow)

        # 3. Update Cache
        if entity:
            try:
                # Store by ID
                await self._cache.set(key, entity, ttl=self._ttl)
            except Exception as e:  # noqa: BLE001
                logger.warning("Cache set failed for key %s: %s", key, e)

        return entity

    async def add(self, entity: T, uow: UnitOfWork | None = None) -> ID:
        """Add entity and invalidate cache."""
        # 1. Delegate
        entity_id = await self._inner.add(entity, uow)

        # 2. Invalidate entity cache
        key = self._key(entity_id)
        try:
            await self._cache.delete(key)
        except Exception as e:  # noqa: BLE001
            logger.warning("Cache invalidate failed for key %s: %s", key, e)

        return entity_id

    async def delete(self, entity_id: ID, uow: UnitOfWork | None = None) -> ID:
        """Delete entity and invalidate cache."""
        # 1. Delegate
        deleted_id = await self._inner.delete(entity_id, uow)

        # 2. Invalidate entity cache
        key = self._key(deleted_id)
        try:
            await self._cache.delete(key)
        except Exception as e:  # noqa: BLE001
            logger.warning("Cache invalidate failed for key %s: %s", key, e)

        return deleted_id

    async def list_all(
        self, entity_ids: list[ID] | None = None, uow: UnitOfWork | None = None
    ) -> list[T]:
        """List entities with read-through caching.

        - If entity_ids is None: pass through (difficult to cache "all")
        - If entity_ids is provided: read-through cache for specific IDs
        """
        # If specific IDs are requested, fetch with read-through caching
        if entity_ids is not None:

            async def fetch_missing(missing_ids: list[ID]) -> list[T]:
                return await self._inner.list_all(missing_ids, uow)

            return await self._execute_read_through(
                list(entity_ids),
                fetch_missing,
            )

        # For complete list (all entities), delegate directly
        # Caching "all" is problematic since we can't be sure what "all" includes
        return await self._inner.list_all(None, uow)

    async def search(
        self,
        criteria: ISpecification[T] | Any,
        uow: UnitOfWork | None = None,
    ) -> SearchResult[T]:
        """Search entities matching specification (bypasses cache).

        Caching search results is complex due to specification variability.
        Pass through to inner repository.
        """
        return await self._inner.search(criteria, uow)

    async def _get_cached_values(self, keys: list[str]) -> list[T | None]:
        """Get cached values for keys, returning None list on failure."""
        try:
            result: list[Any | None] = await self._cache.get_batch(
                keys, cls=self._entity_cls
            )
            # Cast to list[T | None] since cls is provided
            return result
        except Exception as e:  # noqa: BLE001
            logger.warning("Cache batch get failed: %s", e)
            return [None] * len(keys)

    def _collect_missing_ids(
        self, entity_ids: list[ID], cached_values: list[T | None]
    ) -> tuple[dict[ID, T], list[ID]]:
        """Collect cached results and identify missing IDs."""
        results: dict[ID, T] = {}
        missing_ids: list[ID] = []

        for eid, val in zip(entity_ids, cached_values, strict=False):
            eid_typed: ID = eid
            val_typed: T | None = val
            if val_typed is not None:
                results[eid_typed] = val_typed
            else:
                missing_ids.append(eid_typed)

        return results, missing_ids

    def _prepare_cache_entries(
        self, fresh_results: list[T], results: dict[ID, T]
    ) -> list[dict[str, Any]]:
        """Prepare cache entries from fresh results."""
        to_cache = []
        for entity in fresh_results:
            entity_id: Any = getattr(entity, "id", None)
            if entity_id is not None:
                key = self._key(entity_id)
                to_cache.append({"cache_key": key, "value": entity})
                results[entity_id] = entity
        return to_cache

    async def _update_cache(self, to_cache: list[dict[str, Any]]) -> None:
        """Update cache with fresh results."""
        if not to_cache:
            return
        try:
            await self._cache.set_batch(to_cache, ttl=self._ttl)
        except Exception as e:  # noqa: BLE001
            logger.warning("Cache batch set failed: %s", e)

    async def _fetch_and_cache_missing(
        self,
        missing_ids: list[ID],
        fetch_func: Callable[[list[ID]], Awaitable[list[T]]],
        results: dict[ID, T],
    ) -> None:
        """Fetch missing entities and cache them."""
        fresh_results: list[T] = await fetch_func(missing_ids)
        to_cache = self._prepare_cache_entries(fresh_results, results)
        await self._update_cache(to_cache)

    async def _execute_read_through(
        self,
        entity_ids: list[ID],
        fetch_func: Callable[[list[ID]], Awaitable[list[T]]],
    ) -> list[T]:
        """Execute read-through cache for a list of entity IDs.

        Fetches all IDs from cache, identifies missing ones,
        fetches missing from inner repo, caches them, and returns merged results.
        """
        if not entity_ids:
            return []

        keys: list[str] = [self._key(eid) for eid in entity_ids]
        cached_values = await self._get_cached_values(keys)
        results, missing_ids = self._collect_missing_ids(entity_ids, cached_values)

        if missing_ids:
            try:
                await self._fetch_and_cache_missing(missing_ids, fetch_func, results)
            except Exception as e:
                logger.error("Fetch missing entities failed: %s", e)
                raise

        return [results[eid] for eid in entity_ids if eid in results]
