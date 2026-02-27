# Validation Layer - Command/Query Validation

**Package:** `cqrs_ddd_core.validation`
**Purpose:** Validation utilities for commands and queries

---

## Overview

The validation layer provides **flexible validation** for commands and queries.

### Components

| Component | Purpose | File |
|-----------|---------|------|
| **PydanticValidator** | Pydantic-based validation | `pydantic.py` |
| **CompositeValidator** | Combine multiple validators | `composite.py` |
| **ValidationResult** | Validation result wrapper | `result.py` |

---

## PydanticValidator

### Implementation

```python
from cqrs_ddd_core.validation.pydantic import PydanticValidator

class PydanticValidator(IValidator):
    """
    Validator using Pydantic models.

    Features:
    - Automatic field validation
    - Custom validators
    - Type checking
    """

    async def validate(self, obj: Any) -> ValidationResult:
        """Validate object using Pydantic."""
        try:
            # Trigger Pydantic validation
            if hasattr(obj, 'model_validate'):
                obj.model_validate(obj.model_dump())
            return ValidationResult(is_valid=True, errors=[])
        except ValidationError as e:
            errors = [str(err) for err in e.errors()]
            return ValidationResult(is_valid=False, errors=errors)
```

### Usage Example

```python
from cqrs_ddd_core.validation.pydantic import PydanticValidator

# Define command with validation
class CreateOrderCommand(Command[str]):
    customer_id: str
    items: list[OrderItem]

    @field_validator("customer_id")
    @classmethod
    def validate_customer_id(cls, v: str) -> str:
        if not v.startswith("cust-"):
            raise ValueError("Invalid customer ID format")
        return v

    @field_validator("items")
    @classmethod
    def validate_items(cls, v: list[OrderItem]) -> list[OrderItem]:
        if not v:
            raise ValueError("Order must have at least one item")
        return v

# Validate
validator = PydanticValidator()
result = await validator.validate(command)

if not result.is_valid:
    print(f"Validation failed: {result.errors}")
```

---

## CompositeValidator

### Implementation

```python
from cqrs_ddd_core.validation.composite import CompositeValidator

class CompositeValidator(IValidator):
    """
    Combines multiple validators.

    Features:
    - Chain multiple validators
    - Aggregate errors
    - Short-circuit on first error
    """

    def __init__(self, validators: list[IValidator]):
        self.validators = validators

    async def validate(self, obj: Any) -> ValidationResult:
        """Run all validators and aggregate results."""
        all_errors = []

        for validator in self.validators:
            result = await validator.validate(obj)
            if not result.is_valid:
                all_errors.extend(result.errors)

        return ValidationResult(
            is_valid=len(all_errors) == 0,
            errors=all_errors,
        )
```

### Usage Example

```python
from cqrs_ddd_core.validation.composite import CompositeValidator
from cqrs_ddd_core.validation.pydantic import PydanticValidator

# Create custom validator
class BusinessRulesValidator(IValidator):
    async def validate(self, obj: Any) -> ValidationResult:
        errors = []

        if hasattr(obj, 'total'):
            if obj.total > 10000:
                errors.append("Order total exceeds maximum allowed")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

# Combine validators
validator = CompositeValidator([
    PydanticValidator(),
    BusinessRulesValidator(),
    AuthorizationValidator(),
])

# Validate
result = await validator.validate(command)

if not result.is_valid:
    for error in result.errors:
        print(f"Error: {error}")
```

---

## ValidationResult

### Implementation

```python
from cqrs_ddd_core.validation.result import ValidationResult

@dataclass
class ValidationResult:
    """
    Collects field-level validation errors.

    Attributes:
        errors: Dict mapping field names to list of error messages

    Properties:
        is_valid: True if no errors (property, not constructor param)

    Factory methods:
        success() -> ValidationResult
        failure(errors: dict[str, list[str]]) -> ValidationResult
    """

    errors: dict[str, list[str]] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """Check if validation passed."""
        return len(self.errors) == 0

    @classmethod
    def success(cls) -> ValidationResult:
        """Create successful validation result."""
        return cls()

    @classmethod
    def failure(cls, errors: dict[str, list[str]]) -> ValidationResult:
        """Create failed validation result."""
        return cls(errors=errors)

    def merge(self, other: ValidationResult) -> ValidationResult:
        """Merge another result into this one."""
        ...

    def add_error(self, field_name: str, message: str) -> None:
        """Add a single error for field_name."""
        ...
```

### Usage Examples

#### Basic Usage

```python
from cqrs_ddd_core.validation.result import ValidationResult

# Success result
result = ValidationResult.success()
if result.is_valid:
    print("Validation passed")

# Failure result
result = ValidationResult.failure({
    "name": ["Name is required", "Name must be at least 3 characters"],
    "email": ["Invalid email format"],
})

if not result.is_valid:
    for field, messages in result.errors.items():
        print(f"{field}: {', '.join(messages)}")
```

#### Using Constructor

