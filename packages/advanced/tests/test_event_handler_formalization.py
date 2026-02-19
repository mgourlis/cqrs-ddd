"""Comprehensive tests for event handler formalization."""

import pytest

from cqrs_ddd_advanced_core.domain.aggregate_mixin import (
    EventSourcedAggregateMixin,
)
from cqrs_ddd_advanced_core.domain.event_handlers import (
    aggregate_event_handler,
    aggregate_event_handler_validator,
    get_event_handler_config,
    get_handler_event_type,
    is_aggregate_event_handler,
)
from cqrs_ddd_advanced_core.domain.event_validation import (
    EventValidationConfig,
    EventValidator,
)
from cqrs_ddd_advanced_core.event_sourcing.loader import DefaultEventApplicator
from cqrs_ddd_advanced_core.exceptions import (
    EventHandlerError,
    InvalidEventHandlerError,
    MissingEventHandlerError,
    StrictValidationViolationError,
)
from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.domain.events import DomainEvent

# ── Test Event Types ─────────────────────────────────────────────────────


class OrderCreated(DomainEvent, frozen=True):
    order_id: str = ""
    amount: float = 0.0
    currency: str = "EUR"


class OrderPaid(DomainEvent, frozen=True):
    order_id: str = ""
    transaction_id: str = ""


class OrderCancelled(DomainEvent, frozen=True):
    order_id: str = ""
    reason: str = ""


# ── Test Aggregates ───────────────────────────────────────────────────────


class OrderWithHandlers(AggregateRoot[str], EventSourcedAggregateMixin[str]):
    """Order aggregate with event handlers (snake_case = ruff-compliant)."""

    status: str = "pending"
    amount: float = 0.0
    currency: str = "EUR"

    def apply_order_created(self, event: OrderCreated) -> None:
        self.status = "created"
        self.amount = event.amount
        self.currency = event.currency

    def apply_order_paid(self, event: OrderPaid) -> None:
        self.status = "paid"

    def apply_order_cancelled(self, event: OrderCancelled) -> None:
        self.status = "cancelled"


class OrderWithFallback(AggregateRoot[str], EventSourcedAggregateMixin[str]):
    """Order aggregate with only fallback handler."""

    status: str = "pending"

    def apply_event(self, event: DomainEvent) -> None:
        """Generic fallback handler."""
        event_type = type(event).__name__
        if event_type == "OrderCreated":
            self.status = "created"
        elif event_type == "OrderPaid":
            self.status = "paid"


class OrderWithoutHandlers(AggregateRoot[str], EventSourcedAggregateMixin[str]):
    """Order aggregate without any handlers (for backward compatibility tests)."""

    status: str = "pending"


@aggregate_event_handler_validator(enabled=True, strict=False)
class OrderWithLenientValidator(AggregateRoot[str], EventSourcedAggregateMixin[str]):
    """Order aggregate with lenient validator configured."""

    status: str = "pending"

    def apply_order_created(self, event: OrderCreated) -> None:
        self.status = "created"


@aggregate_event_handler_validator(enabled=True, strict=True)
class OrderWithStrictValidator(AggregateRoot[str], EventSourcedAggregateMixin[str]):
    """Order aggregate with strict validator configured."""

    status: str = "pending"

    def apply_order_created(self, event: OrderCreated) -> None:
        self.status = "created"


# ── Mixin Tests ─────────────────────────────────────────────────────────


def test_has_handler_for_event_with_exact_handler() -> None:
    """Mixin returns True for exact handlers."""
    order = OrderWithHandlers(id="1")

    assert order.has_handler_for_event("OrderCreated")
    assert order.has_handler_for_event("OrderPaid")
    assert order.has_handler_for_event("OrderCancelled")


def test_has_handler_for_event_with_fallback() -> None:
    """Mixin returns True when only fallback handler exists."""
    order = OrderWithFallback(id="1")

    assert order.has_handler_for_event("OrderCreated")
    assert order.has_handler_for_event("OrderPaid")
    assert order.has_handler_for_event("OrderCancelled")


