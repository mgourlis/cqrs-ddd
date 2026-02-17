"""bootstrap_sagas — one-call wiring for saga infrastructure."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .manager import SagaManager
from .registry import SagaRegistry

if TYPE_CHECKING:
    from cqrs_ddd_core.cqrs.message_registry import MessageRegistry
    from cqrs_ddd_core.domain.events import DomainEvent
    from cqrs_ddd_core.ports.bus import ICommandBus
    from cqrs_ddd_core.ports.event_dispatcher import IEventDispatcher

    from ..ports.saga_repository import ISagaRepository
    from .orchestration import Saga
    from .worker import SagaRecoveryWorker

logger = logging.getLogger("cqrs_ddd.sagas")


class SagaBootstrapResult:
    """Container returned by :func:`bootstrap_sagas` with all wired components.

    Attributes:
        registry: The :class:`SagaRegistry` with all sagas registered.
        manager: The saga manager.
        worker: Optional :class:`SagaRecoveryWorker` (if ``recovery_interval``
            was provided).
    """

    def __init__(
        self,
        registry: SagaRegistry,
        manager: SagaManager,
        worker: SagaRecoveryWorker | None = None,
    ) -> None:
        self.registry = registry
        self.manager = manager
        self.worker = worker


def bootstrap_sagas(
    *,
    sagas: list[type[Saga[Any]]],
    repository: ISagaRepository,
    command_bus: ICommandBus,
    message_registry: MessageRegistry,
    event_dispatcher: IEventDispatcher[DomainEvent] | None = None,
    registry: SagaRegistry | None = None,
    recovery_interval: int | None = None,
) -> SagaBootstrapResult:
    """Wire up the complete saga infrastructure in one call.

    This is the **recommended entry point** for saga setup.  It creates
    and connects all components automatically:

    1. Registers all saga classes in the :class:`SagaRegistry` (reads
       ``listened_events()`` from each class).
    2. Creates the saga manager.
    3. Binds the manager to the :class:`EventDispatcher` so events are
       routed automatically.
    4. Optionally creates a :class:`SagaRecoveryWorker` for background
       timeout and stall recovery.

    Parameters
    ----------
    sagas:
        List of saga classes to register.  Each must implement
        ``listened_events()`` for auto-registration.
    repository:
        Saga state persistence implementation.
    command_bus:
        ``ICommandBus`` for dispatching saga commands (typically the
        :class:`Mediator`).
    message_registry:
        :class:`MessageRegistry` for command serialisation/deserialisation.
    event_dispatcher:
        Optional :class:`EventDispatcher` to bind to.  If provided,
        the manager auto-registers for all saga event types.
    registry:
        Optional pre-existing :class:`SagaRegistry`.  If ``None``, a
        new one is created.
    recovery_interval:
        If set, creates a :class:`SagaRecoveryWorker` with this
        interval (in seconds).  The caller must ``await worker.start()``
        to begin background polling.

    Returns
    -------
    SagaBootstrapResult
        Container with ``registry``, ``manager``, and optional ``worker``.

    Example
    -------
    ::

        result = bootstrap_sagas(
            sagas=[OrderFulfillmentSaga, PaymentSaga],
            repository=saga_repo,
            command_bus=mediator,
            message_registry=msg_registry,
            event_dispatcher=event_dispatcher,
            recovery_interval=60,
        )
        # Everything is wired — events auto-route to sagas.
        # Start recovery worker:
        await result.worker.start()
    """
    # 1. Registry
    saga_registry = registry or SagaRegistry()
    for saga_class in sagas:
        saga_registry.register_saga(saga_class)

    # 2. Manager
    manager = SagaManager(
        repository=repository,
        registry=saga_registry,
        command_bus=command_bus,
        message_registry=message_registry,
    )

    # 3. Bind to event dispatcher
    if event_dispatcher is not None:
        manager.bind_to(event_dispatcher)

    # 4. Recovery worker (reactive: trigger on stall + poll fallback)
    worker: SagaRecoveryWorker | None = None
    if recovery_interval is not None:
        from .worker import SagaRecoveryWorker

        worker = SagaRecoveryWorker(
            saga_manager=manager,
            poll_interval=float(recovery_interval),
        )
        manager.set_recovery_trigger(worker.trigger)

    logger.info(
        "Saga bootstrap complete: %d sagas registered, recovery=%s",
        len(sagas),
        f"{recovery_interval}s" if recovery_interval else "disabled",
    )

    return SagaBootstrapResult(
        registry=saga_registry,
        manager=manager,
        worker=worker,
    )


__all__ = ["SagaBootstrapResult", "bootstrap_sagas"]
