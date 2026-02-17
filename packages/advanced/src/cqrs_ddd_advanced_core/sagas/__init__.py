"""Saga / Process Manager — explicit state machine implementation."""

from .bootstrap import SagaBootstrapResult, bootstrap_sagas
from .builder import SagaBuilder
from .manager import SagaManager
from .orchestration import Saga, TCCStep
from .registry import SagaRegistry
from .state import (
    CompensationRecord,
    ReservationType,
    SagaState,
    SagaStatus,
    StepRecord,
    TCCPhase,
    TCCStepRecord,
)
from .worker import SagaRecoveryWorker

__all__ = [
    # Builder
    "SagaBuilder",
    # State
    "SagaState",
    "SagaStatus",
    "StepRecord",
    "CompensationRecord",
    # TCC
    "TCCStep",
    "TCCStepRecord",
    "TCCPhase",
    "ReservationType",
    # Base class
    "Saga",
    # Registry
    "SagaRegistry",
    # Managers
    "SagaManager",
    # Worker
    "SagaRecoveryWorker",
    # Bootstrap
    "bootstrap_sagas",
    "SagaBootstrapResult",
]