def test_has_handler_for_event_no_handler() -> None:
    """Mixin returns False when no handler exists."""
    order = OrderWithoutHandlers(id="1")

    assert not order.has_handler_for_event("OrderCreated")
    assert not order.has_handler_for_event("OrderPaid")


def test_get_handler_for_event_exact_handler() -> None:
    """Mixin returns exact handler when it exists."""
    order = OrderWithHandlers(id="1")

    handler = order.get_handler_for_event("OrderCreated")
    assert handler is not None
    assert callable(handler)

    # Call handler to verify it works
    event = OrderCreated(order_id="1", amount=100.0, currency="EUR")
    handler(event)
    assert order.status == "created"
    assert order.amount == 100.0


def test_get_handler_for_event_fallback_handler() -> None:
    """Mixin returns fallback handler when no exact handler exists."""
    order = OrderWithFallback(id="1")

    handler = order.get_handler_for_event("OrderCreated")
    assert handler is not None
    assert callable(handler)

    # Call handler to verify it works
    event = OrderCreated(order_id="1", amount=100.0, currency="EUR")
    handler(event)
    assert order.status == "created"


def test_get_handler_for_event_no_handler() -> None:
    """Mixin returns None when no handler exists."""
    order = OrderWithoutHandlers(id="1")

    handler = order.get_handler_for_event("OrderCreated")
    assert handler is None


def test_get_supported_event_types() -> None:
    """Mixin returns set of supported event types (method name suffix)."""
    order = OrderWithHandlers(id="1")

    supported = order._get_supported_event_types()

    assert "order_created" in supported
    assert "order_paid" in supported
    assert "order_cancelled" in supported


def test_get_supported_event_types_with_fallback() -> None:
    """Mixin includes marker for generic fallback handler."""
    order = OrderWithFallback(id="1")

    supported = order._get_supported_event_types()

    # Generic fallback marker
    assert "*" in supported


# ── Validation Tests ───────────────────────────────────────────────────────


def test_validation_enabled_raises_on_missing_handler() -> None:
    """Validator raises error when handler is missing and validation is enabled."""
    validator = EventValidator(EventValidationConfig(enabled=True, strict_mode=False))
    order = OrderWithoutHandlers(id="1")
    event = OrderCreated(order_id="1", amount=100.0, currency="EUR")

    with pytest.raises(MissingEventHandlerError) as exc_info:
        validator.validate_handler_exists(order, event)

    assert "OrderWithoutHandlers" in str(exc_info.value)
    assert "OrderCreated" in str(exc_info.value)


def test_validation_disabled_silently_ignores() -> None:
    """Validator does nothing when validation is disabled."""
    validator = EventValidator(EventValidationConfig(enabled=False))
    order = OrderWithoutHandlers(id="1")
    event = OrderCreated(order_id="1", amount=100.0, currency="EUR")

    # Should not raise
    validator.validate_handler_exists(order, event)


def test_validation_allows_exact_handler() -> None:
    """Validator passes when exact handler exists."""
    validator = EventValidator(EventValidationConfig(enabled=True, strict_mode=False))
    order = OrderWithHandlers(id="1")
    event = OrderCreated(order_id="1", amount=100.0, currency="EUR")

    # Should not raise
    validator.validate_handler_exists(order, event)


def test_validation_allows_fallback_when_allowed() -> None:
    """Validator allows fallback handler when configured."""
    validator = EventValidator(
        EventValidationConfig(
            enabled=True, strict_mode=False, allow_fallback_handler=True
        )
    )
    order = OrderWithFallback(id="1")
    event = OrderCreated(order_id="1", amount=100.0, currency="EUR")

    # Should not raise
    validator.validate_handler_exists(order, event)


def test_validation_rejects_fallback_when_not_allowed() -> None:
    """Validator rejects fallback when not configured to allow it."""
    validator = EventValidator(
        EventValidationConfig(
            enabled=True, strict_mode=False, allow_fallback_handler=False
        )
    )
    order = OrderWithFallback(id="1")
    event = OrderCreated(order_id="1", amount=100.0, currency="EUR")

    with pytest.raises(MissingEventHandlerError) as exc_info:
        validator.validate_handler_exists(order, event)

    assert "OrderWithFallback" in str(exc_info.value)


