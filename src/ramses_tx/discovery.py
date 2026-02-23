#!/usr/bin/env python3
"""RAMSES RF - Hardware discovery and identification."""

from __future__ import annotations

import asyncio
import glob
import logging
import os
import sys
from functools import partial

from serial import SerialException, serial_for_url  # type: ignore[import-untyped]

from . import exceptions as exc
from .typing import SerPortNameT

_LOGGER = logging.getLogger(__name__)

__all__ = ["comports", "is_hgi80"]

# OS-Specific imports and overrides
if os.name == "nt":
    from serial.tools.list_ports_windows import (  # type: ignore[import-untyped]
        comports as comports,
    )

elif os.name != "posix":
    raise ImportError(
        f"Sorry: no implementation for your platform ('{os.name}') available"
    )

elif sys.platform.lower()[:5] != "linux":
    from serial.tools.list_ports_posix import (  # type: ignore[import-untyped]
        comports as comports,
    )

else:
    from serial.tools.list_ports_linux import SysFS  # type: ignore[import-untyped]

    def list_links(devices: set[str]) -> list[str]:
        """Search for symlinks to ports already listed in devices."""
        links: list[str] = []
        for device in glob.glob("/dev/*") + glob.glob("/dev/serial/by-id/*"):
            if os.path.islink(device) and os.path.realpath(device) in devices:
                links.append(device)
        return links

    def comports(  # type: ignore[no-any-unimported]
        include_links: bool = False, _hide_subsystems: list[str] | None = None
    ) -> list[SysFS]:
        """Return a list of Serial objects for all known serial ports."""
        if _hide_subsystems is None:
            _hide_subsystems = ["platform"]

        devices = set()
        with open("/proc/tty/drivers") as file:
            drivers = file.readlines()
            for driver in drivers:
                items = driver.strip().split()
                if items[4] == "serial":
                    devices.update(glob.glob(items[1] + "*"))

        if include_links:
            devices.update(list_links(devices))

        result: list[SysFS] = [  # type: ignore[no-any-unimported]
            d for d in map(SysFS, devices) if d.subsystem not in _hide_subsystems
        ]
        return result


async def is_hgi80(serial_port: SerPortNameT) -> bool | None:
    """Return True if the device attached to the port has the attributes of a Honeywell HGI80."""
    if serial_port[:7] == "mqtt://":
        return False  # ramses_esp

    if "://" in serial_port:  # e.g. "rfc2217://localhost:5001"
        try:
            serial_for_url(serial_port, do_not_open=True)
        except (SerialException, ValueError) as err:
            raise exc.TransportSerialError(
                f"Unable to find {serial_port}: {err}"
            ) from err
        return None

    loop = asyncio.get_running_loop()
    if not await loop.run_in_executor(None, os.path.exists, serial_port):
        raise exc.TransportSerialError(f"Unable to find {serial_port}")

    if "by-id" not in serial_port:
        pass
    elif "TUSB3410" in serial_port:
        return True
    elif "evofw3" in serial_port or "FT232R" in serial_port or "NANO" in serial_port:
        return False

    try:
        komports = await loop.run_in_executor(
            None, partial(comports, include_links=True)
        )
    except ImportError as err:
        raise exc.TransportSerialError(f"Unable to find {serial_port}: {err}") from err

    vid = {x.device: x.vid for x in komports}.get(serial_port)

    if not vid:
        pass
    elif vid == 0x10AC:  # Honeywell
        return True
    elif vid in (0x0403, 0x1B4F):  # FTDI, SparkFun
        return False

    product = {x.device: getattr(x, "product", None) for x in komports}.get(serial_port)

    if not product:
        pass
    elif "TUSB3410" in product:
        return True
    elif "evofw3" in product or "FT232R" in product or "NANO" in product:
        return False

    _LOGGER.warning(
        f"{serial_port}: the gateway type is not determinable, will assume evofw3"
        + (
            ", TIP: specify the serial port by-id (i.e. /dev/serial/by-id/usb-...)"
            if "by-id" not in serial_port
            else ""
        )
    )
    return None
