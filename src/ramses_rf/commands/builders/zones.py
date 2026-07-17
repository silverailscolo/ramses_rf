"""RAMSES RF - Zone command intent to L3 payload translation."""

from ramses_rf.commands.builders.helpers import resolve_addrs
from ramses_rf.commands.core import Command
from ramses_tx.command.base import _check_idx, _normalise_mode, _normalise_until
from ramses_tx.const import DEFAULT_NUM_REPEATS, W_, Code, Priority
from ramses_tx.dtos import CommandDTO
from ramses_tx.helpers import hex_from_dtm, hex_from_temp


def build_set_temperature(intent: Command) -> CommandDTO:
    """Translate an Action.SET_TEMPERATURE intent into a CommandDTO."""
    # Data expected: {"zone_idx": int | str, "setpoint": float}
    zone_idx = intent.get("zone_idx")
    setpoint = intent.get("setpoint")

    if zone_idx is None or setpoint is None:
        raise ValueError("Missing 'zone_idx' or 'setpoint' in intent data")

    payload = f"{_check_idx(zone_idx)}{hex_from_temp(setpoint)}"
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
    """Translate an Action.SET_MODE intent into a CommandDTO."""
    # Data expected: {"zone_idx": int|str, "mode": int|str|None,
    # "setpoint": float|None, "until": dt|str|None, "duration": int|None}
    zone_idx = intent.get("zone_idx")
    if zone_idx is None:
        raise ValueError("Missing 'zone_idx' in intent data")

    mode = intent.get("mode")
    setpoint = intent.get("setpoint")
    until = intent.get("until")
    duration = intent.get("duration")

    mode = _normalise_mode(mode, setpoint, until, duration)

    if setpoint is not None and not isinstance(setpoint, (float, int)):
        raise ValueError(f"Invalid args: setpoint={setpoint}, but must be a float")

    until, duration = _normalise_until(mode, setpoint, until, duration)

    payload = "".join(
        (
            _check_idx(zone_idx),
            hex_from_temp(setpoint),
            mode,
            "FFFFFF" if duration is None else f"{duration:06X}",
            "" if until is None else hex_from_dtm(until),
        )
    )
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