# ── Strict Mode Tests ──────────────────────────────────────────────────────


def test_strict_validation_requires_exact_handler() -> None:
    """Strict mode requires exact apply_<EventType> methods."""
    validator = EventValidator(EventValidationConfig(enabled=True, strict_mode=True))
    order = OrderWithHandlers(id="1")
    event = OrderCreated(order_id="1", amount=100.0, currency="EUR")

    # Should not raise (exact handler exists)
    validator.validate_handler_exists(order, event)


def test_strict_validation_rejects_fallback() -> None:
    """Strict mode rejects apply_event fallback."""
    validator = EventValidator(EventValidationConfig(enabled=True, strict_mode=True))
    order = OrderWithFallback(id="1")
    event = OrderCreated(order_id="1", amount=100.0, currency="EUR")

    with pytest.raises(StrictValidationViolationError) as exc_info:
        validator.validate_handler_exists(order, event)

    assert "OrderWithFallback" in str(exc_info.value)
    assert "Strict mode requires" in str(exc_info.value)


def test_strict_mode_allows_fallback_when_configured() -> None:
    """Strict mode can be configured to allow fallback."""
    validator = EventValidator(
        EventValidationConfig(
            enabled=True, strict_mode=True, allow_fallback_handler=True
        )
    )
    order = OrderWithFallback(id="1")
    event = OrderCreated(order_id="1", amount=100.0, currency="EUR")

    # Should not raise (fallback allowed in strict mode)
    validator.validate_handler_exists(order, event)


def test_strict_validation_falls_back_to_missing_handler_error() -> None:
    """Strict mode raises MissingEventHandlerError when no handler at all."""
    validator = EventValidator(EventValidationConfig(enabled=True, strict_mode=True))
    order = OrderWithoutHandlers(id="1")
    event = OrderCreated(order_id="1", amount=100.0, currency="EUR")

    with pytest.raises(MissingEventHandlerError) as exc_info:
        validator.validate_handler_exists(order, event)

    assert "OrderWithoutHandlers" in str(exc_info.value)


# ── Exception Tests ─────────────────────────────────────────────────────────


def test_missing_handler_error_message() -> None:
    """MissingEventHandlerError has clear error message."""
    error = MissingEventHandlerError(aggregate_type="Order", event_type="OrderCreated")

    error_msg = str(error)
    assert "Order" in error_msg
    assert "OrderCreated" in error_msg
    assert "apply_OrderCreated" in error_msg


def test_missing_handler_error_attributes() -> None:
    """MissingEventHandlerError stores attributes for programmatic access."""
    error = MissingEventHandlerError(aggregate_type="Order", event_type="OrderCreated")

    assert error.aggregate_type == "Order"
    assert error.event_type == "OrderCreated"


def test_strict_violation_error_message() -> None:
    """StrictValidationViolationError has clear error message."""
    error = StrictValidationViolationError(
        aggregate_type="Order",
        event_type="OrderCreated",
        reason="Strict mode requires exact apply_<EventType> method",
    )

    error_msg = str(error)
    assert "Order" in error_msg
    assert "OrderCreated" in error_msg
    assert "Strict mode requires" in error_msg


def test_strict_violation_error_attributes() -> None:
    """StrictValidationViolationError stores attributes for programmatic access."""
    error = StrictValidationViolationError(
        aggregate_type="Order",
        event_type="OrderCreated",
        reason="Test reason",
    )

    assert error.aggregate_type == "Order"
    assert error.event_type == "OrderCreated"
    assert error.reason == "Test reason"


def test_event_handler_error_is_cqrsddd_error() -> None:
    """All handler errors inherit from CQRSDDDError."""
    from cqrs_ddd_core.primitives.exceptions import CQRSDDDError

    assert issubclass(MissingEventHandlerError, CQRSDDDError)
    assert issubclass(StrictValidationViolationError, CQRSDDDError)
    assert issubclass(EventHandlerError, CQRSDDDError)
    assert issubclass(InvalidEventHandlerError, CQRSDDDError)


# ── Decorator Tests ────────────────────────────────────────────────────────


