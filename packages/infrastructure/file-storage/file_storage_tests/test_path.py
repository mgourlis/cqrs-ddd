"""Tests for BlobPath and validate_path."""

from __future__ import annotations

import pytest

from cqrs_ddd_file_storage.exceptions import PathTraversalError
from cqrs_ddd_file_storage.path import BlobPath, validate_path


class TestValidatePath:
    def test_normal_path(self) -> None:
        assert validate_path("tenant/invoice/1/file.pdf") == "tenant/invoice/1/file.pdf"

    def test_rejects_absolute_path(self) -> None:
        with pytest.raises(PathTraversalError):
            validate_path("/etc/passwd")

    def test_rejects_dot_dot(self) -> None:
        with pytest.raises(PathTraversalError):
            validate_path("../../etc/passwd")

    def test_rejects_embedded_dot_dot(self) -> None:
        with pytest.raises(PathTraversalError):
            validate_path("tenant/../other/file.txt")

    def test_rejects_backslash(self) -> None:
        with pytest.raises(PathTraversalError):
            validate_path("tenant\\file.txt")

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            validate_path("")

    def test_normalises_redundant_slashes(self) -> None:
        result = validate_path("a/./b//c")
        assert ".." not in result


class TestBlobPath:
    def test_build(self) -> None:
        path = BlobPath.build(
            tenant_id="t1",
            entity_type="invoice",
            entity_id="inv-123",
            filename="scan.pdf",
        )
        assert path == "t1/invoice/inv-123/scan.pdf"

    def test_str(self) -> None:
        bp = BlobPath("t1", "order", "o1", "receipt.pdf")
        assert str(bp) == "t1/order/o1/receipt.pdf"

    def test_repr(self) -> None:
        bp = BlobPath("t1", "order", "o1", "receipt.pdf")
        assert "BlobPath(" in repr(bp)

    def test_properties(self) -> None:
        bp = BlobPath("t1", "order", "o1", "receipt.pdf")
        assert bp.tenant_id == "t1"
        assert bp.entity_type == "order"
        assert bp.entity_id == "o1"
        assert bp.filename == "receipt.pdf"

    def test_equality(self) -> None:
        a = BlobPath("t1", "type", "id", "f.txt")
        b = BlobPath("t1", "type", "id", "f.txt")
        assert a == b

    def test_hash(self) -> None:
        a = BlobPath("t1", "type", "id", "f.txt")
        b = BlobPath("t1", "type", "id", "f.txt")
        assert hash(a) == hash(b)

    def test_rejects_slash_in_segment(self) -> None:
        with pytest.raises(ValueError, match="path separators"):
            BlobPath("t1/t2", "type", "id", "f.txt")

    def test_rejects_dot_dot_segment(self) -> None:
        with pytest.raises(PathTraversalError):
            BlobPath("..", "type", "id", "f.txt")

    def test_rejects_empty_segment(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            BlobPath("", "type", "id", "f.txt")

    def test_rejects_backslash_in_segment(self) -> None:
        with pytest.raises(ValueError, match="path separators"):
            BlobPath("t1\\t2", "type", "id", "f.txt")

    def test_inequality_different_paths(self) -> None:
        a = BlobPath("t1", "type", "id", "a.txt")
        b = BlobPath("t1", "type", "id", "b.txt")
        assert a != b

    def test_not_equal_to_other_type(self) -> None:
        bp = BlobPath("t1", "type", "id", "f.txt")
        assert bp != "t1/type/id/f.txt"
