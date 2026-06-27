#!/usr/bin/env python3
"""Unittests for ramses_tx/command.py"""

import logging
from datetime import datetime as dt, timedelta as td
from typing import Final

import pytest

from ramses_tx.command import Command
from ramses_tx.const import SYS_MODE_MAP, ZON_MODE_MAP
from ramses_tx.exceptions import CommandInvalid

#

_LOGGER = logging.getLogger(__name__)

#######################################################################################

# until an hour from now as "2025-08-02 14:00:00"
_UNTIL = (dt.now().replace(minute=0, second=0, microsecond=0) + td(hours=2)).strftime(
    "%Y-%m-%d %H:%M:%S"
)

TEST_COMMANDS: Final = [
    " W --- 18:000730 12:123456 --:------ 1F41 006 00FF00FFFFFF",  # . set_dhw_mode
    " W --- 18:000730 12:123456 --:------ 1F41 006 000002FFFFFF",  # . set_dhw_mode_perm, active-false
    " W --- 18:000730 12:123456 --:------ 2E04 008 00FFFFFFFFFFFF00",  # set_system_mode
    " W --- 18:000730 12:123456 --:------ 2349 007 027FFF00FFFFFF",  # set_zone_mode
    " W --- 18:000730 12:123456 --:------ 2349 007 0101F402FFFFFF",  # set_zone_mode_perm, setpoint
]


async def test_set_dhw_mode_follow() -> None:
    """Test parameter checks from ZON_MODE_MAP key"""
    # Arrange
    expected = TEST_COMMANDS[0]

    # Act
    cmd = Command.set_dhw_mode(ctl_id="12:123456", mode=ZON_MODE_MAP["follow_schedule"])
    #  cls,
    #  ctl_id: DeviceIdT | str,
    #  mode: int | str | None = None,
    #  active: bool | None = None,
    #  until: dt | str | None = None,
    #  duration: int | None = None,  # never passed on by ramses_cc

    # Assert
    assert str(cmd) == expected


async def test_set_dhw_mode_follow_int() -> None:
    """Test parameter checks from int"""
    # Arrange
    expected = TEST_COMMANDS[0]

    # Act
    cmd = Command.set_dhw_mode(ctl_id="12:123456", mode=0)

    # Assert
    assert str(cmd) == expected


async def test_set_dhw_mode_perm_false() -> None:
    """Test parameter checks mode 2, active false"""  # from Peter Nash
    # Arrange
    expected = TEST_COMMANDS[1]

    # Act
    cmd = Command.set_dhw_mode(
        ctl_id="12:123456", mode=ZON_MODE_MAP.PERMANENT, active=False
    )

    # Assert
    assert str(cmd) == expected


async def test_set_dhw_mode_follow_extra() -> None:
    """Test parameter checks extra"""
    # Arrange
    mode = ZON_MODE_MAP["follow_schedule"]

    # Act & Assert
    with pytest.raises(CommandInvalid):
        _ = Command.set_dhw_mode(ctl_id="12:123456", mode=mode, duration=1)


async def test_set_dhw_mode_untilduration() -> None:
    """Test parameter checks extra"""
    # Arrange
    mode = "temporary_override"

    # Act & Assert
    with pytest.raises(CommandInvalid):
        _ = Command.set_dhw_mode(
            ctl_id="12:123456",
            mode=mode,
            active=True,
            duration=3600,  # never passed on by ramses_cc
            until=_UNTIL,  # Invalid args: At least one of until or duration must be None
        )


async def test_set_system_mode_auto_none() -> None:
    """Test parameter checks from int"""
    # Arrange
    expected = TEST_COMMANDS[2]

    # Act
    cmd = Command.set_system_mode(ctl_id="12:123456", system_mode=None)

    # Assert
    assert str(cmd) == expected


async def test_set_system_mode_auto() -> None:
    """Test parameter checks"""
    # Arrange
    expected = TEST_COMMANDS[2]

    # Act
    cmd = Command.set_system_mode(ctl_id="12:123456", system_mode=SYS_MODE_MAP["auto"])
    # cls,
    # ctl_id: DeviceIdT | str,
    # system_mode: int | str | None,
    # *,
    # until: dt | str | None = None,

    # Assert
    assert str(cmd) == expected


