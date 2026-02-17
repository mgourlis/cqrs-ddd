from __future__ import annotations

import asyncio
import logging
import random
from abc import abstractmethod
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from cqrs_ddd_advanced_core.conflict.resolution import (
    ConflictResolutionPolicy,
    DeepMergeStrategy,
    FieldLevelMergeStrategy,
    MergeStrategyRegistry,
)
from cqrs_ddd_advanced_core.exceptions import MergeStrategyRegistryMissingError
from cqrs_ddd_core.cqrs.command import Command
from cqrs_ddd_core.cqrs.handler import CommandHandler
from cqrs_ddd_core.cqrs.response import CommandResponse
from cqrs_ddd_core.primitives.exceptions import ConcurrencyError

from .mixins import ConflictResilient, Retryable

if TYPE_CHECKING:
    from cqrs_ddd_advanced_core.persistence.dispatcher import PersistenceDispatcher
    from cqrs_ddd_advanced_core.ports.conflict import IMergeStrategy

logger = logging.getLogger(__name__)

TResult = TypeVar("TResult")

# Type alias for a pipeline behavior wrapper
BehaviorWrapper = Callable[
    [Callable[[Command[TResult]], Awaitable[CommandResponse[TResult]]]],
    Callable[[Command[TResult]], Awaitable[CommandResponse[TResult]]],
]


class PipelinedCommandHandler(CommandHandler[TResult], Generic[TResult]):
    """
    Base class for command handlers that execute through a customizable pipeline.

    Subclasses can extend behavior by overriding ``get_pipeline`` and using
    ``add_behavior``.
    """

    def __init__(self, dispatcher: PersistenceDispatcher) -> None:
        self.dispatcher = dispatcher
        self._behaviors: list[BehaviorWrapper[TResult]] = []

    @abstractmethod
    async def process(self, command: Command[TResult]) -> CommandResponse[TResult]:
        """Core business logic to be implemented by users."""
        ...

    def add_behavior(self, behavior: BehaviorWrapper[TResult]) -> None:
        """Add a behavior wrapper to the pipeline (applied LIFO)."""
        self._behaviors.append(behavior)

    def get_pipeline(
        self,
    ) -> Callable[[Command[TResult]], Awaitable[CommandResponse[TResult]]]:
        """
        Build the execution pipeline.
        Wraps the core ``process`` method with all registered behaviors.
        """
        pipeline: Callable[
            [Command[TResult]], Awaitable[CommandResponse[TResult]]
        ] = self.process
        # Apply behaviors in reverse order (last added is outermost)
        for behavior in reversed(self._behaviors):
            pipeline = behavior(pipeline)
        return pipeline

    async def handle(self, command: Command[TResult]) -> CommandResponse[TResult]:
        """Execute the command through the pipeline."""
        pipeline = self.get_pipeline()
        return await pipeline(command)


class RetryBehaviorMixin:
    """Mixin that provides retry behavior for PipelinedCommandHandlers."""

    def _retry_behavior(
        self, next_fn: Callable[[Command[TResult]], Awaitable[CommandResponse[TResult]]]
    ) -> Callable[[Command[TResult]], Awaitable[CommandResponse[TResult]]]:
        """Behavior for general exception retries (non-concurrency)."""

        async def _wrapped(command: Command[TResult]) -> CommandResponse[TResult]:
            retry_policy = (
                getattr(command, "retry_policy", None)
                if isinstance(command, Retryable)
                else None
            )
            if not retry_policy:
                return await next_fn(command)

            attempt = 0
            while True:
                try:
                    return await next_fn(command)
                except ConcurrencyError:
                    # Concurrency errors are handled by conflict behaviors inner to this
                    raise
                except Exception as e:  # noqa: BLE001
                    attempt = await self._handle_retry_attempt(attempt, retry_policy, e)
                    continue

        return _wrapped

    async def _handle_retry_attempt(
        self,
        attempt: int,
        retry_policy: Any,
        exception: Exception,
    ) -> int:
        """Handles a failed attempt and returns next attempt number."""
        if attempt < retry_policy.max_retries:
            attempt += 1
            delay = retry_policy.calculate_delay(attempt)
            if retry_policy.jitter:
                # Simple jitter: +/- 50% of delay
                delay = int(delay * (0.5 + random.random()))  # noqa: S311

            logger.info(
                "Command failed: %s. Retrying in %dms (attempt %d/%d).",
                exception,
                delay,
                attempt,
                retry_policy.max_retries,
            )
            await asyncio.sleep(delay / 1000.0)
            return attempt
        raise exception


