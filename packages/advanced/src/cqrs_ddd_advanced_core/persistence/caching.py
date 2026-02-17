"""
Caching Decorator for Persistence Dispatcher.
Implements Read-Through Caching and Write-Through Invalidation.
"""

import logging
from collections.abc import AsyncIterator, Callable, Sequence
from typing import (
    Any,
    TypeVar,
)

from cqrs_ddd_advanced_core.ports import (
    T_ID,
    T_Criteria,
)
from cqrs_ddd_advanced_core.ports.dispatcher import IPersistenceDispatcher
from cqrs_ddd_core.domain.aggregate import AggregateRoot, Modification
from cqrs_ddd_core.domain.specification import ISpecification
from cqrs_ddd_core.ports.cache import ICacheService
from cqrs_ddd_core.ports.search_result import SearchResult
from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

logger = logging.getLogger("cqrs_ddd.caching")

T_Entity = TypeVar("T_Entity", bound=AggregateRoot[Any])
T_Result = TypeVar("T_Result")


class CachingPersistenceDispatcher(IPersistenceDispatcher):
    """
    Decorator that adds caching behavior to an IPersistenceDispatcher.
    """

    def __init__(
        self,
        inner: IPersistenceDispatcher,
        cache_service: ICacheService,
        default_ttl: int = 300,
    ) -> None:
        self._inner = inner
        self._cache = cache_service
        self._default_ttl = default_ttl

    async def apply(
        self, modification: Modification[T_ID], uow: UnitOfWork | None = None
    ) -> T_ID:
        """Apply modification and invalidate cache."""
        # 1. Delegate to inner
        result = await self._inner.apply(modification, uow)

        # 2. Invalidate Cache
        try:
            await self._invalidate_cache(modification, result)
        except Exception as e:  # noqa: BLE001
            logger.warning("Cache invalidation failed: %s", e)

        return result

    async def fetch_domain(
        self,
        entity_type: type[T_Entity],
        ids: Sequence[T_ID],
        uow: UnitOfWork | None = None,
    ) -> list[T_Entity]:
        """Fetch domain entities with Read-Through caching."""
        # Check explicit cacheable attribute or use class name
        entity_name = getattr(entity_type, "__name__", str(entity_type))

        return await self._execute_read_through(
            entity_name,
            list(ids),
            lambda missing_ids: self._inner.fetch_domain(entity_type, missing_ids, uow),
            cache_key_suffix="",
            cls=entity_type,
        )

    async def fetch(
        self,
        result_type: type[T_Result],
        criteria: T_Criteria[Any],
        uow: UnitOfWork | None = None,
    ) -> SearchResult[T_Result]:
        """Fetch read models. Caches only ID-based lookups."""
        # We only cache ID-based lookups for now
        if isinstance(criteria, ISpecification):
            return await self._inner.fetch(result_type, criteria, uow)

        # Assume criteria is list of IDs
        entity_name = getattr(result_type, "__name__", str(result_type))
        ids_list = list(criteria) if isinstance(criteria, Sequence) else [criteria]

        return self._build_cached_search_result(result_type, entity_name, ids_list, uow)

    def _build_cached_search_result(
        self,
        result_type: type[T_Result],
        entity_name: str,
        ids_list: list[Any],
        uow: UnitOfWork | None,
    ) -> SearchResult[T_Result]:
        """Build a SearchResult with caching support for list and stream modes."""

        async def _fetch_list() -> list[T_Result]:
            return await self._execute_read_through(
                entity_name,
                ids_list,
                lambda missing_ids: self._inner.fetch(
                    result_type, missing_ids, uow
                ).__await__(),
                cache_key_suffix=":query",
                cls=result_type,
            )

        async def _stream(batch_size: int | None = None) -> AsyncIterator[T_Result]:
            if batch_size and batch_size > 0:
                async for item in self._stream_in_batches(
                    result_type, ids_list, batch_size, uow
                ):
                    yield item
            else:
                # Fetch all at once
                items = await _fetch_list()
                for item in items:
                    yield item

        return SearchResult(list_fn=_fetch_list, stream_fn=_stream)

    async def _stream_in_batches(
        self,
        result_type: type[T_Result],
        ids_list: list[Any],
        batch_size: int,
        uow: UnitOfWork | None,
    ) -> AsyncIterator[T_Result]:
        """Stream results in batches without full caching."""
        for i in range(0, len(ids_list), batch_size):
            batch = ids_list[i : i + batch_size]
            batch_result = await self._inner.fetch(result_type, batch, uow)
            batch_items = await batch_result
            for item in batch_items:
                yield item

    # --- Helpers ---

    async def _invalidate_cache(
        self, modification: Modification[Any], result: Any | list[Any]
    ) -> None:
        entity_name = type(modification.entity).__name__
        ids = result if isinstance(result, list) else [result]
        keys = []

        for id_val in ids:
            if id_val is not None:
                keys.append(f"{entity_name}:{id_val}")
                keys.append(f"{entity_name}:query:{id_val}")

        if keys:
            await self._cache.delete_batch(keys)
            logger.debug("Invalidated cache keys: %s", keys)

    async def _get_cached_values(
        self, keys: list[str], cls: type[Any] | None = None
    ) -> list[Any]:
        """Try to get values from cache, return list of None on failure."""
        try:
            return await self._cache.get_batch(keys, cls=cls)
        except Exception as e:  # noqa: BLE001
            logger.warning("Cache get failed: %s", e)
            return [None] * len(keys)

    def _collect_missing_ids(
        self, ids: list[Any], cached_values: list[Any]
    ) -> tuple[list[Any], list[Any]]:
        """Separate cached results from missing IDs."""
        results = []
        missing_ids = []
        for eid, val in zip(ids, cached_values, strict=True):
            if val is not None:
                results.append(val)
            else:
                missing_ids.append(eid)
        return results, missing_ids

    def _prepare_cache_entries(
        self, fresh_results: list[Any], entity_name: str, cache_key_suffix: str
    ) -> list[dict[str, Any]]:
        """Prepare cache entries from fresh results."""
        to_cache = []
        for item in fresh_results:
            item_id = getattr(item, "id", None)
            if item_id:
                key = f"{entity_name}{cache_key_suffix}:{item_id}"
                to_cache.append({"cache_key": key, "value": item})
        return to_cache

    async def _update_cache(self, to_cache: list[dict[str, Any]]) -> None:
        """Update cache with new entries."""
        if to_cache:
            try:
                await self._cache.set_batch(to_cache, ttl=self._default_ttl)
            except Exception as e:  # noqa: BLE001
                logger.warning("Cache set failed: %s", e)

    async def _execute_read_through(
        self,
        entity_name: str,
        ids: list[Any],
        fetch_func: Callable[[list[Any]], Any],  # Returns Awaitable[List[T]]
        cache_key_suffix: str,
        cls: type[Any] | None = None,
    ) -> list[Any]:
        keys = [f"{entity_name}{cache_key_suffix}:{eid}" for eid in ids]

        # 1. Try Cache
        cached_values = await self._get_cached_values(keys, cls=cls)

        # 2. Separate cached results from missing IDs
        results, missing_ids = self._collect_missing_ids(ids, cached_values)

        if not missing_ids:
            # Restore order from cached values
            return [val for val in cached_values if val]

        # 3. Fetch Missing
        fresh_results = await fetch_func(missing_ids)

        # 4. Update Cache
        to_cache = self._prepare_cache_entries(
            fresh_results, entity_name, cache_key_suffix
        )
        await self._update_cache(to_cache)

        # 5. Merge and Return (Simple append for now)
        # Ideally we'd sort by input ID order
        merged: list[Any] = results + fresh_results
        return merged
