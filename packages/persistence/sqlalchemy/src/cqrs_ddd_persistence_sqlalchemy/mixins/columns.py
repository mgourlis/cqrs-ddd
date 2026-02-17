"""
SQLAlchemy column mixins that mirror domain mixins.

Use these to build versioned, auditable, or archivable table models
without repeating column definitions.

Indexes:
- Single-column: use ``index=True`` on ``mapped_column(...)``.
- Composite or partial indexes: set ``__table_args__ = (Index(...),)`` on your
  model (or use a mixin's ``__table_args__``). For partial indexes use
  ``postgresql_where`` and ``sqlite_where`` on ``Index(...)``.
- Partial unique constraints: use ``Index(..., unique=True, postgresql_where=...,
  sqlite_where=...)``. For archivable models, set ``__archivable_unique_columns__
  = ["code"]`` or ``("code",)`` for one constraint; use ``[["code"], ["foo", "bar"]]``
  or ``(("code",), ("foo", "bar"))`` for both unique code and unique (foo, bar).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class VersionMixin:
    """Adds integer version column with SQLAlchemy OCC via version_id_col."""

    version: Mapped[int] = mapped_column(Integer, default=0)

    @declared_attr.directive
    def __mapper_args__(cls: Any) -> dict[str, Any]:  # noqa: N805
        return {
            "version_id_col": cls.__table__.c.version,
            "version_id_generator": False,
        }


class AuditableModelMixin:
    """Adds created_at and updated_at columns. Mirrors domain AuditableMixin."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )


class ArchivableModelMixin:
    """
    Adds archived_at and archived_by columns. Mirrors domain ArchivableMixin.

    Defines partial indexes for filtering by archival status, and optionally
    a partial unique index for "unique among active rows" when you set
    ``__archivable_unique_columns__`` on your model.

    Partial indexes:
    - Active rows (archived_at IS NULL): efficient "list non-archived" queries.
    - Archived rows (archived_at IS NOT NULL): efficient "list archived" queries.
    - If you set ``__archivable_unique_columns__``, adds partial UNIQUE
      constraint(s) WHERE archived_at IS NULL. Use a single sequence for one
      constraint, or a sequence of sequences for several. Tuple or list
      syntax both work, e.g. ``["code"]`` or ``("code",)`` for unique code;
      ``[["code"], ["foo", "bar"]]`` or ``(("code",), ("foo", "bar"))`` for
      unique code and unique (foo, bar).

    If your subclass defines ``__table_args__``, include these indexes (e.g. by
    extending the tuple) or they will be omitted.

    Override Example:
    ```python
    class MyModel(ArchivableModelMixin, Base):
    __tablename__ = "my_table"
    __archivable_unique_columns__ = ["slug"]

    @declared_attr.directive
    def __table_args__(cls):
        # Merge mixin indexes with local args
        return ArchivableModelMixin.__table_args__(cls) + (
            UniqueConstraint("some_other_col"),
            {"comment": "My table comment"},
        )
    ```
    """

    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    archived_by: Mapped[str | None] = mapped_column(String, nullable=True)

    @declared_attr.directive
    def __table_args__(cls: Any) -> tuple[Any, ...]:  # noqa: N805
        # Partial index: active rows (archived_at IS NULL)
        active_where = cls.archived_at.is_(None)
        idx_active = Index(
            f"ix_{cls.__tablename__}_archivable_active",
            cls.archived_at,
            postgresql_where=active_where,
            sqlite_where=active_where,
        )
        # Partial index: archived rows (archived_at IS NOT NULL)
        archived_where = cls.archived_at.is_not(None)
        idx_archived = Index(
            f"ix_{cls.__tablename__}_archivable_archived",
            cls.archived_at,
            postgresql_where=archived_where,
            sqlite_where=archived_where,
        )
        result: list[Index] = [idx_active, idx_archived]
        # Partial unique constraint(s): unique on given column(s) among active rows
        raw = getattr(cls, "__archivable_unique_columns__", None)
        if raw:
            # Normalize: ["code"] or ("code",) -> one; [["code"], ["foo","bar"]] -> two
            if raw and isinstance(next(iter(raw), None), str):
                constraints: list[tuple[str, ...]] = [tuple(raw)]
            else:
                constraints = [tuple(cols) for cols in raw]
            for cols in constraints:
                columns = [getattr(cls, c) for c in cols]
                name_suffix = "_".join(cols)
                uq = Index(
                    f"uq_{cls.__tablename__}_archivable_{name_suffix}",
                    *columns,
                    unique=True,
                    postgresql_where=active_where,
                    sqlite_where=active_where,
                )
                result.append(uq)
        return tuple(result)
