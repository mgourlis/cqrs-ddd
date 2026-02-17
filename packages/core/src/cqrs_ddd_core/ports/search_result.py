"""
SearchResult — lazy query result that supports both await (→ list) and .stream().

Usage::

    # Batch mode — await to get all results at once
    items = await repo.search(spec)

    # Stream mode — iterate efficiently over large result sets
    async for item in repo.search(spec).stream(batch_size=100):
        process(item)

``SearchResult`` is returned by every list-producing query method
(``search``, ``fetch``, etc.) so that callers can choose between
eagerly loading everything or streaming row by row, without requiring
a separate method on the repository/dispatcher protocol.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Coroutine, Generator

T = TypeVar("T")


class SearchResult(Generic[T]):
    """
    Lazy query result — ``await`` for a ``list[T]`` or ``.stream()``
    for an ``AsyncIterator[T]``.

    This object does **not** execute any query at construction time.
    Execution is deferred until the caller either ``await``s or calls
    ``.stream()``.

    Parameters
    ----------
    list_fn:
        Zero-argument async callable that returns a ``list[T]``.
    stream_fn:
        Callable ``(batch_size: int | None) -> AsyncIterator[T]``.
    """

    __slots__ = ("_list_fn", "_stream_fn")

    def __init__(
        self,
        list_fn: Callable[[], Coroutine[Any, Any, list[T]]],
        stream_fn: Callable[[int | None], AsyncIterator[T]],
    ) -> None:
        self._list_fn = list_fn
        self._stream_fn = stream_fn

    # -- await support ------------------------------------------------------

    def __await__(self) -> Generator[Any, None, list[T]]:
        """Make ``await search_result`` return ``list[T]``."""
        return self._list_fn().__await__()

    # -- streaming support --------------------------------------------------

    def stream(self, *, batch_size: int | None = None) -> AsyncIterator[T]:
        """Return an ``AsyncIterator[T]`` for memory-efficient iteration.

        Args:
            batch_size: Rows fetched per DB round-trip (implementation-
                dependent).  ``None`` lets the backend pick a sensible
                default.
        """
        return self._stream_fn(batch_size)

    # -- convenience --------------------------------------------------------

    async def first(self) -> T | None:
        """Return the first result, or ``None`` if the result set is empty."""
        items = await self._list_fn()
        return items[0] if items else None

    async def count(self) -> int:
        """Return the number of results.

        .. note:: This eagerly evaluates the query.  Use with care on
           unbounded result sets.
        """
        items = await self._list_fn()
        return len(items)
