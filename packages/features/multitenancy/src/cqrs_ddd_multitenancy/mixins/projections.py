"""Multitenant projection mixins for IProjectionWriter, IProjectionReader, and IProjectionPositionStore.

These mixins add tenant context propagation and filtering to projection
operations when composed with base projection classes via MRO.

Usage:
    class MyProjectionStore(
        MultitenantProjectionMixin,
        SQLAlchemyProjectionStore
    ):
        pass

    class MyPositionStore(
        MultitenantProjectionPositionMixin,
        SQLAlchemyProjectionPositionStore
    ):
        pass

The mixins must appear BEFORE the base classes in the MRO.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..context import require_tenant

if TYPE_CHECKING:
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

__all__ = [
    "MultitenantProjectionMixin",
    "MultitenantProjectionPositionMixin",
]

logger = logging.getLogger(__name__)


class MultitenantProjectionMixin:
    """Mixin for IProjectionWriter and IProjectionReader with tenant isolation.

    Provides automatic tenant namespacing for projection documents:
    - **get/upsert**: Keys prefixed with tenant_id
    - **find**: Filters by tenant context
    - **delete**: Scoped to tenant

    Usage:
        class MyProjectionStore(
            MultitenantProjectionMixin,
            SQLAlchemyProjectionStore
        ):
            pass
    """

    def _tenant_doc_id(
        self, doc_id: str | int | dict[str, Any]
    ) -> str | int | dict[str, Any]:
        """Prefix document ID with tenant namespace.

        Args:
            doc_id: Original document ID

        Returns:
            Tenant-namespaced document ID
        """
        tenant_id = require_tenant()

        if isinstance(doc_id, str):
            return f"{tenant_id}:{doc_id}"
        if isinstance(doc_id, int):
            # For int IDs, we can't prefix, so use composite key
            return {"tenant_id": tenant_id, "id": doc_id}
        if isinstance(doc_id, dict):
            # For composite keys, inject tenant_id directly into the dict
            doc_id["tenant_id"] = tenant_id
            return doc_id
        return f"{tenant_id}:{doc_id}"

    def _tenant_collection(self, collection: str) -> str:
        """Get tenant-scoped collection name.

        For discriminator strategy, we use the same collection but filter by tenant.
        For separate collections strategy, we could prefix collection name.

        Args:
            collection: Original collection name

        Returns:
            Collection name (unchanged for discriminator strategy)
        """
        # For discriminator strategy, collection stays the same
        # Filtering happens at query level
        return collection

    async def get(
        self,
        collection: str,
        doc_id: str | int | dict[str, Any],
        *,
        uow: UnitOfWork | None = None,
    ) -> dict[str, Any] | None:
        """Get projection document with tenant filtering.

        Args:
            collection: Collection/table name
            doc_id: Document ID
            uow: Optional unit of work

        Returns:
            Document if found and belongs to tenant, None otherwise

        Raises:
            TenantContextMissingError: If no tenant context is set
        """
        tenant_id = require_tenant()

        # Use tenant-namespaced ID
        tenant_doc_id = self._tenant_doc_id(doc_id)

        logger.debug(
            "Getting projection with tenant context",
            extra={
                "tenant_id": tenant_id,
                "collection": collection,
                "doc_id": str(doc_id),
            },
        )

        # Call parent get method
        result = await super().get(collection, tenant_doc_id, uow=uow)  # type: ignore[misc]

        # Verify tenant ownership (belt and suspenders)
        if result and result.get("tenant_id") != tenant_id:
            logger.warning(
                "Cross-tenant projection access blocked",
                extra={
                    "tenant_id": tenant_id,
                    "doc_tenant": result.get("tenant_id"),
                },
            )
            return None

        return result  # type: ignore[no-any-return]

    async def get_batch(
        self,
        collection: str,
        doc_ids: list[str | int | dict[str, Any]],
        *,
        uow: UnitOfWork | None = None,
    ) -> list[dict[str, Any] | None]:
        """Get batch of projection documents with tenant filtering.

        Calls ``self.get`` for each doc_id so the mixin's namespacing and
        tenant validation are applied exactly once per item (avoiding the
        double-namespacing that occurs when the parent's get_batch delegates
        to ``self.get`` after IDs have already been transformed).

        Args:
            collection: Collection/table name
            doc_ids: List of document IDs
            uow: Optional unit of work

        Returns:
            List of documents (None for not found or cross-tenant)

        Raises:
            TenantContextMissingError: If no tenant context is set
        """
        # require_tenant() here to raise early if no context is set
        require_tenant()
        return [await self.get(collection, doc_id, uow=uow) for doc_id in doc_ids]

    async def find(
        self,
        collection: str,
        filter_dict: dict[str, Any],
        *,
        limit: int = 100,
        offset: int = 0,
        uow: UnitOfWork | None = None,
    ) -> list[dict[str, Any]]:
        """Find projection documents with tenant filtering.

        Args:
            collection: Collection/table name
            filter_dict: Filter criteria
            limit: Maximum results
            offset: Result offset
            uow: Optional unit of work

        Returns:
            List of matching documents for current tenant

        Raises:
            TenantContextMissingError: If no tenant context is set
        """
        tenant_id = require_tenant()

        # Add tenant filter
        tenant_filter = {**filter_dict, "tenant_id": tenant_id}

        logger.debug(
            "Finding projections with tenant filter",
            extra={
                "tenant_id": tenant_id,
                "collection": collection,
            },
        )

        # Call parent with tenant filter
        return await super().find(  # type: ignore[misc, no-any-return]
            collection, tenant_filter, limit=limit, offset=offset, uow=uow
        )

    async def upsert(
        self,
        collection: str,
        doc_id: str | int | dict[str, Any],
        data: dict[str, Any] | Any,
        *,
        event_position: int | None = None,
        event_id: str | None = None,
        uow: UnitOfWork | None = None,
    ) -> bool:
        """Upsert projection document with tenant context.

        Args:
            collection: Collection/table name
            doc_id: Document ID
            data: Document data
            event_position: Event position for versioning
            event_id: Event ID for deduplication
            uow: Optional unit of work

        Returns:
            True if upserted, False if rejected

        Raises:
            TenantContextMissingError: If no tenant context is set
        """
        tenant_id = require_tenant()

        # Namespace the document ID
        tenant_doc_id = self._tenant_doc_id(doc_id)

        # Inject tenant_id into data
        if isinstance(data, dict):
            data["tenant_id"] = tenant_id
        elif hasattr(data, "model_dump"):
            # Pydantic model
            data_dict = data.model_dump()
            data_dict["tenant_id"] = tenant_id
            data = data_dict

        logger.debug(
            "Upserting projection with tenant context",
            extra={
                "tenant_id": tenant_id,
                "collection": collection,
                "doc_id": str(doc_id),
            },
        )

        # Call parent upsert
        return await super().upsert(  # type: ignore[misc, no-any-return]
            collection,
            tenant_doc_id,
            data,
            event_position=event_position,
            event_id=event_id,
            uow=uow,
        )

    async def upsert_batch(
        self,
        collection: str,
        docs: list[dict[str, Any] | Any],
        *,
        id_field: str = "id",
        uow: UnitOfWork | None = None,
    ) -> None:
        """Batch upsert with tenant context.

        Args:
            collection: Collection/table name
            docs: List of documents to upsert
            id_field: Field containing document ID
            uow: Optional unit of work

        Raises:
            TenantContextMissingError: If no tenant context is set
        """
        tenant_id = require_tenant()

        # Inject tenant_id into all documents
        tenant_docs = []
        for doc in docs:
            if isinstance(doc, dict):
                tenant_doc = {**doc, "tenant_id": tenant_id}
            elif hasattr(doc, "model_dump"):
                tenant_doc = doc.model_dump()
                tenant_doc["tenant_id"] = tenant_id
            else:
                tenant_doc = {"data": doc, "tenant_id": tenant_id}
            tenant_docs.append(tenant_doc)

        logger.debug(
            "Batch upserting projections with tenant context",
            extra={
                "tenant_id": tenant_id,
                "collection": collection,
                "count": len(docs),
            },
        )

        # Call parent
        await super().upsert_batch(collection, tenant_docs, id_field=id_field, uow=uow)  # type: ignore[misc]

    async def delete(
        self,
        collection: str,
        doc_id: str | int | dict[str, Any],
        *,
        cascade: bool = False,
        uow: UnitOfWork | None = None,
    ) -> None:
        """Delete projection document with tenant scoping.

        Args:
            collection: Collection/table name
            doc_id: Document ID
            cascade: Whether to cascade delete
            uow: Optional unit of work

        Raises:
            TenantContextMissingError: If no tenant context is set
        """
        tenant_id = require_tenant()

        # Namespace the document ID
        tenant_doc_id = self._tenant_doc_id(doc_id)

        logger.debug(
            "Deleting projection with tenant context",
            extra={
                "tenant_id": tenant_id,
                "collection": collection,
                "doc_id": str(doc_id),
            },
        )

        # Call parent delete
        await super().delete(collection, tenant_doc_id, cascade=cascade, uow=uow)  # type: ignore[misc]


class MultitenantProjectionPositionMixin:
    """Mixin for IProjectionPositionStore with tenant isolation.

    Provides tenant-specific position tracking for projections.

    Usage:
        class MyPositionStore(
            MultitenantProjectionPositionMixin,
            SQLAlchemyProjectionPositionStore
        ):
            pass
    """

    def _tenant_projection_name(self, projection_name: str) -> str:
        """Prefix projection name with tenant namespace.

        Args:
            projection_name: Original projection name

        Returns:
            Tenant-namespaced projection name
        """
        tenant_id = require_tenant()
        return f"{tenant_id}:{projection_name}"

    async def get_position(
        self,
        projection_name: str,
        *,
        uow: UnitOfWork | None = None,
    ) -> int | None:
        """Get projection position for current tenant.

        Args:
            projection_name: Projection name
            uow: Optional unit of work

        Returns:
            Position if found, None otherwise

        Raises:
            TenantContextMissingError: If no tenant context is set
        """
        tenant_id = require_tenant()

        # Namespace projection name
        tenant_name = self._tenant_projection_name(projection_name)

        logger.debug(
            "Getting projection position with tenant context",
            extra={
                "tenant_id": tenant_id,
                "projection": projection_name,
            },
        )

        # Call parent
        return await super().get_position(tenant_name, uow=uow)  # type: ignore[misc, no-any-return]

    async def save_position(
        self,
        projection_name: str,
        position: int,
        *,
        uow: UnitOfWork | None = None,
    ) -> None:
        """Save projection position for current tenant.

        Args:
            projection_name: Projection name
            position: Position to save
            uow: Optional unit of work

        Raises:
            TenantContextMissingError: If no tenant context is set
        """
        tenant_id = require_tenant()

        # Namespace projection name
        tenant_name = self._tenant_projection_name(projection_name)

        logger.debug(
            "Saving projection position with tenant context",
            extra={
                "tenant_id": tenant_id,
                "projection": projection_name,
                "position": position,
            },
        )

        # Call parent
        await super().save_position(tenant_name, position, uow=uow)  # type: ignore[misc]

    async def reset_position(
        self,
        projection_name: str,
        *,
        uow: UnitOfWork | None = None,
    ) -> None:
        """Reset projection position for current tenant.

        Args:
            projection_name: Projection name
            uow: Optional unit of work

        Raises:
            TenantContextMissingError: If no tenant context is set
        """
        tenant_id = require_tenant()

        # Namespace projection name
        tenant_name = self._tenant_projection_name(projection_name)

        logger.debug(
            "Resetting projection position with tenant context",
            extra={
                "tenant_id": tenant_id,
                "projection": projection_name,
            },
        )

        # Call parent
        await super().reset_position(tenant_name, uow=uow)  # type: ignore[misc]
