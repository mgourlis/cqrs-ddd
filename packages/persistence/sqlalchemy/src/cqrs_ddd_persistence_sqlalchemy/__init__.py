"""SQLAlchemy Persistence Adapter."""

from __future__ import annotations

from .advanced.position_store import SQLAlchemyProjectionPositionStore
from .advanced.projection_store import SQLAlchemyProjectionStore
from .compat import HAS_GEOMETRY
from .core.event_store import SQLAlchemyEventStore
from .core.model_mapper import ModelMapper
from .core.models import (
    Base,
    OutboxMessage,
    OutboxStatus,
    StoredEventModel,
)
from .core.outbox import SQLAlchemyOutboxStorage
from .core.repository import SQLAlchemyRepository
from .core.uow import SQLAlchemyUnitOfWork
from .exceptions import (
    MappingError,
    OptimisticConcurrencyError,
    RepositoryError,
    SessionManagementError,
    SQLAlchemyPersistenceError,
    TransactionError,
    UnitOfWorkError,
)
from .projections import (
    ProjectionCheckpoint,
    SQLAlchemyProjectionCheckpointStore,
)
from .specifications import (
    SQLAlchemyHookResult,
    SQLAlchemyOperator,
    SQLAlchemyOperatorRegistry,
    SQLAlchemyResolutionContext,
    apply_query_options,
    build_sqla_filter,
)

if HAS_GEOMETRY:
    from .types.spatialite import (
        geojson_to_geometry,
        geometry_to_geojson,
        geometry_type_coercers,
        init_geopackage,
        register_spatialite_mappings,
        reverse_geometry_type_coercers,
        setup_geopackage_engine,
        setup_spatialite_engine,
    )

__all__ = [
    # Core
    "ModelMapper",
    "SQLAlchemyRepository",
    "SQLAlchemyUnitOfWork",
    "SQLAlchemyEventStore",
    "SQLAlchemyOutboxStorage",
    "Base",
    "OutboxMessage",
    "StoredEventModel",
    "OutboxStatus",
    # Projections (IProjectionWriter / IProjectionPositionStore)
    "SQLAlchemyProjectionStore",
    "SQLAlchemyProjectionPositionStore",
    "ProjectionCheckpoint",
    "SQLAlchemyProjectionCheckpointStore",
    # Specifications / Compiler
    "build_sqla_filter",
    "apply_query_options",
    "SQLAlchemyOperator",
    "SQLAlchemyOperatorRegistry",
    "SQLAlchemyResolutionContext",
    "SQLAlchemyHookResult",
    # Exceptions
    "SQLAlchemyPersistenceError",
    "SessionManagementError",
    "UnitOfWorkError",
    "RepositoryError",
    "TransactionError",
    "OptimisticConcurrencyError",
    "MappingError",
]

if HAS_GEOMETRY:
    __all__ += [
        "geometry_to_geojson",
        "geometry_type_coercers",
        "geojson_to_geometry",
        "init_geopackage",
        "register_spatialite_mappings",
        "reverse_geometry_type_coercers",
        "setup_geopackage_engine",
        "setup_spatialite_engine",
    ]
