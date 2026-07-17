"""RAMSES RF - Helper functions for devices."""

from __future__ import annotations

import logging
from typing import Any, Protocol, cast

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
    device: _FakeableDevice,
    action: Action,
    data: dict[str, Any],
    *,
    priority: Priority | None = Priority.HIGH,
    wait_for_reply: bool | None = None,
) -> Packet | None:
    """Fake the device reading by sending an intent.

    This helper constructs an intent and dispatches it through the device's gateway,
    acting on behalf of a faked device.

    :param device: The fakeable device from which to send the intent.
    :param action: The action intent to send.
    :param data: The payload data dictionary for the intent.
    :param priority: The transmission priority. Defaults to Priority.HIGH.
    :param wait_for_reply: Whether to wait for a reply packet.
    :return: The resulting packet, or None if no packet was returned.
    :raises DeviceNotFaked: If the device is not currently enabled for faking.
    """
    if not device.is_faked:
        raise DeviceNotFaked(f"{device}: Faking is not enabled")

    intent = Intent(
        src=Address(device.id),
        dst=Address(device.id),
        action=action,
        data=data,
    )

    return cast(
        Packet | None,
        await device._gwy.dispatcher.send(
            intent, priority=priority, wait_for_reply=wait_for_reply
        ),
    )