```python
from cqrs_ddd_core.validation.result import ValidationResult

# Create with empty errors
result = ValidationResult()
assert result.is_valid

# Create with errors
result = ValidationResult(errors={"age": ["Must be positive"]})
assert not result.is_valid
```

#### Adding Errors Dynamically

```python
result = ValidationResult()

# Add single errors
result.add_error("name", "Name is required")
result.add_error("name", "Name must be at least 3 characters")
result.add_error("email", "Invalid email format")

print(result.errors)
# {
#     "name": ["Name is required", "Name must be at least 3 characters"],
#     "email": ["Invalid email format"]
# }
```

#### Merging Results

```python
from cqrs_ddd_core.validation.result import ValidationResult

# Create two results
result1 = ValidationResult.failure({"name": ["Name is required"]})
result2 = ValidationResult.failure({"email": ["Invalid email"], "name": ["Must be unique"]})

# Merge them
merged = result1.merge(result2)

print(merged.errors)
# {
#     "name": ["Name is required", "Must be unique"],
#     "email": ["Invalid email"]
# }
```

#### Boolean Conversion

```python
result = ValidationResult.success()

if result:  # Uses __bool__
    print("Valid")
else:
    print("Invalid")
```

---

## Integration with Middleware

### ValidatorMiddleware

```python
from cqrs_ddd_core.middleware.validation import ValidatorMiddleware

# Create validator
validator = CompositeValidator([
    PydanticValidator(),
    BusinessRulesValidator(),
])

# Register middleware
middleware_registry = MiddlewareRegistry()
middleware_registry.register(ValidatorMiddleware(validator), priority=10)

# All commands/queries validated automatically
mediator = Mediator(
    registry=handler_registry,
    uow_factory=uow_factory,
    middleware_registry=middleware_registry,
)

# Invalid command raises ValidationError
command = CreateOrderCommand(customer_id="", items=[])  # Invalid
try:
    response = await mediator.send(command)
except ValidationError as e:
    print(f"Validation failed: {e.errors}")
```

---

## Custom Validators

### Creating Custom Validators

```python
from cqrs_ddd_core.ports.validation import IValidator
from cqrs_ddd_core.validation.result import ValidationResult

class AuthorizationValidator(IValidator):
    """Validates user authorization."""

    def __init__(self, auth_service: IAuthService):
        self.auth_service = auth_service

    async def validate(self, obj: Any) -> ValidationResult:
        errors = []

        # Check authorization
        if hasattr(obj, 'user_id'):
            is_authorized = await self.auth_service.check_permission(
                user_id=obj.user_id,
                permission="create_order",
            )
            if not is_authorized:
                errors.append("User not authorized to create orders")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

# Use in composite validator
validator = CompositeValidator([
    PydanticValidator(),
    AuthorizationValidator(auth_service),
])
```

---

## Best Practices

### ✅ DO: Use Pydantic for Field Validation

```python
class CreateOrderCommand(Command[str]):
    customer_id: str
    items: list[OrderItem]
    total: float

    @field_validator("customer_id")
    @classmethod
    def validate_customer_id(cls, v: str) -> str:
        if not v.startswith("cust-"):
            raise ValueError("Invalid customer ID format")
        return v

    @field_validator("total")
    @classmethod
    def validate_total(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Total must be positive")
        return v
```

### ❌ DON'T: Validate in Handlers

```python
# BAD: Validation in handler
class CreateOrderHandler(CommandHandler[str]):
    async def handle(self, command: CreateOrderCommand) -> CommandResponse[str]:
        if not command.customer_id.startswith("cust-"):
            raise ValueError("Invalid customer ID")  # Should be in validator

        # Business logic
        order = Order.create(...)
        return CommandResponse(result=order.id)
```

### ✅ DO: Use CompositeValidator for Complex Validation

```python
# Combine multiple validators
validator = CompositeValidator([
    PydanticValidator(),           # Field validation
    BusinessRulesValidator(),      # Business rules
    AuthorizationValidator(auth),  # Authorization
])
```

### ❌ DON'T: Create Monolithic Validators

```python
# BAD: Monolithic validator with all logic
class OrderValidator(IValidator):
    async def validate(self, obj: Any) -> ValidationResult:
        errors = []

        # Field validation
        if not obj.customer_id.startswith("cust-"):
            errors.append("Invalid customer ID")

        # Business rules
        if obj.total > 10000:
            errors.append("Total too high")

        # Authorization
        if not await self.check_permission(obj.user_id):
            errors.append("Not authorized")

        # Too much responsibility - split into separate validators
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
```

---

## Summary

**Key Features:**
- Pydantic-based validation
- Composite validation
- Flexible and extensible
- Middleware integration

**Components:**
- `PydanticValidator` - Pydantic validation
- `CompositeValidator` - Combine validators
- `ValidationResult` - Result wrapper

---

**Last Updated:** February 22, 2026
**Package:** `cqrs_ddd_core.validation`
