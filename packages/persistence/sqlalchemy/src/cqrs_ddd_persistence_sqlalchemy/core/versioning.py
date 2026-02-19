"""Shared helpers for optimistic locking (version column) on SQLAlchemy models."""

from __future__ import annotations

from typing import Any


def _model_has_version_column(model: Any) -> bool:
    """Return True if the model has a mapped 'version' column."""
    table = getattr(model, "__table__", None)
    if table is None:
        return False
    cols = getattr(table, "c", None)
    return cols is not None and "version" in cols


def set_version_for_insert(model: Any) -> None:
    """Set version to 1 on the model for a new insert (entity.version == 0)."""
    if _model_has_version_column(model):
        model.version = 1
    elif hasattr(model, "_version"):
        object.__setattr__(model, "_version", 1)


def set_version_after_merge(merged: Any, entity: Any) -> None:
    """Set version on merged model and entity after an update merge."""
    if _model_has_version_column(merged):
        merged.version = entity.version + 1
    object.__setattr__(entity, "_version", entity.version + 1)
