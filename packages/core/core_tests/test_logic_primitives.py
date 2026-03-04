import pytest

from cqrs_ddd_core.primitives.id_generator import UUID4Generator

# --- ID Generator Tests ---


def test_uuid4_generator() -> None:
    """Verifies that UUID4Generator produces valid-looking UUIDs."""
    generator = UUID4Generator()
    id1 = generator.next_id()
    id2 = generator.next_id()

    assert isinstance(id1, str)
    assert len(id1) == 36
    assert id1 != id2
    # Basic format check: 8-4-4-4-12 hex chars
    parts = id1.split("-")
    assert len(parts) == 5
    assert [len(p) for p in parts] == [8, 4, 4, 4, 12]


# --- Exception Tests ---


def test_domain_error() -> None:
    """Verifies DomainError can be raised and caught."""
    from cqrs_ddd_core.primitives.exceptions import DomainError

    with pytest.raises(DomainError) as exc:
        raise DomainError("test error")
    assert str(exc.value) == "test error"


def test_specific_domain_errors() -> None:
    """Verifies specific domain error types."""
    from cqrs_ddd_core.primitives.exceptions import (
        ConcurrencyError,
        DomainConcurrencyError,
        DomainError,
        InvariantViolationError,
        NotFoundError,
        OptimisticLockingError,
        PersistenceError,
    )

    # Base Concurrency
    with pytest.raises(ConcurrencyError):
        raise ConcurrencyError("base fail")

    # --- Semantic (Domain) ---
    with pytest.raises(DomainConcurrencyError) as exc:
        raise DomainConcurrencyError("semantic fail")
    assert isinstance(exc.value, ConcurrencyError)
    assert isinstance(exc.value, DomainError)

    # --- Technical (Infrastructure) ---
    with pytest.raises(OptimisticLockingError) as exc:
        raise OptimisticLockingError("technical fail")
    assert isinstance(exc.value, ConcurrencyError)
    assert isinstance(exc.value, PersistenceError)

    with pytest.raises(NotFoundError):
        raise NotFoundError("not found")

    with pytest.raises(InvariantViolationError):
        raise InvariantViolationError("invariant fail")
