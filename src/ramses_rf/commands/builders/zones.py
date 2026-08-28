"""RAMSES RF - Zone command intent to L3 payload translation."""

from ramses_rf.commands.builders.helpers import (
    check_index,
    normalise_mode,
    normalise_until,
    resolve_addrs,
)
from ramses_rf.commands.core import Command
from ramses_rf.payloads.heating import (
    ZoneConfigPayload,
    ZoneModePayload,
    ZoneNamePayload,
    ZoneSetpointPayload,
)
from ramses_tx.const import DEFAULT_NUM_REPEATS, RQ, W_, Code, Priority
from ramses_tx.dtos import CommandDTO


def _build_zone_rq(
    intent: Command, code: Code, payload_suffix: str = ""
) -> CommandDTO:
    """Construct a standard single-zone RQ CommandDTO."""
    zone_index = intent.get("zone_index", intent.get("zone_index"))
    if zone_index is None:
        raise ValueError("Missing 'zone_index'/'zone_index' in intent data")

    payload = f"{check_index(zone_index)}{payload_suffix}"
    addr1, addr2, addr3 = resolve_addrs(intent.src, intent.dst)

    return CommandDTO(
        verb=RQ,
        addr1=addr1,
        addr2=addr2,
        addr3=addr3,
        code=code,
        payload=payload,
        priority=Priority.DEFAULT,
        num_repeats=DEFAULT_NUM_REPEATS,
    )


def build_set_temperature(intent: Command) -> CommandDTO:
    """Translate an Action.SET_ZONE_SETPOINT intent into a CommandDTO.

    Constructs a 3-byte Opcode 2309 setpoint write command.

    :param intent: The intent containing 'zone_index' and 'setpoint'.
    :type intent: Command
    :returns: A CommandDTO representing the intent.
    :rtype: CommandDTO
    :raises ValueError: If 'zone_index' or 'setpoint' is missing.
    """
    zone_index = intent.get("zone_index", intent.get("zone_index"))
    setpoint = intent.get("setpoint")

    if zone_index is None or setpoint is None:
        raise ValueError(
            "Missing 'zone_index'/'zone_index' or 'setpoint' in intent data"
        )

    payload = ZoneSetpointPayload.create(
        zone_index=zone_index, setpoint_temp=setpoint
    ).hex()

    addr1, addr2, addr3 = resolve_addrs(intent.src, intent.dst)

    return CommandDTO(
        verb=W_,
        addr1=addr1,
        addr2=addr2,
        addr3=addr3,
        code=Code._2309,
        payload=payload,
        priority=Priority.DEFAULT,
        num_repeats=DEFAULT_NUM_REPEATS,
    )


def build_set_mode(intent: Command) -> CommandDTO:
    """Translate an Action.SET_ZONE_MODE intent into a CommandDTO.

    Constructs a 7-byte or 13-byte Opcode 2349 mode override command.

    :param intent: The intent containing 'zone_index', 'mode', 'setpoint',
        'until', and 'duration'.
    :type intent: Command
    :returns: A CommandDTO representing the intent.
    :rtype: CommandDTO
    :raises ValueError: If 'zone_index' is missing or parameters are invalid.
    """
    zone_index = intent.get("zone_index", intent.get("zone_index"))
    if zone_index is None:
        raise ValueError("Missing 'zone_index'/'zone_index' in intent data")

    mode = intent.get("mode")
    setpoint = intent.get("setpoint")
    until = intent.get("until")
    duration = intent.get("duration")

    mode = normalise_mode(mode, setpoint, until, duration)

    if setpoint is not None and not isinstance(setpoint, (float, int)):
        raise ValueError(
            f"Invalid args: setpoint={setpoint}, but must be a float"
        )

    until, duration = normalise_until(mode, setpoint, until, duration)

    payload = ZoneModePayload.create(
        zone_index=zone_index,
        setpoint_temp=setpoint,
        mode_code=mode,
        duration_minutes=duration,
        until_dtm=until,
    ).hex()

    addr1, addr2, addr3 = resolve_addrs(intent.src, intent.dst)

    return CommandDTO(
        verb=W_,
        addr1=addr1,
        addr2=addr2,
        addr3=addr3,
        code=Code._2349,
        payload=payload,
        priority=Priority.DEFAULT,
        num_repeats=DEFAULT_NUM_REPEATS,
    )


def build_set_name(intent: Command) -> CommandDTO:
    """Translate an Action.SET_ZONE_NAME intent into a CommandDTO.

    Constructs a 22-byte Opcode 0004 zone name write command.

    :param intent: The intent containing 'zone_index' and 'name'.
    :type intent: Command
    :returns: A CommandDTO representing the intent.
    :rtype: CommandDTO
    :raises ValueError: If 'zone_index' or 'name' is missing.
    """
    zone_index = intent.get("zone_index", intent.get("zone_index"))
    name = intent.get("name")

    if zone_index is None or name is None:
        raise ValueError(
            "Missing 'zone_index'/'zone_index' or 'name' in intent data"
        )

    payload = ZoneNamePayload.create(zone_index=zone_index, name=name).hex()
    addr1, addr2, addr3 = resolve_addrs(intent.src, intent.dst)

    return CommandDTO(
        verb=W_,
        addr1=addr1,
        addr2=addr2,
        addr3=addr3,
        code=Code._0004,
        payload=payload,
        priority=Priority.DEFAULT,
        num_repeats=DEFAULT_NUM_REPEATS,
    )


