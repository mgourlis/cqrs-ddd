from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, relationship

from cqrs_ddd_persistence_sqlalchemy.specifications.compiler import build_sqla_filter


class Base(DeclarativeBase):
    pass


class PostRecord(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True)
    title = Column(String)
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("UserRecord", back_populates="posts")


class UserRecord(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    status = Column(String)
    posts = relationship("PostRecord", back_populates="user")


def test_build_sqla_filter_basic():
    data = {"op": "=", "attr": "status", "val": "active"}
    expr = build_sqla_filter(UserRecord, data)

    # Check if the expression is correct (SQLAlchemy internal comparison)
    assert str(expr.compile()) == "users.status = :status_1"


def test_build_sqla_filter_and():
    data = {
        "op": "and",
        "conditions": [
            {"op": "=", "attr": "status", "val": "active"},
            {"op": "ilike", "attr": "name", "val": "John%"},
        ],
    }
    expr = build_sqla_filter(UserRecord, data)
    compiled = str(expr.compile())
    assert "users.status = :status_1" in compiled
    assert "lower(users.name) LIKE lower(:name_1)" in compiled


def test_build_sqla_filter_relationship_any():
    data = {
        "op": "ilike",
        "attr": "posts.title",
        "val": "%python%",
    }
    expr = build_sqla_filter(UserRecord, data)
    compiled = str(expr.compile())

    # SQLAlchemy .any() generates an EXISTS clause
    assert "EXISTS" in compiled
    assert "posts.title" in compiled


def test_build_sqla_filter_relationship_has():
    data = {
        "op": "=",
        "attr": "user.name",
        "val": "John Doe",
    }
    expr = build_sqla_filter(PostRecord, data)
    compiled = str(expr.compile())

    # SQLAlchemy .has() generates an EXISTS clause for many-to-one
    assert "EXISTS" in compiled
    assert "users.name" in compiled


def test_build_sqla_filter_not():
    data = {
        "op": "not",
        "conditions": [{"op": "=", "attr": "status", "val": "active"}],
    }
    expr = build_sqla_filter(UserRecord, data)
    compiled = str(expr.compile())
    # SQLAlchemy may optimize NOT(col == val) to col != val
    assert "users.status != :status_1" in compiled or "NOT" in compiled


def test_build_sqla_filter_jsonb():
    data = {
        "op": "json_contains",
        "attr": "metadata",
        "val": {"key": "value"},
    }
    # Mock metadata column on UserRecord for this test
    from sqlalchemy.dialects.postgresql import JSONB

    UserRecord.metadata_col = Column("metadata", JSONB)

    data["attr"] = "metadata_col"
    expr = build_sqla_filter(UserRecord, data)
    compiled = str(expr.compile())
    assert "@>" in compiled
    assert '\'{"key": "value"}\'::jsonb' in compiled


def test_build_sqla_filter_geometry():
    data = {
        "op": "intersects",
        "attr": "location",
        "val": {"type": "Point", "coordinates": [0, 0]},
    }
    # Mock location column
    UserRecord.location = Column("location", String)  # Simplified for testing compile

    expr = build_sqla_filter(UserRecord, data)
    compiled = str(expr.compile())
    assert "ST_Intersects" in compiled
    assert "ST_GeomFromGeoJSON" in compiled
