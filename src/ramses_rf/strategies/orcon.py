"""RAMSES RF - Orcon HVAC strategy."""

from __future__ import annotations

from ramses_rf.models import HvacState
from ramses_rf.models.hvac_schemas import _22F1_MODE_MAX, _22F1_MODE_ORCON
from ramses_rf.strategies.base import HvacStrategyBase
from ramses_rf.typing import SchemaT
from ramses_tx.const import Code, IndexT

# The generic 3-byte 31D9 parser decodes the speed byte with the
# Vasco-style fan_info map, but on Orcon units (e.g. MVS-15) that byte
# is a 22F1-style mode index.  Keys are the parser's output strings:
# the Vasco-style display names, and the raw hex emitted for mode
# indices the chosen map does not know (bound-REM/fall-back branches,
# and 0x06/0x07 on the Vasco map).
_31D9_ORCON_MODE_NAMES: dict[str, str] = {
    "off": "away",  # 0x00 on the generic maps
    "1 (trickle)": "low",  # 0x01
    "2 (low)": "medium",  # 0x02
    "3 (medium)": "high",  # 0x03
    "4 (boost)": "auto",  # 0x04
    "auto": "auto_alt",  # 0x05
    "01": "low",  # 0x01 as raw hex
    "02": "medium",
    "03": "high",
    "04": "auto",
    "05": "auto_alt",
    "06": "boost",
    "07": "off",
}

# 22F3 timed boost commands (7-byte Orcon format), built structurally
# rather than tabulated per variant (issue ramses-rf/ramses_cc#1332):
#
#   byte0 hdr     : 00
#   byte1 flags   : 0x12 on classic remotes, 0x02 on newer models (e.g.
#                   VMN-15LF01) — flags & 0x10 maps to
#                   fallback_speed_mode, flags & 0x40 means the duration
#                   is in hours rather than minutes
#   byte2 duration: minutes (×60 when the hours flag is set)
#   byte3 speed   : 01=low, 02=medium, 03=high
#   bytes4-6 tail : fallback mode/fan + pad — "04 04 04" on classic
#                   remotes, "04 00 00" observed on the 0x02 dialect
#
# The flag/tail differences are per-remote-model dialects, so they are
# parameters of the builder/matcher below, not separate command names.
_ORCON_BOOST_SPEEDS: dict[str, int] = {
    "low": 0x01,
    "medium": 0x02,
    "high": 0x03,
}
_ORCON_BOOST_SPEED_NAMES: dict[int, str] = {
    v: k for k, v in _ORCON_BOOST_SPEEDS.items()
}
_ORCON_BOOST_DURATIONS: tuple[int, ...] = (15, 30, 60)
_ORCON_BOOST_FLAGS = 0x12
_ORCON_BOOST_TAIL = b"\x04\x04\x04"
_ORCON_BOOST_LEN = 7  # bytes


def _orcon_boost_payload(
    speed: str | int,
    minutes: int,
    *,
    flags: int = _ORCON_BOOST_FLAGS,
    tail: bytes = _ORCON_BOOST_TAIL,
) -> str:
    """Assemble a 7-byte Orcon 22F3 boost payload from building blocks.

    :param speed: Speed name ("low"/"medium"/"high") or byte (0x01-0x03).
    :type speed: str | int
    :param minutes: Boost duration in minutes (1-255, or a multiple of
        60 up to 15300 which is encoded via the hours flag).
    :type minutes: int
    :param flags: Flags byte — dialect-dependent (0x12 or 0x02).
    :type flags: int
    :param tail: Bytes 4-6 (fallback mode/fan + pad), dialect-dependent.
    :type tail: bytes
    :returns: The 14-char payload hex string.
    :rtype: str
    """
    speed_byte = (
        _ORCON_BOOST_SPEEDS.get(speed, -1) if isinstance(speed, str) else speed
    )
    if speed_byte not in _ORCON_BOOST_SPEED_NAMES:
        raise ValueError(f"Invalid 22F3 boost speed: {speed!r}")
    if len(tail) != _ORCON_BOOST_LEN - 4:
        raise ValueError(f"Invalid 22F3 tail length: {len(tail)}")
    if minutes <= 0 or minutes > 0xFF * 60:
        raise ValueError(f"Invalid 22F3 boost duration: {minutes}")
    if minutes <= 0xFF:
        duration = minutes
    elif minutes % 60 == 0:
        flags |= 0x40  # duration encoded in hours
        duration = minutes // 60
    else:
        raise ValueError(f"Invalid 22F3 boost duration: {minutes}")
    return (bytes([0x00, flags, duration, speed_byte]) + tail).hex().upper()


def _orcon_boost_command_name(payload: str) -> str | None:
    """Attribute a canonical boost name to an Orcon 22F3 payload.

    Structural match: extracts the duration and speed bytes, tolerating
    flag/tail dialect differences between remote models — e.g.
    ``00120F03040404`` and ``00020F03040000`` both map to ``high_15``
    (issue ramses-rf/ramses_cc#1332).

    :param payload: The 14-char 22F3 payload hex string.
    :type payload: str
    :returns: The canonical ``<speed>_<minutes>`` name, or None if the
        payload is not a recognizable Orcon timed-boost frame.
    :rtype: str | None
    """
    if len(payload) != _ORCON_BOOST_LEN * 2:
        return None
    try:
        raw = bytes.fromhex(payload)
    except ValueError:
        return None
    speed_name = _ORCON_BOOST_SPEED_NAMES.get(raw[3])
    if raw[0] != 0x00 or speed_name is None:
        return None
    minutes = raw[2] * 60 if raw[1] & 0x40 else raw[2]
    if minutes <= 0:
        return None
    return f"{speed_name}_{minutes}"


