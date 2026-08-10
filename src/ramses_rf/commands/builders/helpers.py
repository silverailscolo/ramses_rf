"""RAMSES RF - Intent-to-DTO Translation Helpers."""

from datetime import datetime as dt
from typing import Any

from ramses_rf.address import Address
from ramses_rf.const import ZON_MODE_MAP
from ramses_tx import exceptions as exc
from ramses_tx.const import FA


def resolve_addrs(src: Address | str, dst: Address | str) -> tuple[str, str, str]:
    """Resolve logical source and destination to positional MAC addresses.

    :param src: Logical source of the command.
    :param dst: Logical target of the command.
    :return: A tuple of (addr1, addr2, addr3) for the L3 CommandDTO.
    """
    src_id = src if isinstance(src, str) else src.id
    dst_id = dst if isinstance(dst, str) else dst.id

    if src_id == dst_id:
        return src_id, "--:------", dst_id
    return src_id, dst_id, "--:------"


def check_idx(zone_idx: int | str) -> str:
    """Validate and normalise a zone index or DHW index byte.

    :param zone_idx: Zone index integer or hex string representation.
    :type zone_idx: int | str
    :returns: Uppercase 2-character hex string index.
    :rtype: str
    :raises CommandInvalid: If zone_idx is invalid.
    """
    if not isinstance(zone_idx, int | str):
        raise exc.CommandInvalid(f"Invalid value for zone_idx: {zone_idx}")
    if isinstance(zone_idx, str):
        zone_idx = FA if zone_idx == "HW" else zone_idx
    result: int = zone_idx if isinstance(zone_idx, int) else int(zone_idx, 16)
    if 0 > result > 15 and result != 0xFA:
        raise exc.CommandInvalid(f"Invalid value for zone_idx: {result}")
    return f"{result:02X}"


def normalise_mode(
    mode: int | str | None,
    target: bool | float | None,
    until: dt | str | None,
    duration: int | None,
) -> str:
    """Validate and normalise a heating mode for zone or DHW control.

    :param mode: Heating mode identifier or index.
    :type mode: int | str | None
    :param target: Target setpoint temperature or active boolean flag.
    :type target: bool | float | None
    :param until: Target expiration timestamp.
    :type until: dt | str | None
    :param duration: Override duration integer in minutes.
    :type duration: int | None
    :returns: Normalised 2-character hex mode string.
    :rtype: str
    :raises CommandInvalid: If mode options or parameters are invalid.
    """
    if mode is None and target is None:
        raise exc.CommandInvalid(
            "Invalid args: One of mode or setpoint/active can't be None"
        )
    if until and duration:
        raise exc.CommandInvalid(
            "Invalid args: At least one of until or duration must be None"
        )

    if mode is None:
        if until:
            mode = ZON_MODE_MAP.TEMPORARY
        elif duration:
            mode = ZON_MODE_MAP.COUNTDOWN
        else:
            mode = ZON_MODE_MAP.PERMANENT  # TODO: advanced_override?
    elif isinstance(mode, int):
        mode = f"{mode:02X}"
    if mode not in ZON_MODE_MAP:
        mode = ZON_MODE_MAP._hex(mode)  # type: ignore[arg-type]  # may raise KeyError

    assert isinstance(mode, str)  # mypy check

    if mode != ZON_MODE_MAP.FOLLOW and target is None:
        raise exc.CommandInvalid(
            f"Invalid args: For {ZON_MODE_MAP[mode]}, setpoint/active can't be None"
        )

    return mode


def normalise_until(
    mode: int | str | None,
    _: Any,
    until: dt | str | None,
    duration: int | None,
) -> tuple[Any, Any]:
    """Validate and normalise timing parameters for zone or DHW mode changes.

    :param mode: Normalised heating mode string.
    :type mode: int | str | None
    :param _: Reserved parameter.
    :type _: Any
    :param until: Target expiration timestamp.
    :type until: dt | str | None
    :param duration: Override duration integer in minutes.
    :type duration: int | None
    :returns: Tuple of (until, duration) timing parameters.
    :rtype: tuple[Any, Any]
    :raises CommandInvalid: If timing parameters conflict with the specified mode.
    """
    if mode == ZON_MODE_MAP.TEMPORARY:
        if duration is not None:
            raise exc.CommandInvalid(
                f"Invalid args: For mode={mode}, duration must be None"
            )
        if until is None:
            mode = ZON_MODE_MAP.ADVANCED  # or: until = dt.now() + td(hour=1)

    elif mode in ZON_MODE_MAP.COUNTDOWN:
        if duration is None:
            raise exc.CommandInvalid(
                f"Invalid args: For mode={mode}, duration can't be None"
            )
        if until is not None:
            raise exc.CommandInvalid(
                f"Invalid args: For mode={mode}, until must be None"
            )

    elif until is not None or duration is not None:
        raise exc.CommandInvalid(
            f"Invalid args: For mode={mode}, until and duration must both be None"
        )

    return until, duration  # TODO return updated mode for ZON_MODE_MAP.TEMPORARY ?
