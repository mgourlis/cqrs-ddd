import pytest
from pydantic import Field

from cqrs_ddd_core.cqrs.command import Command
from cqrs_ddd_core.validation.pydantic import PydanticValidator

# --- Test Models ---


class ValidatableCommand(Command):
    name: str = Field(..., min_length=3)
    age: int = Field(..., gt=0)


class NonPydanticCommand(Command):
    name: str


# --- Tests ---


@pytest.mark.asyncio
async def test_validation_success() -> None:
    validator = PydanticValidator()
    cmd = ValidatableCommand(name="Alice", age=30)

    result = await validator.validate(cmd)

    assert result.is_valid
    assert result.errors == {}


@pytest.mark.asyncio
async def test_validation_failure() -> None:
    validator = PydanticValidator()

    # We use construct() or equivalent to bypass validation.
    cmd = ValidatableCommand.model_construct(name="Al", age=-5)

    result = await validator.validate(cmd)

    assert not result.is_valid
    assert "name" in str(result.errors) or "name" in result.errors
    assert "age" in str(result.errors) or "age" in result.errors


@pytest.mark.asyncio
async def test_validation_skips_non_pydantic() -> None:
    validator = PydanticValidator()
    cmd = NonPydanticCommand(name="test")

    # Should skip efficiently
    result = await validator.validate(cmd)

    assert result.is_valid
