"""RAMSES RF - Helper functions for devices."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from ramses_rf.address import Address
from ramses_rf.commands.core import Command as Intent
from ramses_rf.enums import Action
from ramses_rf.exceptions import DeviceNotFaked
from ramses_tx import Packet, Priority
from ramses_tx.typing import DeviceIdT


class _FakeableDevice(Protocol):
    @property
    def is_faked(self) -> bool: ...
    @property
    def id(self) -> DeviceIdT: ...
    @property
    def _gwy(self) -> Any: ...


_LOGGER = logging.getLogger(__name__)


async def send_fake_intent(
    device: _FakeableDevice, action: Action, data: dict[str, Any]
) -> Packet | None:
    """Fake the device reading by sending an intent."""
    if not device.is_faked:
        raise DeviceNotFaked(f"{device}: Faking is not enabled")

    intent = Intent(
        src=Address(device.id),
        dst=Address(device.id),
        action=action,
        data=data,
    )
    from typing import cast

    return cast(
        Packet | None, await device._gwy.dispatcher.send(intent, priority=Priority.HIGH)
    )