def test_event_handler_decorator_metadata() -> None:
    """@aggregate_event_handler decorator adds metadata to methods."""

    class Order(AggregateRoot[str], EventSourcedAggregateMixin[str]):
        @aggregate_event_handler()
        def apply_order_created(self, event: OrderCreated) -> None:
            self.status = "created"

    # Check metadata
    method = Order.apply_order_created
    assert is_aggregate_event_handler(method)
    assert get_handler_event_type(method) is None  # Not explicitly set


def test_event_handler_decorator_with_event_type() -> None:
    """@aggregate_event_handler with explicit event type."""

    class Order(AggregateRoot[str], EventSourcedAggregateMixin[str]):
        @aggregate_event_handler(event_type=OrderCreated)
        def handle_creation(self, event: OrderCreated) -> None:
            self.status = "created"

    # Check metadata
    method = Order.handle_creation
    assert is_aggregate_event_handler(method)
    assert get_handler_event_type(method) == "OrderCreated"


def test_event_handler_decorator_validate_on_load() -> None:
    """@aggregate_event_handler with validate_on_load parameter."""

    class Order(AggregateRoot[str], EventSourcedAggregateMixin[str]):
        @aggregate_event_handler(validate_on_load=False)
        def apply_order_created(self, event: OrderCreated) -> None:
            self.status = "created"

    # Check metadata
    method = Order.apply_order_created
    assert is_aggregate_event_handler(method)
    assert method._validate_on_load is False  # type: ignore[attr-defined]


def test_event_handler_validator_decorator() -> None:
    """@aggregate_event_handler_validator sets configuration on class."""
    # Already tested via OrderWithLenientValidator and OrderWithStrictValidator
    config = get_event_handler_config(OrderWithLenientValidator)
    assert config is not None
    assert config.enabled is True
    assert config.strict_mode is False


def test_get_event_handler_config_none() -> None:
    """get_event_handler_config returns None when not set."""
    config = get_event_handler_config(OrderWithHandlers)
    assert config is None


def test_is_event_handler_without_decorator() -> None:
    """is_aggregate_event_handler returns False for non-decorated methods."""

    class Order(AggregateRoot[str]):
        def some_method(self) -> None:
            pass

    method = Order.some_method
    assert not is_aggregate_event_handler(method)


# ── DefaultEventApplicator Integration Tests ────────────────────────────


def test_applicator_with_validation_enabled() -> None:
    """Applicator uses validation when enabled."""
    validator = EventValidator(EventValidationConfig(enabled=True, strict_mode=False))
    applicator = DefaultEventApplicator(validator=validator)

    order = OrderWithHandlers(id="1")
    event = OrderCreated(order_id="1", amount=100.0, currency="EUR")

    result = applicator.apply(order, event)
    assert result is order
    assert order.status == "created"
    assert order.amount == 100.0


def test_applicator_with_validation_disabled() -> None:
    """Applicator skips validation when disabled."""
    validator = EventValidator(EventValidationConfig(enabled=False))
    applicator = DefaultEventApplicator(validator=validator)

    order = OrderWithHandlers(id="1")
    event = OrderCreated(order_id="1", amount=100.0, currency="EUR")

    result = applicator.apply(order, event)
    assert result is order
    assert order.status == "created"


def test_applicator_fallback_handler() -> None:
    """Applicator uses fallback handler when exact not found."""
    applicator = DefaultEventApplicator()

    order = OrderWithFallback(id="1")
    event = OrderCreated(order_id="1", amount=100.0, currency="EUR")

    result = applicator.apply(order, event)
    assert result is order
    assert order.status == "created"


def test_applicator_with_strict_validator() -> None:
    """Applicator respects strict validator configuration."""
    validator = EventValidator(EventValidationConfig(enabled=True, strict_mode=True))
    applicator = DefaultEventApplicator(validator=validator)

    order = OrderWithStrictValidator(id="1")
    event = OrderCreated(order_id="1", amount=100.0, currency="EUR")

    result = applicator.apply(order, event)
    assert result is order
    assert order.status == "created"


