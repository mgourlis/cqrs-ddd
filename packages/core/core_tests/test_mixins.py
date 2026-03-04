"""Tests for domain mixins (AuditableMixin, ArchivableMixin)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import BaseModel

from cqrs_ddd_core.domain.mixins import ArchivableMixin, AuditableMixin
from cqrs_ddd_core.primitives.exceptions import InvariantViolationError


class AuditableEntity(AuditableMixin, BaseModel):
    """Test entity with auditable fields."""

    id: str = ""
    name: str = ""


class ArchivableEntity(ArchivableMixin, BaseModel):
    """Test entity with archivable fields."""

    id: str = ""
    name: str = ""


class TestAuditableMixin:
    """Test AuditableMixin timestamp fields and touch method."""

    def test_created_at_defaults_to_current_time(self) -> None:
        """created_at is set to current UTC time by default."""
        before = datetime.now(timezone.utc)
        entity = AuditableEntity(id="e1", name="Test")
        after = datetime.now(timezone.utc)

        assert before <= entity.created_at <= after
        assert entity.created_at.tzinfo == timezone.utc

    def test_updated_at_defaults_to_current_time(self) -> None:
        """updated_at is set to current UTC time by default."""
        before = datetime.now(timezone.utc)
        entity = AuditableEntity(id="e1", name="Test")
        after = datetime.now(timezone.utc)

        assert before <= entity.updated_at <= after
        assert entity.updated_at.tzinfo == timezone.utc

    def test_created_at_and_updated_at_are_initially_equal(self) -> None:
        """created_at and updated_at are the same on creation."""
        entity = AuditableEntity(id="e1", name="Test")

        # They should be very close (within milliseconds)
        diff = abs((entity.created_at - entity.updated_at).total_seconds())
        assert diff < 0.1  # Within 100ms

    def test_touch_updates_updated_at(self) -> None:
        """touch() updates updated_at to current time."""
        entity = AuditableEntity(id="e1", name="Test")
        original_updated_at = entity.updated_at

        # Wait a tiny bit to ensure time difference
        import time

        time.sleep(0.01)

        entity.touch()

        assert entity.updated_at > original_updated_at
        assert entity.updated_at.tzinfo == timezone.utc

    def test_touch_does_not_change_created_at(self) -> None:
        """touch() does not modify created_at."""
        entity = AuditableEntity(id="e1", name="Test")
        original_created_at = entity.created_at

        import time

        time.sleep(0.01)

        entity.touch()

        assert entity.created_at == original_created_at

    def test_touch_can_be_called_multiple_times(self) -> None:
        """touch() can be called multiple times, each updating updated_at."""
        entity = AuditableEntity(id="e1", name="Test")

        import time

        times = []
        for _ in range(3):
            time.sleep(0.01)
            entity.touch()
            times.append(entity.updated_at)

        # Each call should produce a later timestamp
        assert times[0] < times[1] < times[2]


class TestArchivableMixin:
    """Test ArchivableMixin archive/restore functionality."""

    def test_archived_at_defaults_to_none(self) -> None:
        """archived_at is None by default."""
        entity = ArchivableEntity(id="e1", name="Test")

        assert entity.archived_at is None

    def test_archived_by_defaults_to_none(self) -> None:
        """archived_by is None by default."""
        entity = ArchivableEntity(id="e1", name="Test")

        assert entity.archived_by is None

    def test_is_archived_false_by_default(self) -> None:
        """is_archived returns False for non-archived entity."""
        entity = ArchivableEntity(id="e1", name="Test")

        assert not entity.is_archived

    def test_archive_sets_archived_at(self) -> None:
        """archive() sets archived_at to current time."""
        entity = ArchivableEntity(id="e1", name="Test")

        before = datetime.now(timezone.utc)
        entity.archive()
        after = datetime.now(timezone.utc)

        assert entity.archived_at is not None
        assert before <= entity.archived_at <= after
        assert entity.archived_at.tzinfo == timezone.utc

    def test_archive_with_by_parameter(self) -> None:
        """archive(by=...) sets archived_by."""
        entity = ArchivableEntity(id="e1", name="Test")

        entity.archive(by="admin@example.com")

        assert entity.archived_by == "admin@example.com"

    def test_archive_without_by_parameter(self) -> None:
        """archive() without by parameter leaves archived_by as None."""
        entity = ArchivableEntity(id="e1", name="Test")

        entity.archive()

        assert entity.archived_by is None

    def test_is_archived_true_after_archive(self) -> None:
        """is_archived returns True after archiving."""
        entity = ArchivableEntity(id="e1", name="Test")

        entity.archive()

        assert entity.is_archived

    def test_archive_already_archived_raises_error(self) -> None:
        """Archiving already-archived entity raises InvariantViolationError."""
        entity = ArchivableEntity(id="e1", name="Test")
        entity.archive()

        with pytest.raises(InvariantViolationError, match="Already archived"):
            entity.archive()

    def test_restore_clears_archived_at(self) -> None:
        """restore() clears archived_at."""
        entity = ArchivableEntity(id="e1", name="Test")
        entity.archive()

        entity.restore()

        assert entity.archived_at is None

    def test_restore_clears_archived_by(self) -> None:
        """restore() clears archived_by."""
        entity = ArchivableEntity(id="e1", name="Test")
        entity.archive(by="admin@example.com")

        entity.restore()

        assert entity.archived_by is None

    def test_is_archived_false_after_restore(self) -> None:
        """is_archived returns False after restore."""
        entity = ArchivableEntity(id="e1", name="Test")
        entity.archive()

        entity.restore()

        assert not entity.is_archived

    def test_restore_not_archived_raises_error(self) -> None:
        """Restoring non-archived entity raises InvariantViolationError."""
        entity = ArchivableEntity(id="e1", name="Test")

        with pytest.raises(InvariantViolationError, match="Not archived"):
            entity.restore()

    def test_archive_restore_cycle(self) -> None:
        """Entity can be archived and restored multiple times."""
        entity = ArchivableEntity(id="e1", name="Test")

        # First cycle
        entity.archive(by="user1")
        assert entity.is_archived
        entity.restore()
        assert not entity.is_archived

        # Second cycle
        entity.archive(by="user2")
        assert entity.is_archived
        assert entity.archived_by == "user2"
        entity.restore()
        assert not entity.is_archived


class TestCombinedMixins:
    """Test using both mixins together."""

    class CombinedEntity(AuditableMixin, ArchivableMixin, BaseModel):
        """Entity with both audit and archive features."""

        id: str = ""
        name: str = ""

    def test_entity_has_both_mixin_features(self) -> None:
        """Entity can use features from both mixins."""
        entity = self.CombinedEntity(id="e1", name="Test")

        # Auditable features
        assert entity.created_at is not None
        assert entity.updated_at is not None
        entity.touch()

        # Archivable features
        assert not entity.is_archived
        entity.archive()
        assert entity.is_archived
        entity.restore()
        assert not entity.is_archived

    def test_touch_and_archive_work_independently(self) -> None:
        """touch() and archive() work independently."""
        entity = self.CombinedEntity(id="e1", name="Test")

        entity.touch()
        updated_at_after_touch = entity.updated_at

        entity.archive()

        # Touch should not affect archive state
        assert entity.is_archived
        assert entity.updated_at == updated_at_after_touch
