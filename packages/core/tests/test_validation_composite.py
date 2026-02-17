from unittest.mock import AsyncMock

import pytest

from cqrs_ddd_core.ports.validation import IValidator
from cqrs_ddd_core.validation.composite import CompositeValidator
from cqrs_ddd_core.validation.result import ValidationResult


# Use a dummy command, type doesn't matter for these mocks
class Cmd:
    pass


@pytest.mark.asyncio
async def test_composite_validator_success() -> None:
    v1 = AsyncMock(spec=IValidator)
    v1.validate.return_value = ValidationResult.success()

    v2 = AsyncMock(spec=IValidator)
    v2.validate.return_value = ValidationResult.success()

    composite = CompositeValidator([v1, v2])
    result = await composite.validate(Cmd())

    assert result.is_valid
    assert result.errors == {}
    v1.validate.assert_called()
    v2.validate.assert_called()


@pytest.mark.asyncio
async def test_composite_validator_merges_failures() -> None:
    v1 = AsyncMock(spec=IValidator)
    v1.validate.return_value = ValidationResult.failure({"field1": ["error1"]})

    v2 = AsyncMock(spec=IValidator)
    v2.validate.return_value = ValidationResult.failure({"field2": ["error2"]})

    v3 = AsyncMock(spec=IValidator)
    v3.validate.return_value = ValidationResult.failure({"field1": ["error3"]})

    composite = CompositeValidator()
    composite.add(v1)
    composite.add(v2)
    composite.add(v3)

    result = await composite.validate(Cmd())

    assert not result.is_valid
    assert result.errors["field1"] == ["error1", "error3"]
    assert result.errors["field2"] == ["error2"]


def test_validation_result_methods() -> None:
    r1 = ValidationResult.failure({"a": ["1"]})
    r1.add_error("b", "2")

    assert r1.errors["a"] == ["1"]
    assert r1.errors["b"] == ["2"]

    assert not r1
    assert not r1.is_valid

    r2 = ValidationResult.success()
    assert r2
    assert r2.is_valid
