"""Tests for FilterParser and syntaxes."""

from __future__ import annotations

import pytest
from cqrs_ddd_filtering.exceptions import FieldNotAllowedError
from cqrs_ddd_filtering.parser import FilterParser
from cqrs_ddd_filtering.syntax import JsonFilterSyntax
from cqrs_ddd_filtering.whitelist import FieldWhitelist


def test_parse_colon_filter() -> None:
    parser = FilterParser()
    spec, options = parser.parse({"filter": "status:eq:active"})
    assert spec is not None
    assert options.limit is None
    assert options.offset is None


def test_parse_with_whitelist() -> None:
    whitelist = FieldWhitelist(
        filterable_fields={"status": {"eq", "in"}, "amount": {"gte"}},
        sortable_fields={"created_at"},
        projectable_fields={"id", "status"},
    )
    parser = FilterParser()
    spec, options = parser.parse(
        {"filter": "status:eq:active", "sort": "created_at", "limit": "10"},
        whitelist=whitelist,
    )
    assert options.sort == [("created_at", "asc")]
    assert options.limit == 10


def test_whitelist_rejects_unknown_field() -> None:
    whitelist = FieldWhitelist(filterable_fields={"status": {"eq"}})
    parser = FilterParser()
    with pytest.raises(FieldNotAllowedError):
        parser.parse({"filter": "other:eq:1"}, whitelist=whitelist)


def test_json_syntax() -> None:
    parser = FilterParser(default_syntax=JsonFilterSyntax())
    spec_dict = {"and": [{"field": "status", "op": "eq", "value": "active"}]}
    spec, _ = parser.parse({"filter": spec_dict})
    assert spec is not None