class ConflictResolutionMixin:
    """
    Mixin that provides automated conflict resolution for PipelinedCommandHandlers.

    Subclasses must implement:
    - fetch_latest_state(command): return the current entity state.
    - get_incoming_state(command): return the incoming state from command.
    - update_command(command, merged_state): return a new updated command.
    """

    def _conflict_resolution_behavior(
        self, next_fn: Callable[[Command[TResult]], Awaitable[CommandResponse[TResult]]]
    ) -> Callable[[Command[TResult]], Awaitable[CommandResponse[TResult]]]:
        """Behavior for optimistic concurrency conflict resolution."""

        async def _wrapped(command: Command[TResult]) -> CommandResponse[TResult]:
            conflict_config = (
                getattr(command, "conflict_config", None)
                if isinstance(command, ConflictResilient)
                else None
            )

            if (
                not conflict_config
                or conflict_config.policy == ConflictResolutionPolicy.FIRST_WINS
            ):
                return await next_fn(command)

            max_conflict_retries = 3
            for attempt in range(max_conflict_retries):
                try:
                    return await next_fn(command)
                except ConcurrencyError:
                    logger.warning(
                        "Conflict detected for %s (attempt %d/%d). Resolving...",
                        type(command).__name__,
                        attempt + 1,
                        max_conflict_retries,
                    )

                    if attempt < max_conflict_retries - 1:
                        try:
                            # Re-run resolution hook
                            return await self.resolve_conflict(command, next_fn)
                        except ConcurrencyError:
                            # If resolution still hits a conflict, we loop to try again
                            continue
                    else:
                        raise ConcurrencyError(
                            "Max conflict resolution attempts reached"
                        ) from None

            raise ConcurrencyError("Max conflict resolution attempts reached")

        return _wrapped

    @abstractmethod
    async def fetch_latest_state(self, command: Command[TResult]) -> Any:
        """Fetch the current persisted state of the entity involved in the command."""
        ...

    @abstractmethod
    def get_incoming_state(self, command: Command[TResult]) -> Any:
        """Extract the 'incoming' state from the command."""
        ...

    @abstractmethod
    def update_command(
        self, command: Command[TResult], merged_state: Any
    ) -> Command[TResult]:
        """
        Create a new command instance with the merged state.
        Must return a new instance as Commands are immutable.
        """
        ...

    async def resolve_conflict(
        self,
        command: Command[TResult],
        next_fn: Callable[[Command[TResult]], Awaitable[CommandResponse[TResult]]],
    ) -> CommandResponse[TResult]:
        """
        Resolves a conflict by fetching latest state, merging, and updating the command.
        """
        conflict_config = (
            getattr(command, "conflict_config", None)
            if isinstance(command, ConflictResilient)
            else None
        )

        if not conflict_config:
            return await next_fn(command)

        # 1. Fetch Latest
        current_state = await self.fetch_latest_state(command)
        if current_state is None:
            return await next_fn(command)

        # 2. Extract Incoming
        incoming_state = self.get_incoming_state(command)

        # 3. Select Strategy
        strategy = self._get_merge_strategy(conflict_config)

        if not strategy:
            return await next_fn(command)

        # 4. Merge
        merged_state = strategy.merge(current_state, incoming_state)

        # 5. Create New Command
        new_command = self.update_command(command, merged_state)

        # 6. Retry with updated command
        return await next_fn(new_command)

    def _get_merge_strategy(self, conflict_config: Any) -> IMergeStrategy | None:
        """Determines the appropriate merge strategy based on configuration."""
        # 1. Try injected strategy on the handler
        strategy: IMergeStrategy | None = getattr(self, "merge_strategy", None)
        if strategy:
            return strategy

        # 2. Try explicit strategy name if registry is available
        if conflict_config.strategy_name:
            strategy = self._create_strategy_from_registry(conflict_config)
            if strategy:
                return strategy

        # 3. Fallback to inferred strategy based on policy
        return self._infer_strategy_from_policy(conflict_config)

    def _create_strategy_from_registry(
        self, conflict_config: Any
    ) -> IMergeStrategy | None:
        """Creates a strategy instance from the injected registry."""
        registry: MergeStrategyRegistry | None = getattr(
            self, "strategy_registry", None
        )
        if not registry:
            raise MergeStrategyRegistryMissingError(
                f"Conflict strategy '{conflict_config.strategy_name}' was requested, "
                "but no 'strategy_registry' was provided to the handler."
            )

        kwargs = dict(conflict_config.strategy_kwargs)
        self._populate_strategy_kwargs(conflict_config, kwargs)

        return registry.create(conflict_config.strategy_name, **kwargs)

    def _populate_strategy_kwargs(
        self, conflict_config: Any, kwargs: dict[str, Any]
    ) -> None:
        """Populates strategy kwargs based on the strategy name."""
        name = conflict_config.strategy_name
        if name == "deep":
            kwargs.setdefault("append_lists", conflict_config.append_lists)
            kwargs.setdefault("list_identity_key", conflict_config.list_identity_key)
        elif name == "field":
            kwargs.setdefault("ignore_conflicts", conflict_config.ignore_conflicts)
            kwargs.setdefault("include_fields", conflict_config.include_fields)
            kwargs.setdefault("exclude_fields", conflict_config.exclude_fields)
        elif name == "timestamp":
            kwargs.setdefault("timestamp_field", conflict_config.timestamp_field)
            kwargs.setdefault(
                "fallback_to_incoming", conflict_config.fallback_to_incoming
            )
        elif name == "union":
            kwargs.setdefault("identity_key", conflict_config.list_identity_key)

    def _infer_strategy_from_policy(
        self, conflict_config: Any
    ) -> IMergeStrategy | None:
        """Infers a default strategy based on the conflict policy."""
        if conflict_config.policy == ConflictResolutionPolicy.MERGE:
            # If append_lists is requested, we MUST use DeepMerge
            if conflict_config.append_lists or conflict_config.strategy_name == "deep":
                return DeepMergeStrategy(
                    append_lists=conflict_config.append_lists,
                    list_identity_key=conflict_config.list_identity_key,
                )
            return FieldLevelMergeStrategy(
                ignore_conflicts=conflict_config.ignore_conflicts,
                include_fields=conflict_config.include_fields,
                exclude_fields=conflict_config.exclude_fields,
            )

        if conflict_config.policy == ConflictResolutionPolicy.LAST_WINS:
            return DeepMergeStrategy(append_lists=False)

        return None


