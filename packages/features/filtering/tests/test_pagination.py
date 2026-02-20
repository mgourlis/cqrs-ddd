"""Tests for PaginationParser."""

from __future__ import annotations

from cqrs_ddd_filtering.pagination import PaginationParser


def test_parse_offset_limit() -> None:
    p = PaginationParser()
    r = p.parse({"offset": "20", "limit": "10"})
    assert r.offset == 20
    assert r.limit == 10
    assert r.cursor is None


def test_encode_cursor() -> None:
    s = PaginationParser.encode_cursor({"id": "x", "created_at": "2025-01-01"})
    assert isinstance(s, str)
    assert len(s) > 0