async def test_set_system_mode_auto_int() -> None:
    """Test parameter checks from int"""
    # Arrange
    expected = TEST_COMMANDS[2]

    # Act
    cmd = Command.set_system_mode(ctl_id="12:123456", system_mode=0)

    # Assert
    assert str(cmd) == expected


async def test_set_system_mode_heatoff() -> None:
    """Test parameter checks mode 1"""
    # Arrange
    system_mode = SYS_MODE_MAP.HEAT_OFF

    # Act & Assert
    with pytest.raises(CommandInvalid):
        _ = Command.set_system_mode(
            ctl_id="12:123456",
            system_mode=system_mode,  # until should be None
            until="456789566",
        )


async def test_set_zone_mode_noargs() -> None:
    """Test parameter checks extra"""
    # Arrange
    ctl_id = "12:123456"

    # Act & Assert
    with pytest.raises(CommandInvalid):
        _ = Command.set_zone_mode(
            ctl_id=ctl_id,
            zone_idx=4,
        )


async def test_set_zone_mode_follow() -> None:
    """Test parameter checks"""
    # Arrange
    expected = TEST_COMMANDS[3]

    # Act
    cmd = Command.set_zone_mode(
        ctl_id="12:123456", mode=ZON_MODE_MAP["follow_schedule"], zone_idx=2
    )
    #  cls,
    #  ctl_id: DeviceIdT | str,
    #  mode: int | str | None = None,
    #  zone_idx: _ZoneIdxT,
    #  *
    #  active: bool | None = None,
    #  until: dt | str | None = None,
    #  duration: int | None = None,

    # Assert
    assert str(cmd) == expected


async def test_set_zone_mode_follow_extra() -> None:
    """Test parameter checks extra"""
    # Arrange
    mode = ZON_MODE_MAP["follow_schedule"]

    # Act & Assert
    with pytest.raises(CommandInvalid):
        _ = Command.set_zone_mode(
            ctl_id="12:123456",
            zone_idx=1,
            mode=mode,
            duration=1,  # never passed on by ramses_cc
        )


async def test_set_zone_mode_perm_setp() -> None:
    """Test parameter checks mode 2, active false"""  # from Peter Nash
    # Arrange
    expected = TEST_COMMANDS[4]

    # Act
    cmd = Command.set_zone_mode(
        ctl_id="12:123456", zone_idx=1, mode=ZON_MODE_MAP.PERMANENT, setpoint=5
    )

    # Assert
    assert str(cmd) == expected


async def test_clone_with_source() -> None:
    """Test that clone_with_source creates an identical command with a new source."""
    # Arrange
    original_cmd = Command("RQ --- 18:000730 01:145038 --:------ 000A 002 0800")
    new_source = "18:123456"
    assert original_cmd.src.id == "18:000730"

    # Act
    cloned_cmd = original_cmd.clone_with_source(new_source)

    # Assert
    # Assert cloned command is properly mutated
    assert cloned_cmd is not original_cmd
    assert cloned_cmd.src.id == "18:123456"
    assert cloned_cmd.dst.id == "01:145038"
    assert cloned_cmd.verb == "RQ"
    assert cloned_cmd.code == "000A"
    assert cloned_cmd.payload == "0800"
    assert str(cloned_cmd) == "RQ --- 18:123456 01:145038 --:------ 000A 002 0800"

    # Enforce strict immutability: the original command MUST NOT have changed
    assert original_cmd.src.id == "18:000730"


async def test_rq_missing_target() -> None:
    """Test parameter checks for RQ missing target."""
    # Arrange & Act & Assert
    with pytest.raises(CommandInvalid):
        _ = Command._from_attrs(
            verb="RQ",
            code="0016",
            payload="00",
            addr0="--:------",
            addr1="--:------",
        )


# --- set_fan_mode (22F1) scheme-aware payload tests (issue #547) ---


def test_set_fan_mode_orcon_2byte_default() -> None:
    """Default scheme (orcon) produces a 3-byte payload with mode_max=07."""
    # Arrange
    expected_payload = "000107"
    expected_code = "22F1"

    # Act
    cmd = Command.set_fan_mode("37:111111", "low", src_id="18:000730")

    # Assert
    # ORCON: low=01, mode_max=07 -> payload "000107"
    assert cmd.payload == expected_payload
    assert str(cmd.code) == expected_code


