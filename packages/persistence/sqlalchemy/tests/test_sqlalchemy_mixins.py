"""Tests for SQLAlchemy model mixins (VersionMixin, AuditableModelMixin, ArchivableModelMixin)."""

from __future__ import annotations

from sqlalchemy import Index, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from cqrs_ddd_persistence_sqlalchemy.mixins import (
    ArchivableModelMixin,
    AuditableModelMixin,
    VersionMixin,
)


class Base(DeclarativeBase):
    pass


# --- VersionMixin ---


class VersionedModel(VersionMixin, Base):
    __tablename__ = "versioned"
    id: Mapped[str] = mapped_column(String, primary_key=True)


def test_version_mixin_adds_version_column() -> None:
    assert hasattr(VersionedModel, "version")
    col = VersionedModel.__table__.c.version
    assert col is not None
    assert not col.nullable


def test_version_mixin_mapper_args() -> None:
    args = VersionedModel.__mapper_args__
    assert "version_id_col" in args
    assert args["version_id_col"] is VersionedModel.__table__.c.version
    assert args.get("version_id_generator") is False


# --- AuditableModelMixin ---


class AuditableModel(AuditableModelMixin, Base):
    __tablename__ = "auditable"
    id: Mapped[str] = mapped_column(String, primary_key=True)


def test_auditable_mixin_adds_created_at_updated_at() -> None:
    assert hasattr(AuditableModel, "created_at")
    assert hasattr(AuditableModel, "updated_at")
    t = AuditableModel.__table__
    assert t.c.created_at is not None
    assert t.c.updated_at is not None


def test_auditable_mixin_updated_at_indexed() -> None:
    updated_col = AuditableModel.__table__.c.updated_at
    assert updated_col.index is True


# --- ArchivableModelMixin: no unique columns ---


class ArchivableOnly(ArchivableModelMixin, Base):
    __tablename__ = "archivable_only"
    id: Mapped[str] = mapped_column(String, primary_key=True)


def test_archivable_mixin_adds_archived_columns() -> None:
    assert hasattr(ArchivableOnly, "archived_at")
    assert hasattr(ArchivableOnly, "archived_by")
    t = ArchivableOnly.__table__
    assert t.c.archived_at is not None
    assert t.c.archived_by is not None


def test_archivable_without_unique_columns_has_only_active_archived_indexes() -> None:
    indexes = list(ArchivableOnly.__table__.indexes)
    # Column index on archived_at (index=True) plus two partial indexes from mixin
    names = {ix.name for ix in indexes}
    assert "ix_archivable_only_archivable_active" in names
    assert "ix_archivable_only_archivable_archived" in names
    unique_indexes = [ix for ix in indexes if getattr(ix, "unique", False)]
    assert len(unique_indexes) == 0


# --- ArchivableModelMixin: single unique constraint (tuple) ---


class ArchivableUniqueTuple(ArchivableModelMixin, Base):
    __tablename__ = "archivable_uq_tuple"
    __archivable_unique_columns__ = ("code",)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    code: Mapped[str] = mapped_column(String, nullable=False)


def test_archivable_single_unique_tuple() -> None:
    indexes = list(ArchivableUniqueTuple.__table__.indexes)
    unique_indexes = [ix for ix in indexes if getattr(ix, "unique", False)]
    assert len(unique_indexes) == 1
    assert unique_indexes[0].name == "uq_archivable_uq_tuple_archivable_code"


# --- ArchivableModelMixin: single unique constraint (list) ---


class ArchivableUniqueList(ArchivableModelMixin, Base):
    __tablename__ = "archivable_uq_list"
    __archivable_unique_columns__ = ["code"]
    id: Mapped[str] = mapped_column(String, primary_key=True)
    code: Mapped[str] = mapped_column(String, nullable=False)


def test_archivable_single_unique_list() -> None:
    indexes = list(ArchivableUniqueList.__table__.indexes)
    unique_indexes = [ix for ix in indexes if getattr(ix, "unique", False)]
    assert len(unique_indexes) == 1
    assert unique_indexes[0].name == "uq_archivable_uq_list_archivable_code"


# --- ArchivableModelMixin: multiple unique constraints (tuple) ---


class ArchivableMultiUniqueTuple(ArchivableModelMixin, Base):
    __tablename__ = "archivable_multi_tuple"
    __archivable_unique_columns__ = (("code",), ("foo", "bar"))
    id: Mapped[str] = mapped_column(String, primary_key=True)
    code: Mapped[str] = mapped_column(String, nullable=False)
    foo: Mapped[str] = mapped_column(String, nullable=False)
    bar: Mapped[str] = mapped_column(String, nullable=False)


def test_archivable_multiple_unique_tuple() -> None:
    indexes = list(ArchivableMultiUniqueTuple.__table__.indexes)
    unique_indexes = [ix for ix in indexes if getattr(ix, "unique", False)]
    assert len(unique_indexes) == 2
    names = {ix.name for ix in unique_indexes}
    assert names == {
        "uq_archivable_multi_tuple_archivable_code",
        "uq_archivable_multi_tuple_archivable_foo_bar",
    }


# --- ArchivableModelMixin: multiple unique constraints (list) ---


class ArchivableMultiUniqueList(ArchivableModelMixin, Base):
    __tablename__ = "archivable_multi_list"
    __archivable_unique_columns__ = [["code"], ["foo", "bar"]]
    id: Mapped[str] = mapped_column(String, primary_key=True)
    code: Mapped[str] = mapped_column(String, nullable=False)
    foo: Mapped[str] = mapped_column(String, nullable=False)
    bar: Mapped[str] = mapped_column(String, nullable=False)


def test_archivable_multiple_unique_list() -> None:
    indexes = list(ArchivableMultiUniqueList.__table__.indexes)
    unique_indexes = [ix for ix in indexes if getattr(ix, "unique", False)]
    assert len(unique_indexes) == 2
    names = {ix.name for ix in unique_indexes}
    assert names == {
        "uq_archivable_multi_list_archivable_code",
        "uq_archivable_multi_list_archivable_foo_bar",
    }


# --- Partial index predicates (dialect_options store postgresql_where / sqlite_where) ---


def _index_has_partial_where(index: Index) -> bool:
    pg = index.dialect_options.get("postgresql", {})
    sqlite = index.dialect_options.get("sqlite", {})
    return "where" in pg and "where" in sqlite


def test_archivable_partial_indexes_have_where_clause() -> None:
    # Only mixin-defined indexes have partial where (not the simple archived_at index)
    mixin_index_names = {
        "ix_archivable_only_archivable_active",
        "ix_archivable_only_archivable_archived",
    }
    for ix in ArchivableOnly.__table__.indexes:
        if ix.name in mixin_index_names:
            assert _index_has_partial_where(ix)


def test_archivable_unique_indexes_are_partial() -> None:
    for ix in ArchivableUniqueList.__table__.indexes:
        if getattr(ix, "unique", False):
            assert _index_has_partial_where(ix)
