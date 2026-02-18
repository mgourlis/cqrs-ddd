"""SQLAlchemy model mixins for versioning, audit, archival, and geometry."""

from .columns import (
    ArchivableModelMixin,
    AuditableModelMixin,
    VersionMixin,
)

__all__ = [
    "ArchivableModelMixin",
    "AuditableModelMixin",
    "VersionMixin",
]

try:
    from .geometry import SpatialModelMixin  # noqa: F401

    __all__.append("SpatialModelMixin")
except ImportError:
    pass
