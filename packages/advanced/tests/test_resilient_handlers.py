from unittest.mock import MagicMock

import pytest
from pydantic import Field

from cqrs_ddd_advanced_core.conflict.resolution import (
    ConflictResolutionPolicy,
    MergeStrategyRegistry,
    UnionListMergeStrategy,
)
from cqrs_ddd_advanced_core.cqrs.handlers import (
    ConflictResolutionMixin,
    PipelinedCommandHandler,
    ResilientCommandHandler,
    RetryableCommandHandler,
    RetryBehaviorMixin,
)
from cqrs_ddd_advanced_core.cqrs.mixins import (
    ConflictConfig,
    ConflictResilient,
    ExponentialBackoffPolicy,
    FixedRetryPolicy,
    Retryable,
)
from cqrs_ddd_advanced_core.persistence.dispatcher import PersistenceDispatcher
from cqrs_ddd_core.cqrs.command import Command
from cqrs_ddd_core.cqrs.response import CommandResponse
from cqrs_ddd_core.primitives.exceptions import ConcurrencyError

# --- Mock Setup ---


class MockCommand(Command[str], Retryable):
    retry_policy: FixedRetryPolicy = FixedRetryPolicy(delay_ms=1, max_retries=3)


class MockResilientCommand(Command[str], ConflictResilient, Retryable):
    retry_policy: FixedRetryPolicy = FixedRetryPolicy(delay_ms=1, max_retries=3)
    conflict_config: ConflictConfig = ConflictConfig(
        policy=ConflictResolutionPolicy.MERGE, append_lists=True
    )
    payload: dict = Field(default_factory=dict)


# --- Handlers for Testing ---


class FailingRetryHandler(RetryableCommandHandler[str]):
    def __init__(self, dispatcher) -> None:
        super().__init__(dispatcher)
        self.attempts = 0

    async def process(self, command: Command[str]) -> CommandResponse[str]:
        self.attempts += 1
        if self.attempts < 3:
            raise Exception("Transient failure")
        return CommandResponse(result="Success", events=[])


class FullResilientHandler(ResilientCommandHandler[dict]):
    def __init__(self, dispatcher) -> None:
        super().__init__(dispatcher)
        self.attempts = 0
        self.current_state = {"tags": ["a"]}

    async def fetch_latest_state(self, command):
        return self.current_state

    def get_incoming_state(self, command):
        return command.payload

    def update_command(self, command, merged_state):
        return command.model_copy(update={"payload": merged_state})

    async def process(self, command: Command[dict]) -> CommandResponse[dict]:
        self.attempts += 1
        if self.attempts == 1:
            self.current_state["tags"].append("b")
            raise ConcurrencyError("Conflict")
        return CommandResponse(result=command.payload, events=[])


class CustomComposedHandler(
    RetryBehaviorMixin, ConflictResolutionMixin, PipelinedCommandHandler[dict]
):
    """Demonstrates manual composition via mixins."""

    def __init__(self, dispatcher) -> None:
        super().__init__(dispatcher)
        self.add_behavior(self._conflict_resolution_behavior)
        self.add_behavior(self._retry_behavior)
        self.attempts = 0
        self.current_state = {"tags": ["a"]}

    async def fetch_latest_state(self, command):
        return self.current_state

    def get_incoming_state(self, command):
        return command.payload

    def update_command(self, command, merged_state):
        return command.model_copy(update={"payload": merged_state})

    async def process(self, command: Command[dict]) -> CommandResponse[dict]:
        self.attempts += 1
        if self.attempts == 1:
            self.current_state["tags"].append("conflict")
            raise ConcurrencyError("Conflict")
        if self.attempts == 2:
            raise Exception("Transient")
        return CommandResponse(result=command.payload, events=[])


# --- Tests ---


@pytest.mark.asyncio
async def test_retry_on_general_failure() -> None:
    dispatcher = MagicMock(spec=PersistenceDispatcher)
    handler = FailingRetryHandler(dispatcher)
    cmd = MockCommand()
    response = await handler.handle(cmd)

    assert response.result == "Success"
    assert handler.attempts == 3


