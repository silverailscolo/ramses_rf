#!/usr/bin/env python3
"""RAMSES RF - a RAMSES-II protocol decoder & analyser."""

from ramses_rf import Device
from ramses_rf.binding_fsm import BindingManager
from ramses_rf.device import Fakeable


def ensure_fakeable(dev: Device, make_fake: bool = True) -> None:
    """If a Device is not Fakeable (i.e. Fakeable, not _faked), make it so.

    :param dev: The Device instance to check and potentially modify.
    :type dev: Device
    :param make_fake: Whether to invoke the _make_fake method if it wasn't already.
    :type make_fake: bool
    :returns: None
    :rtype: None
    """

    class _Fakeable(dev.__class__, Fakeable):  # type: ignore[misc, name-defined]
        """Dynamically constructed subclass to inject Fakeable behavior."""

        pass

    if isinstance(dev, Fakeable | _Fakeable):
        return

    dev.__class__ = _Fakeable
    assert isinstance(dev, Fakeable)

    # Initialize the BindingManager requiring both the device and a dispatcher
    dispatcher = dev._gwy.async_send_cmd
    setattr(dev, "_bind_context", BindingManager(dev, dispatcher))  # noqa: B010

    if make_fake:
        dev._make_fake()
