from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cqrs_ddd_advanced_core.conflict.resolution import (
    ConflictResolutionPolicy,
    DeepMergeStrategy,
    FieldLevelMergeStrategy,
    MergeStrategyRegistry,
)
from cqrs_ddd_advanced_core.cqrs.handlers import (
    ConflictResolutionMixin,
    RetryBehaviorMixin,
)
from cqrs_ddd_advanced_core.cqrs.mixins import ConflictConfig, FixedRetryPolicy
from cqrs_ddd_advanced_core.exceptions import MergeStrategyRegistryMissingError


class TestConflictResolutionMixinUnit:
    @pytest.fixture
    def mixin(self):
        return ConflictResolutionMixin()

    def test_get_merge_strategy_injected_instance(self, mixin):
        """Should return the injected strategy instance if present."""
        mock_strategy = MagicMock()
        mixin.merge_strategy = mock_strategy

        config = ConflictConfig(policy=ConflictResolutionPolicy.MERGE)
        assert mixin._get_merge_strategy(config) == mock_strategy

    def test_get_merge_strategy_explicit_name_success(self, mixin):
        """Should create strategy from registry if name is provided."""
        registry = MagicMock(spec=MergeStrategyRegistry)
        mock_strategy = MagicMock()
        registry.create.return_value = mock_strategy
        mixin.strategy_registry = registry

        config = ConflictConfig(
            policy=ConflictResolutionPolicy.CUSTOM,
            strategy_name="union",
            strategy_kwargs={"foo": "bar"},
        )

        assert mixin._get_merge_strategy(config) == mock_strategy
        registry.create.assert_called_with("union", foo="bar", identity_key="id")

    def test_get_merge_strategy_explicit_name_missing_registry(self, mixin):
        """Should raise error if strategy name is requested but no registry provided."""
        mixin.strategy_registry = None
        config = ConflictConfig(
            policy=ConflictResolutionPolicy.CUSTOM, strategy_name="union"
        )

        with pytest.raises(MergeStrategyRegistryMissingError):
            mixin._get_merge_strategy(config)

    def test_get_merge_strategy_infer_deep_merge(self, mixin):
        """Should infer DeepMergeStrategy when append_lists is True."""
        config = ConflictConfig(
            policy=ConflictResolutionPolicy.MERGE,
            append_lists=True,
            list_identity_key="id",
        )
        strategy = mixin._get_merge_strategy(config)
        assert isinstance(strategy, DeepMergeStrategy)
        assert strategy.append_lists is True
        assert strategy.list_identity_key == "id"

    def test_get_merge_strategy_infer_field_merge(self, mixin):
        """Should infer FieldLevelMergeStrategy for default MERGE policy."""
        config = ConflictConfig(
            policy=ConflictResolutionPolicy.MERGE, ignore_conflicts=True
        )
        strategy = mixin._get_merge_strategy(config)
        assert isinstance(strategy, FieldLevelMergeStrategy)
        assert strategy.ignore_conflicts is True

    def test_get_merge_strategy_infer_last_wins(self, mixin):
        """Should infer DeepMergeStrategy(append_lists=False) for LAST_WINS."""
        config = ConflictConfig(policy=ConflictResolutionPolicy.LAST_WINS)
        strategy = mixin._get_merge_strategy(config)
        assert isinstance(strategy, DeepMergeStrategy)
        assert strategy.append_lists is False


class TestRetryBehaviorMixinUnit:
    @pytest.fixture
    def mixin(self):
        return RetryBehaviorMixin()

    @pytest.mark.asyncio
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_handle_retry_attempt_success(self, mock_sleep, mixin):
        """Should increment attempt, sleep, and return new attempt count."""
        policy = FixedRetryPolicy(delay_ms=100, max_retries=3, jitter=False)
        exception = ValueError("oops")

        next_attempt = await mixin._handle_retry_attempt(0, policy, exception)

        assert next_attempt == 1
        mock_sleep.assert_called_once_with(0.1)

    @pytest.mark.asyncio
    async def test_handle_retry_attempt_exceeded(self, mixin):
        """Should raise the exception if max retries exceeded."""
        policy = FixedRetryPolicy(delay_ms=100, max_retries=3)
        exception = ValueError("fatal")

        with pytest.raises(ValueError, match="fatal"):
            await mixin._handle_retry_attempt(3, policy, exception)

    @pytest.mark.asyncio
    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("random.random", return_value=0.5)  # Make jitter deterministic
    async def test_handle_retry_attempt_with_jitter(
        self, mock_random, mock_sleep, mixin
    ):
        """Should apply jitter to delay."""
        # 100ms delay * (0.5 + 0.5) = 100ms
        policy = FixedRetryPolicy(delay_ms=100, max_retries=3, jitter=True)
        exception = ValueError("oops")

        await mixin._handle_retry_attempt(0, policy, exception)

        # logic: int(100 * (0.5 + 0.5)) = 100
        mock_sleep.assert_called_once_with(0.1)