def test_applicator_raise_on_missing_handler_true() -> None:
    """Applicator raises error when no handler and raise_on_missing_handler=True."""
    validator = EventValidator(EventValidationConfig(enabled=True, strict_mode=False))
    applicator = DefaultEventApplicator(
        validator=validator, raise_on_missing_handler=True
    )

    order = OrderWithoutHandlers(id="1")
    event = OrderCreated(order_id="1", amount=100.0, currency="EUR")

    with pytest.raises(MissingEventHandlerError):
        applicator.apply(order, event)


def test_applicator_raise_on_missing_handler_false() -> None:
    """Applicator silently ignores when no handler and raise_on_missing_handler=False."""
    validator = EventValidator(EventValidationConfig(enabled=True, strict_mode=False))
    applicator = DefaultEventApplicator(
        validator=validator, raise_on_missing_handler=False
    )

    order = OrderWithoutHandlers(id="1")
    event = OrderCreated(order_id="1", amount=100.0, currency="EUR")

    # Should not raise
    result = applicator.apply(order, event)
    assert result is order


# ── Backward Compatibility Tests ─────────────────────────────────────────────


def test_existing_aggregates_still_work() -> None:
    """Aggregates without mixin work with applicator."""
    applicator = DefaultEventApplicator()

    # Create an aggregate without mixin but with handlers (snake_case = ruff-compliant)
    class OldOrder(AggregateRoot[str]):
        status: str = "pending"

        def apply_order_created(self, event: OrderCreated) -> None:
            self.status = "created"

    order = OldOrder(id="1")
    event = OrderCreated(order_id="1", amount=100.0, currency="EUR")

    result = applicator.apply(order, event)
    assert result is order
    assert order.status == "created"


def test_aggregates_without_mixin_still_work() -> None:
    """Aggregates without EventSourcedAggregateMixin work."""
    applicator = DefaultEventApplicator(raise_on_missing_handler=False)

    order = OrderWithoutHandlers(id="1")
    event = OrderCreated(order_id="1", amount=100.0, currency="EUR")

    # Should not raise with raise_on_missing_handler=False
    result = applicator.apply(order, event)
    assert result is order


def test_default_validator_is_lenient() -> None:
    """Default applicator uses lenient validation."""
    applicator = DefaultEventApplicator()

    order = OrderWithFallback(id="1")
    event = OrderCreated(order_id="1", amount=100.0, currency="EUR")

    # Should work with fallback handler (lenient mode)
    result = applicator.apply(order, event)
    assert result is order
    assert order.status == "created"


# ── Validator Configuration Tests ───────────────────────────────────────────


def test_validator_get_config() -> None:
    """get_config returns the validator's configuration."""
    config = EventValidationConfig(enabled=True, strict_mode=False)
    validator = EventValidator(config)

    assert validator.get_config() is config
    assert validator.get_config().enabled is True
    assert validator.get_config().strict_mode is False


def test_validator_is_enabled() -> None:
    """is_enabled returns True when validation is enabled."""
    validator = EventValidator(EventValidationConfig(enabled=True))
    assert validator.is_enabled() is True

    validator_disabled = EventValidator(EventValidationConfig(enabled=False))
    assert validator_disabled.is_enabled() is False


def test_validator_is_strict_mode() -> None:
    """is_strict_mode returns True when strict mode is enabled."""
    validator = EventValidator(EventValidationConfig(strict_mode=True))
    assert validator.is_strict_mode() is True

    validator_lenient = EventValidator(EventValidationConfig(strict_mode=False))
    assert validator_lenient.is_strict_mode() is False


# ── EventSourcedAggregateMixin Internal Tests ────────────────────────


def test_apply_event_internal() -> None:
    """Internal _apply_event_internal method works correctly."""
    order = OrderWithHandlers(id="1")
    event = OrderCreated(order_id="1", amount=100.0, currency="EUR")

    order._apply_event_internal(event)
    assert order.status == "created"
    assert order.amount == 100.0


def test_apply_event_internal_missing_handler() -> None:
    """Internal _apply_event_internal raises on missing handler."""
    order = OrderWithoutHandlers(id="1")
    event = OrderCreated(order_id="1", amount=100.0, currency="EUR")

    with pytest.raises(MissingEventHandlerError):
        order._apply_event_internal(event)
