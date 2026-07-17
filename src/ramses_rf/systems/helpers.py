"""RAMSES RF - Helper functions for systems."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol

from ramses_rf.address import Address
from ramses_rf.commands.core import Command as Intent
from ramses_rf.enums import Action
from ramses_tx import Packet, Priority

if TYPE_CHECKING:
    pass


class _SystemEntity(Protocol):
    @property
    def ctl(self) -> Any: ...
    @property
    def _gwy(self) -> Any: ...


_LOGGER = logging.getLogger(__name__)


async def send_system_intent(
    system: _SystemEntity,
    action: Action,
    data: dict[str, Any],
    wait_for_reply: bool | None = None,
) -> Packet:
    """Helper to dispatch intent from HGI (or CTL) to the CTL."""
    src_id = system._gwy.hgi.id if system._gwy.hgi else system.ctl.id
    intent = Intent(
        src=Address(src_id),
        dst=Address(system.ctl.id),
        action=action,
        data=data,
    )
    from typing import cast

    if wait_for_reply is not None:
        return cast(
            Packet,
            await system._gwy.dispatcher.send(
                intent, priority=Priority.HIGH, wait_for_reply=wait_for_reply
            ),
        )
    return cast(
        Packet, await system._gwy.dispatcher.send(intent, priority=Priority.HIGH)
    )