def test_set_fan_mode_orcon_2byte_explicit() -> None:
    """Explicit orcon scheme with mode_max='' produces legacy 2-byte payload."""
    # Arrange
    expected_payload = "0001"

    # Act
    cmd = Command.set_fan_mode(
        "37:111111",
        "low",
        scheme="orcon",
        src_id="18:000730",
        legacy_format=True,
    )

    # Assert
    # 2-byte legacy form: idx + mode only
    assert cmd.payload == expected_payload


def test_set_fan_mode_itho_3byte() -> None:
    """Itho scheme produces 3-byte payload with mode_max=04."""
    # Arrange
    expected_payload = "000204"

    # Act
    cmd = Command.set_fan_mode("37:111111", "low", scheme="itho", src_id="18:000730")

    # Assert
    # ITHO: low=02, mode_max=04 -> "000204"
    assert cmd.payload == expected_payload


def test_set_fan_mode_vasco_3byte() -> None:
    """Vasco scheme produces 3-byte payload with mode_max=06."""
    # Arrange
    expected_payload = "000406"

    # Act
    cmd = Command.set_fan_mode("37:111111", "high", scheme="vasco", src_id="18:000730")

    # Assert
    # VASCO: high=04, mode_max=06 -> "000406"
    assert cmd.payload == expected_payload


def test_set_fan_mode_siber_3byte_from_issue() -> None:
    """Siber DF Evo 4 payloads from issue #547 (orcon scheme, mode_max=07)."""
    # Arrange
    expected_low = "000107"
    expected_int = "000207"

    # Act
    # low:  003 000207
    cmd_low = Command.set_fan_mode(
        "37:111111", "low", scheme="orcon", src_id="18:000730"
    )

    # The issue lists Siber modes as 02=low,03=medium,04=high,07=boost.
    # With orcon scheme these map to: 02=medium,03=high,04=auto,07=off.
    # For Siber, the user should use the itho scheme or raw int indices.
    # Verify int index works: 02 -> "000207"
    cmd_int = Command.set_fan_mode(
        "37:111111", 0x02, scheme="orcon", src_id="18:000730"
    )

    # Assert
    assert cmd_low.payload == expected_low
    assert cmd_int.payload == expected_int


def test_set_fan_mode_nuaire_3byte() -> None:
    """Nuaire scheme produces 3-byte payload with mode_max=0A."""
    # Arrange
    expected_payload = "00020A"

    # Act
    cmd = Command.set_fan_mode(
        "37:111111", "normal", scheme="nuaire", src_id="18:000730"
    )

    # Assert
    # NUAIRE: normal=02, mode_max=0A -> "00020A"
    assert cmd.payload == expected_payload


def test_set_fan_mode_int_index() -> None:
    """Integer fan_mode is treated as a hex mode index."""
    # Arrange
    expected_payload = "000307"

    # Act
    cmd = Command.set_fan_mode("37:111111", 3, scheme="orcon", src_id="18:000730")

    # Assert
    assert cmd.payload == expected_payload


def test_set_fan_mode_none_is_off() -> None:
    """None fan_mode maps to mode 00 (off/away)."""
    # Arrange
    expected_payload = "000007"

    # Act
    cmd = Command.set_fan_mode("37:111111", None, scheme="orcon", src_id="18:000730")

    # Assert
    assert cmd.payload == expected_payload


def test_set_fan_mode_invalid_scheme_raises() -> None:
    """An unknown scheme raises CommandInvalid."""
    # Arrange & Act & Assert
    with pytest.raises(CommandInvalid, match="scheme is not valid"):
        Command.set_fan_mode("37:111111", "low", scheme="bogus", src_id="18:000730")


def test_set_fan_mode_invalid_mode_raises() -> None:
    """A mode not in the scheme's map raises CommandInvalid."""
    # Arrange & Act & Assert
    with pytest.raises(CommandInvalid, match="fan_mode is not valid"):
        Command.set_fan_mode("37:111111", "turbo", scheme="itho", src_id="18:000730")