_ORCON_BOOST_COMMANDS: dict[str, dict[str, str]] = {
    f"{speed}_{minutes}": {
        "verb": "I",
        "code": Code._22F3,
        "payload": _orcon_boost_payload(speed, minutes),
        "type": "boost_timer",
    }
    for speed in _ORCON_BOOST_SPEEDS
    for minutes in _ORCON_BOOST_DURATIONS
}


class OrconStrategy(HvacStrategyBase):
    """Strategy for Orcon ventilation systems."""

    scheme = "orcon"
    _mode_map = _22F1_MODE_ORCON
    _mode_max = _22F1_MODE_MAX[scheme]
    _binding_codes = (Code._22F1, Code._22F3)
    alias_language = "nl"
    _aliases = {
        k: v
        for k, v in HvacStrategyBase._DUTCH_ALIASES.items()
        if v in _22F1_MODE_ORCON.values()
    }
    _builtin_commands: dict[str, dict[str, str]] = dict(_ORCON_BOOST_COMMANDS)
    _boost_aliases = {
        k: v
        for k, v in HvacStrategyBase._DUTCH_BOOST_ALIASES.items()
        if v in _ORCON_BOOST_COMMANDS
    }

    def apply_quirk(
        self,
        payload: SchemaT,
        current_state: HvacState | None,
        msg_code: Code | str,
    ) -> SchemaT:
        """Apply Orcon-specific quirks.

        QUIRK: 3-byte 31D9 mode decode (ramses-rf/ramses_cc#1231).  Short
        Orcon payloads (e.g. MVS-15) carry the active mode as a
        22F1-style index in the speed byte, which the generic parser
        mislabels with Vasco names and reports as a fan speed
        (spd / 200 → a bogus 0-2%).  The parser suppresses
        exhaust_fan_speed only for the 4-byte Orcon format, so its
        presence marks the short decode.  Timed boosts report as high
        (0x03); there is no dedicated boost mode byte.

        The remap runs before ``super().apply_quirk()`` so mode
        indices emitted as raw hex ("06", "07") are translated before
        the base quirk nulls them.

        :param payload: The flattened, canonical telemetry dictionary.
        :type payload: SchemaT
        :param current_state: The existing Read-Model for the device.
        :type current_state: HvacState | None
        :param msg_code: The hex opcode of the incoming message.
        :type msg_code: Code | str
        :returns: The safely mutated telemetry dictionary.
        :rtype: SchemaT
        """
        mutated = dict(payload)
        if msg_code == Code._31D9 and "exhaust_fan_speed" in mutated:
            fan_mode = mutated.get("fan_mode")
            if mode := _31D9_ORCON_MODE_NAMES.get(str(fan_mode)):
                mutated["fan_mode"] = mode
            mutated["exhaust_fan_speed"] = None
        return super().apply_quirk(mutated, current_state, msg_code)

    def boost_command_name(self, code: Code | str, payload: str) -> str | None:
        """Attribute a canonical boost name to an observed 22F3 payload."""
        if code == Code._22F3:
            return _orcon_boost_command_name(payload)
        return None

    def boost_timer_payload(
        self,
        speed: str,
        minutes: int,
        *,
        flags: int = _ORCON_BOOST_FLAGS,
        tail: bytes = _ORCON_BOOST_TAIL,
    ) -> str:
        """Assemble an Orcon 22F3 timed-boost payload (issue 1332).

        ``flags``/``tail`` select the remote-model dialect: classic
        remotes use ``flags=0x12``/``tail=04 04 04`` (the default, as in
        ``_builtin_commands``), while e.g. the VMN-15LF01 emits
        ``flags=0x02``/``tail=04 00 00``.
        """
        return _orcon_boost_payload(speed, minutes, flags=flags, tail=tail)

    def co2_binding_codes(
        self,
    ) -> tuple[Code | tuple[IndexT, Code], ...]:
        """Return the indexed binding offer used by Orcon CO2 sensors."""
        return (
            ("00", Code._31E0),
            ("01", Code._31E0),
            ("00", Code._1298),
        )

    def ventilation_demand_payload(self, value: float) -> str:
        """Encode the second-domain demand used by Orcon VMD units."""
        demand_raw = round(value * 100)
        return f"000000000100{demand_raw:02X}00"

    async def unbind_remote(self, fan: object, device_id: str) -> bool:
        """Release the FAN's binding slot for a REM/CO2 over RF.

        Verified on Orcon hardware (MS-17C01 CO2 → FAN capture,
        ramses_cc issue 1283): the unbind gesture emits the standard
        1FC9 handshake ending in an empty Confirm (payload ``00``).
        """
        return await self._send_unbind_handshake(fan, device_id)


class OrconHrc350Strategy(OrconStrategy):
    """Orcon capability profile for HRC-350 units (VMD-15RMS64, VMD-15RMS86)."""

    def ventilation_demand_payload(self, value: float) -> str:
        """Encode the first-domain high-resolution HRC-350 demand."""
        demand_raw = round(value * 200)
        return f"0000{demand_raw:02X}0001000000"