@pytest.mark.asyncio
async def test_resilient_handler_handles_both() -> None:
    dispatcher = MagicMock(spec=PersistenceDispatcher)
    handler = FullResilientHandler(dispatcher)
    cmd = MockResilientCommand(payload={"tags": ["c"]})
    response = await handler.handle(cmd)

    expected = {"tags": ["a", "b", "c"]}
    assert response.result == expected
    assert handler.attempts == 2


@pytest.mark.asyncio
async def test_manual_mixin_composition() -> None:
    dispatcher = MagicMock(spec=PersistenceDispatcher)
    handler = CustomComposedHandler(dispatcher)
    cmd = MockResilientCommand(payload={"tags": ["c"]})

    response = await handler.handle(cmd)

    # 1st attempt: ConcurrencyError -> Conflict loop retries (merges tags -> ['a', 'conflict', 'c'])
    # 2nd attempt: Exception -> Retry loop retries
    # 3rd attempt: Success
    expected = {"tags": ["a", "conflict", "c"]}
    assert response.result == expected
    assert handler.attempts == 3


@pytest.mark.asyncio
async def test_explicit_strategy_selection() -> None:
    """Verify that strategy_name explicitly selects a strategy from the registry."""
    dispatcher = MagicMock(spec=PersistenceDispatcher)

    class ExplicitCommand(Command[dict], ConflictResilient):
        conflict_config: ConflictConfig = ConflictConfig(
            policy=ConflictResolutionPolicy.MERGE, strategy_name="union"
        )
        payload: list = Field(default_factory=list)

    class UnionHandler(ResilientCommandHandler[dict]):
        def __init__(self, dispatcher, registry=None) -> None:
            super().__init__(dispatcher, strategy_registry=registry)
            self.attempts = 0
            self.current_state = [1, 2]

        async def fetch_latest_state(self, command):
            return self.current_state

        def get_incoming_state(self, command):
            return command.payload

        def update_command(self, command, merged_state):
            return command.model_copy(update={"payload": merged_state})

        async def process(self, command):
            self.attempts += 1
            if self.attempts == 1:
                self.current_state.append(3)
                raise ConcurrencyError("Conflict")
            return CommandResponse(result=command.payload, events=[])

    registry = MergeStrategyRegistry()
    registry.register("union", UnionListMergeStrategy)

    handler = UnionHandler(dispatcher, registry=registry)
    # Union of [1, 2, 3] and [2, 4] should be [1, 2, 3, 4] (order might vary)
    cmd = ExplicitCommand(payload=[2, 4])
    response = await handler.handle(cmd)

    assert set(response.result) == {1, 2, 3, 4}
    assert handler.attempts == 2


@pytest.mark.asyncio
async def test_manual_strategy_injection() -> None:
    """Verify that injecting a strategy instance on the handler overrides everything else."""
    dispatcher = MagicMock(spec=PersistenceDispatcher)

    class InjectedHandler(ResilientCommandHandler[dict]):
        def __init__(self, dispatcher, strategy) -> None:
            super().__init__(dispatcher)
            self.merge_strategy = strategy
            self.attempts = 0
            self.current_state = {"a": 1}

        async def fetch_latest_state(self, command):
            return self.current_state

        def get_incoming_state(self, command):
            return command.payload

        def update_command(self, command, merged_state):
            return command.model_copy(update={"payload": merged_state})

        async def process(self, command):
            self.attempts += 1
            if self.attempts == 1:
                self.current_state["a"] = 2
                raise ConcurrencyError("Conflict")
            return CommandResponse(result=command.payload, events=[])

    # Injected strategy that always returns a constant instead of merging
    mock_strategy = MagicMock()
    mock_strategy.merge.return_value = {"injected": "yes"}

    handler = InjectedHandler(dispatcher, mock_strategy)
    cmd = MockResilientCommand(payload={"ignore": "me"})
    response = await handler.handle(cmd)

    assert response.result == {"injected": "yes"}
    assert handler.attempts == 2
    mock_strategy.merge.assert_called_once()


@pytest.mark.asyncio
async def test_exponential_backoff_calculation() -> None:
    policy = ExponentialBackoffPolicy(initial_delay_ms=100, multiplier=2.0)
    assert policy.calculate_delay(0) == 100
    assert policy.calculate_delay(1) == 200
    assert policy.calculate_delay(2) == 400
