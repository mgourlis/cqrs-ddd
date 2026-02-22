"""Infrastructure-agnostic projection writer and position store protocols."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, Union, runtime_checkable

if TYPE_CHECKING:
    from cqrs_ddd_advanced_core.projections.schema import ProjectionSchema
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork


DocId = Union[str, int, dict[str, Any]]  # Simple or composite key


@runtime_checkable
class IProjectionWriter(Protocol):
    """
    Protocol for projection writers (infrastructure-agnostic).

    Uses the existing UnitOfWork pattern for transaction management.

    Usage Patterns:

    1. **Single operation (auto-commit):**
        ```python
        await writer.upsert("summaries", "123", data)
        ```

    2. **Multi-operation transaction (via UnitOfWork):**
        ```python
        async with uow:
            await writer.upsert("customers", "C1", customer_data, uow=uow)
            await writer.upsert("orders", "123", order_data, uow=uow)
            await writer.upsert("items", "I1", item_data, uow=uow)
        ```

    Implementations:
        - MongoProjectionStore
        - SQLAlchemyProjectionStore

    CRITICAL: All projection upserts MUST include version columns:
        - `_version`: Event position for concurrency control
        - `_last_event_id`: Event ID for idempotency
        - `_last_event_position`: Last processed position
    """

    # ========================================
    # SCHEMA LIFECYCLE METHODS
    # ========================================

    async def ensure_collection(
        self,
        collection: str,
        *,
        schema: ProjectionSchema | None = None,
    ) -> None:
        """
        Ensure collection/table exists.

        Args:
            collection: Table name (SQL) or collection name (MongoDB)
            schema: SQLAlchemy-based schema definition

        MongoDB:
            - No-op (auto-creates) or apply validation rules

        PostgreSQL/SQLite:
            - Creates table using schema.table DDL
            - Uses SQLAlchemy's CreateTable() construct

        PRODUCTION: Requires migrations (see allow_auto_ddl flag)
        """
        ...

    async def collection_exists(self, collection: str) -> bool:
        """Check if collection/table exists."""
        ...

    async def truncate_collection(self, collection: str) -> None:
        """
        Remove all data but keep structure.

        MongoDB: Deletes all documents (keeps collection)
        PostgreSQL: TRUNCATE TABLE (fast, resets sequences)

        Use this for projection replay (faster than drop + recreate).
        """
        ...

    async def drop_collection(self, collection: str) -> None:
        """
        Drop entire collection/table.

        MongoDB: db.collection.drop()
        PostgreSQL: DROP TABLE ... CASCADE
        """
        ...

    # ========================================
    # DATA OPERATIONS
    # ========================================

    async def upsert(
        self,
        collection: str,
        doc_id: DocId,
        data: dict[str, Any] | Any,
        *,
        event_position: int | None = None,
        event_id: str | None = None,
        uow: UnitOfWork | None = None,
    ) -> bool:
        """
        Upsert a single projection document/row with version control.

        Args:
            collection: Table name (SQL) or collection name (MongoDB)
            doc_id: Document/row ID (str/int for simple, dict for composite)
            data: Data to upsert (Pydantic model or dict)
            event_position: Event position for version checking
            event_id: Event ID for deduplication
            uow: Optional UnitOfWork for transactional consistency

        Returns:
            True if upsert succeeded, False if rejected (stale version/duplicate)
        """
        ...

    async def upsert_batch(
        self,
        collection: str,
        docs: list[dict[str, Any] | Any],
        *,
        id_field: str = "id",
        uow: UnitOfWork | None = None,
    ) -> None:
        """
        Bulk upsert projection documents/rows to a single collection/table.

        Args:
            collection: Table name (SQL) or collection name (MongoDB)
            docs: List of documents/rows to upsert
            id_field: Field name containing the ID (default: "id")
            uow: Optional UnitOfWork for transactional consistency
        """
        ...

    async def delete(
        self,
        collection: str,
        doc_id: DocId,
        *,
        cascade: bool = False,
        uow: UnitOfWork | None = None,
    ) -> None:
        """
        Delete a single projection document/row.

        Args:
            collection: Table name (SQL) or collection name (MongoDB)
            doc_id: Document/row ID (str/int for simple, dict for composite)
            cascade: If True, delete related entities (SQL: ON DELETE CASCADE)
            uow: Optional UnitOfWork for transactional consistency
        """
        ...

    async def ensure_ttl_index(
        self,
        collection: str,
        field: str,
        expire_after_seconds: int,
    ) -> None:
        """
        Create TTL index/constraint for temporary projections.

        MongoDB: Native TTL indexes
        PostgreSQL: Requires pg_partman or external scheduler
        SQLite: No-op
        """
        ...


@runtime_checkable
class IProjectionReader(Protocol):
    """
    Protocol for reading projection documents by collection and id.

    Symmetric with IProjectionWriter at the same abstraction level:
    use for projection handlers that need read-modify-write, or for
    tooling that reads from a named collection without a typed DTO.
    """

    async def get(
        self,
        collection: str,
        doc_id: DocId,
        *,
        uow: UnitOfWork | None = None,
    ) -> dict[str, Any] | None:
        """
        Get a single projection document/row by id.

        Returns:
            Document as dict, or None if not found.
        """
        ...

    async def get_batch(
        self,
        collection: str,
        doc_ids: list[DocId],
        *,
        uow: UnitOfWork | None = None,
    ) -> list[dict[str, Any] | None]:
        """
        Fetch multiple documents by IDs (optional method).

        Returns:
            List of documents (or None for not found), preserving order.
        """
        ...

    async def find(
        self,
        collection: str,
        filter: dict[str, Any],
        *,
        limit: int = 100,
        offset: int = 0,
        uow: UnitOfWork | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query documents by filter dict (optional method).

        Args:
            collection: Table/collection name
            filter: Filter conditions (e.g., {"status": "active"})
            limit: Max results (default: 100)
            offset: Skip first N results (default: 0)

        Returns:
            List of matching documents.
        """
        ...


@runtime_checkable
class IProjectionPositionStore(Protocol):
    """
    Tracks last processed event position for each projection.

    Essential for:
    - Crash recovery (resume from last position)
    - Idempotency (skip already-processed events)
    - Monitoring (lag detection)

    MUST be used in same transaction as projection upsert.
    """

    async def get_position(
        self,
        projection_name: str,
        *,
        uow: UnitOfWork | None = None,
    ) -> int | None:
        """
        Get last processed event position/offset.

        Returns:
            Last processed position, or None if never processed
        """
        ...

    async def save_position(
        self,
        projection_name: str,
        position: int,
        *,
        uow: UnitOfWork | None = None,
    ) -> None:
        """
        Update position after successful event processing.

        MUST be in same transaction as projection upsert.
        """
        ...

    async def reset_position(
        self,
        projection_name: str,
        *,
        uow: UnitOfWork | None = None,
    ) -> None:
        """Reset position for full replay."""
        ...
