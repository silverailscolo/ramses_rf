#!/usr/bin/env python3
"""Test ramses_tx/command.py"""

import logging
from typing import Final  # , NoReturn, TypeAlias, TypedDict

#  from unittest.mock import patch
import serial as ser  # type: ignore[import-untyped]
from serial.tools.list_ports import comports  # type: ignore[import-untyped]

from ramses_tx.command import Command
from ramses_tx.const import SYS_MODE_MAP, ZON_MODE_MAP
from ramses_tx.exceptions import CommandInvalid

#

_LOGGER = logging.getLogger(__name__)

#######################################################################################

#######################################################################################

#######################################################################################


TEST_COMMANDS: Final = [
    " W --- 18:000730 12:123456 --:------ 1F41 006 00FF00FFFFFF",
    " W --- 18:000730 12:123456 --:------ 2E04 008 00FFFFFFFFFFFF00",
    " W --- 18:000730 12:123456 --:------ 2349 007 027FFF00FFFFFF",
]


async def test_set_dhw_mode_follow() -> None:
    """Test parameter checks"""
    cmd = Command.set_dhw_mode(ctl_id="12:123456", mode=ZON_MODE_MAP["follow_schedule"])
    #  cls,
    #  ctl_id: DeviceIdT | str,
    #  mode: int | str | None = None,
    #  active: bool | None = None,
    #  until: dt | str | None = None,
    #  duration: int | None = None,

    assert str(cmd) == TEST_COMMANDS[0]


async def test_set_dhw_mode_follow_int() -> None:
    """Test parameter checks"""
    cmd = Command.set_dhw_mode(ctl_id="12:123456", mode=0)
    #  cls,
    #  ctl_id: DeviceIdT | str,
    #  mode: int | str | None = None,
    #  active: bool | None = None,
    #  until: dt | str | None = None,
    #  duration: int | None = None,

    assert str(cmd) == TEST_COMMANDS[0]


async def test_set_dhw_mode_follow_extra() -> None:
    """Test parameter checks extra"""
    try:
        _ = Command.set_dhw_mode(
            ctl_id="12:123456", mode=ZON_MODE_MAP["follow_schedule"], duration=1
        )
    except CommandInvalid:
        pass
    else:
        assert False


async def test_set_system_mode_auto() -> None:
    """Test parameter checks"""
    cmd = Command.set_system_mode(ctl_id="12:123456", system_mode=SYS_MODE_MAP["auto"])
    #  cls,
    #  ctl_id: DeviceIdT | str,
    #  mode: int | str | None = None,
    #  active: bool | None = None,
    #  until: dt | str | None = None,
    #  duration: int | None = None,

    assert str(cmd) == TEST_COMMANDS[1]


async def test_set_system_mode_auto_int() -> None:
    """Test parameter checks"""
    cmd = Command.set_system_mode(ctl_id="12:123456", system_mode=0)
    #  cls,
    #  ctl_id: DeviceIdT | str,
    #  mode: int | str | None = None,
    #  active: bool | None = None,
    #  until: dt | str | None = None,
    #  duration: int | None = None,

    assert str(cmd) == TEST_COMMANDS[1]


async def test_set_zone_mode_follow() -> None:
    """Test parameter checks"""
    cmd = Command.set_zone_mode(
        ctl_id="12:123456", mode=ZON_MODE_MAP["follow_schedule"], zone_idx=2
    )
    #  cls,
    #  ctl_id: DeviceIdT | str,
    #  mode: int | str | None = None,
    #  zone_idx: _ZoneIdxT,
    #  active: bool | None = None,
    #  until: dt | str | None = None,
    #  duration: int | None = None,

    assert str(cmd) == TEST_COMMANDS[2]


async def test_set_zone_mode_follow_extra() -> None:
    """Test parameter checks"""

    try:
        _ = Command.set_zone_mode(
            ctl_id="12:123456",
            zone_idx=1,
            mode=ZON_MODE_MAP["follow_schedule"],
            duration=1,
        )
    except CommandInvalid:
        pass
    else:
        assert False
