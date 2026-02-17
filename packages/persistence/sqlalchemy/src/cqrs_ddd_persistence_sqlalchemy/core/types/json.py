from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON, TypeDecorator


class JSONType(TypeDecorator[dict[str, Any]]):
    """
    Dialect-agnostic JSON type.
    Uses JSONB on PostgreSQL and standard JSON on other dialects (like SQLite).
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())
