"""RAMSES RF - The Asynchronous Topology Builder Engine."""

from __future__ import annotations

import logging
from collections.abc import Callable

from ramses_rf.messages.core import Message
from ramses_rf.models import TopologyChangedEvent
from ramses_rf.pipeline.topology_handlers import (
    BindTopologyHandler,
    DhwTopologyHandler,
    HvacTopologyHandler,
    OtbTopologyHandler,
    RadTopologyHandler,
    TopologyHandler,
    UfhTopologyHandler,
)

_LOGGER = logging.getLogger(__name__)


class TopologyBuilder:
    """Centralised CQRS engine for graph mutation and topology construction.

    INDUSTRY ARCHITECTURE NOTE: The CQRS Subsystem Handler Pattern
    --------------------------------------------------------------
    Because this project decodes reverse-engineered RF protocols across
    diverse heating, ventilation, and hot water devices, topology rules
    are decoupled into dedicated subsystem handlers (e.g., `BindTopologyHandler`,
    `UfhTopologyHandler`, `DhwTopologyHandler`, `HvacTopologyHandler`).

    When a L7 `Message` envelope arrives, the engine passes the message to each
    registered `TopologyHandler` in `self._handlers`. Handlers evaluate the packet
    and emit deterministic `TopologyChangedEvent` domain events onto the CQRS bus.

    GUIDANCE FOR MAINTAINERS:
    ------------------------
    To add support for a new device type, manufacturer quirk, or subsystem protocol:
    1. Create a new `TopologyHandler` subclass in `src/ramses_rf/pipeline/topology_handlers/`
       (or add logic to an existing subsystem handler file).
    2. Implement `consume(msg: Message)` to evaluate the frame and call `self._emit(event)`.
    3. Instantiate the new handler in `self._handlers` below.
    The core ingestion pipeline and `TopologyBuilder` never need structural modification.
    """

    def __init__(
        self,
        emit_event_cb: Callable[[TopologyChangedEvent], None],
        enable_eavesdrop: bool = False,
    ) -> None:
        """Initialize the TopologyBuilder.

        :param emit_event_cb: Callback to emit topology events back
            onto the central event bus or directly to the registry.
        :type emit_event_cb: Callable[[TopologyChangedEvent], None]
        :param enable_eavesdrop: Flag toggling heuristic class promotions.
            If False (default), only explicit configuration rules process.
        :type enable_eavesdrop: bool
        :returns: None
        :rtype: None
        """
        self._emit: Callable[[TopologyChangedEvent], None] = emit_event_cb
        self._enable_eavesdrop: bool = enable_eavesdrop

        # Subsystem topology handlers managing individual hardware domains.
        # Rules previously held in a flat self._rules list are now encapsulated
        # inside these single-responsibility handler classes.
        self._handlers: list[TopologyHandler] = [
            BindTopologyHandler(
                emit_event_cb, enable_eavesdrop=enable_eavesdrop
            ),
            RadTopologyHandler(
                emit_event_cb, enable_eavesdrop=enable_eavesdrop
            ),
            UfhTopologyHandler(
                emit_event_cb, enable_eavesdrop=enable_eavesdrop
            ),
            DhwTopologyHandler(
                emit_event_cb, enable_eavesdrop=enable_eavesdrop
            ),
            OtbTopologyHandler(
                emit_event_cb, enable_eavesdrop=enable_eavesdrop
            ),
            HvacTopologyHandler(
                emit_event_cb, enable_eavesdrop=enable_eavesdrop
            ),
        ]

    async def consume(self, msg: Message) -> None:
        """Ingest a message and evaluate it against registered subsystem handlers.

        :param msg: The immutable Message L7 envelope to evaluate.
        :type msg: Message
        :returns: None
        :rtype: None
        """
        for handler in self._handlers:
            try:
                handler.consume(msg)
            except Exception as err:
                if "changed app_cntrl" in str(err) or "Can't create" in str(
                    err
                ):
                    _LOGGER.debug(
                        "Topology handler %s bypassed: %s",
                        type(handler).__name__,
                        err,
                    )
                else:
                    _LOGGER.error(
                        "Error evaluating topology handler %s: %s",
                        type(handler).__name__,
                        err,
                    )
