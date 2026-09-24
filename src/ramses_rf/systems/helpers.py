"""RAMSES RF - Helper functions for systems."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from ramses_rf.address import HGI_DEV_ADDR, Address
from ramses_rf.commands.core import Command as Intent
from ramses_rf.enums import Action
from ramses_rf.interfaces import DeviceInterface, GatewayInterface
from ramses_rf.messages import Message
from ramses_tx import Priority


class _SystemEntity(Protocol):
    @property
    def ctl(self) -> DeviceInterface | None: ...
    @property
    def _gateway(self) -> GatewayInterface: ...


_LOGGER = logging.getLogger(__name__)


async def send_system_intent(
    system: _SystemEntity,
    action: Action,
    data: dict[str, Any],
    wait_for_reply: bool | None = None,
) -> Message:
    """Dispatch system intent from the HGI to the CTL.

    When the gateway device is not yet known (e.g. early startup),
    falls back to the HGI placeholder address rather than the CTL:
    every intent targets the CTL, so a CTL source would produce a
    self-addressed frame that gateways cannot transmit (issue 1237).
    """
    if system.ctl is None:
        raise ValueError(f"{system} has no associated controller")

    src_id = system._gateway.hgi.id if system._gateway.hgi else HGI_DEV_ADDR.id
    intent = Intent(
        src=Address(src_id),
        dst=Address(system.ctl.id),
        action=action,
        data=data,
    )

    if wait_for_reply is not None:
        return await system._gateway.dispatcher.send(
            intent, priority=Priority.HIGH, wait_for_reply=wait_for_reply
        )
    return await system._gateway.dispatcher.send(
        intent, priority=Priority.HIGH
    )