class RetryableCommandHandler(
    RetryBehaviorMixin, PipelinedCommandHandler[TResult], Generic[TResult]
):
    """
    A PipelinedCommandHandler that adds retry behavior.
    """

    def __init__(self, dispatcher: PersistenceDispatcher) -> None:
        super().__init__(dispatcher)
        self.add_behavior(self._retry_behavior)


class ConflictCommandHandler(
    ConflictResolutionMixin, PipelinedCommandHandler[TResult], Generic[TResult]
):
    """
    A PipelinedCommandHandler that adds conflict resolution behavior.
    """

    def __init__(
        self,
        dispatcher: PersistenceDispatcher,
        strategy_registry: MergeStrategyRegistry | None = None,
    ) -> None:
        super().__init__(dispatcher)
        self.strategy_registry = strategy_registry
        self.add_behavior(self._conflict_resolution_behavior)


class ResilientCommandHandler(
    RetryBehaviorMixin,
    ConflictResolutionMixin,
    PipelinedCommandHandler[TResult],
    Generic[TResult],
):
    """
    A PipelinedCommandHandler that adds both Retry and Conflict resolution behaviors.
    """

    def __init__(
        self,
        dispatcher: PersistenceDispatcher,
        strategy_registry: MergeStrategyRegistry | None = None,
    ) -> None:
        super().__init__(dispatcher)
        self.strategy_registry = strategy_registry
        self.add_behavior(self._conflict_resolution_behavior)
        self.add_behavior(self._retry_behavior)