def build_set_config(intent: Command) -> CommandDTO:
    """Translate an Action.SET_ZONE_CONFIG intent into a CommandDTO.

    Constructs a 6-byte Opcode 000A zone configuration write command.

    :param intent: The intent containing 'zone_index', 'min_temp',
        'max_temp', 'local_override', 'openwindow_function', and
        'multiroom_mode'.
    :type intent: Command
    :returns: A CommandDTO representing the intent.
    :rtype: CommandDTO
    :raises ValueError: If required parameters are missing or out of range.
    """
    zone_index = intent.get("zone_index", intent.get("zone_index"))
    if zone_index is None:
        raise ValueError("Missing 'zone_index'/'zone_index' in intent data")

    min_temp = intent.get("min_temp", 5.0)
    max_temp = intent.get("max_temp", 35.0)
    local_override = intent.get("local_override", False)
    openwindow_function = intent.get("openwindow_function", False)
    multiroom_mode = intent.get("multiroom_mode", False)

    if not (5.0 <= min_temp <= 21.0):
        raise ValueError(f"Out of range, min_temp: {min_temp}")
    if not (21.0 <= max_temp <= 35.0):
        raise ValueError(f"Out of range, max_temp: {max_temp}")

    for flag_name, flag_val in (
        ("local_override", local_override),
        ("openwindow_function", openwindow_function),
        ("multiroom_mode", multiroom_mode),
    ):
        if not isinstance(flag_val, bool):
            raise ValueError(f"Invalid arg, {flag_name}: {flag_val}")

    zone_flags = 0
    if not local_override:
        zone_flags |= 0x01
    if not openwindow_function:
        zone_flags |= 0x02
    if not multiroom_mode:
        zone_flags |= 0x10

    payload = ZoneConfigPayload(
        zone_index=zone_index,
        zone_flags=zone_flags,
        min_temp=min_temp,
        max_temp=max_temp,
    ).hex()

    addr1, addr2, addr3 = resolve_addrs(intent.src, intent.dst)

    return CommandDTO(
        verb=W_,
        addr1=addr1,
        addr2=addr2,
        addr3=addr3,
        code=Code._000A,
        payload=payload,
        priority=Priority.DEFAULT,
        num_repeats=DEFAULT_NUM_REPEATS,
    )


def build_get_name(intent: Command) -> CommandDTO:
    """Translate a GET_ZONE_NAME intent into a CommandDTO.

    :param intent: The intent containing 'zone_index'.
    :type intent: Command
    :returns: A CommandDTO representing the intent.
    :rtype: CommandDTO
    :raises ValueError: If 'zone_index' is missing in intent data.
    """
    return _build_zone_rq(intent, Code._0004, payload_suffix="00")


def build_get_config(intent: Command) -> CommandDTO:
    """Translate a GET_ZONE_CONFIG intent into a CommandDTO.

    :param intent: The intent containing 'zone_index'.
    :type intent: Command
    :returns: A CommandDTO representing the intent.
    :rtype: CommandDTO
    :raises ValueError: If 'zone_index' is missing in intent data.
    """
    return _build_zone_rq(intent, Code._000A)


def build_get_window_state(intent: Command) -> CommandDTO:
    """Translate a GET_ZONE_WINDOW_STATE intent into a CommandDTO.

    :param intent: The intent containing 'zone_index'.
    :type intent: Command
    :returns: A CommandDTO representing the intent.
    :rtype: CommandDTO
    :raises ValueError: If 'zone_index' is missing in intent data.
    """
    return _build_zone_rq(intent, Code._12B0)


def build_get_setpoint(intent: Command) -> CommandDTO:
    """Translate a GET_ZONE_SETPOINT intent into a CommandDTO.

    :param intent: The intent containing 'zone_index'.
    :type intent: Command
    :returns: A CommandDTO representing the intent.
    :rtype: CommandDTO
    :raises ValueError: If 'zone_index' is missing in intent data.
    """
    return _build_zone_rq(intent, Code._2309)


def build_get_mode(intent: Command) -> CommandDTO:
    """Translate a GET_ZONE_MODE intent into a CommandDTO.

    :param intent: The intent containing 'zone_index'.
    :type intent: Command
    :returns: A CommandDTO representing the intent.
    :rtype: CommandDTO
    :raises ValueError: If 'zone_index' is missing in intent data.
    """
    return _build_zone_rq(intent, Code._2349)


def build_get_temp(intent: Command) -> CommandDTO:
    """Translate a GET_ZONE_TEMP intent into a CommandDTO.

    :param intent: The intent containing 'zone_index'.
    :type intent: Command
    :returns: A CommandDTO representing the intent.
    :rtype: CommandDTO
    :raises ValueError: If 'zone_index' is missing in intent data.
    """
    return _build_zone_rq(intent, Code._30C9)
