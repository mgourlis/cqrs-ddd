"""Index definition helpers — compound, text, TTL, geospatial (2dsphere)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .connection import MongoConnectionManager


async def create_compound_index(
    connection: MongoConnectionManager,
    database: str,
    collection: str,
    keys: list[tuple[str, int]],
    *,
    name: str | None = None,
    unique: bool = False,
) -> str:
    """Create a compound index. keys: [(field, 1|(-1)), ...]. Returns index name."""
    coll = connection.client.get_database(database).get_collection(collection)
    return await coll.create_index(keys, name=name, unique=unique)


async def create_text_index(
    connection: MongoConnectionManager,
    database: str,
    collection: str,
    fields: list[tuple[str, str]],
    *,
    name: str | None = None,
) -> str:
    """Create a text index. fields: [(field_name, 'text'), ...]."""
    coll = connection.client.get_database(database).get_collection(collection)
    return await coll.create_index(fields, name=name)


async def create_ttl_index(
    connection: MongoConnectionManager,
    database: str,
    collection: str,
    field: str,
    expire_after_seconds: int,
    *,
    name: str | None = None,
) -> str:
    """Create a TTL index for ephemeral data."""
    coll = connection.client.get_database(database).get_collection(collection)
    return await coll.create_index(
        [(field, 1)],
        expireAfterSeconds=expire_after_seconds,
        name=name or f"ttl_{field}",
    )


async def create_2dsphere_index(
    connection: MongoConnectionManager,
    database: str,
    collection: str,
    field: str,
    *,
    name: str | None = None,
) -> str:
    """Create a 2dsphere geospatial index."""
    coll = connection.client.get_database(database).get_collection(collection)
    return await coll.create_index(
        [(field, "2dsphere")],
        name=name or f"geo_{field}",
    )
