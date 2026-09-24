"""RAMSES RF - Orcon HVAC strategy."""

from __future__ import annotations

from typing import Any

from ramses_rf.models import HvacState
from ramses_rf.models.hvac_schemas import _22F1_MODE_MAX, _22F1_MODE_ORCON
from ramses_rf.strategies.base import HvacStrategyBase
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

# 22F3 timed boost commands (7-byte Orcon format).
# Payload: 00 12 <mins> <speed> 04 04 04
# Speed: 01=low, 02=medium, 03=high
# Durations: 0F=15, 1E=30, 3C=60 minutes
_ORCON_BOOST_COMMANDS: dict[str, dict[str, str]] = {
    "low_15": {
        "verb": "I",
        "code": Code._22F3,
        "payload": "00120F01040404",
        "type": "boost_timer",
    },
    "low_30": {
        "verb": "I",
        "code": Code._22F3,
        "payload": "00121E01040404",
        "type": "boost_timer",
    },
    "low_60": {
        "verb": "I",
        "code": Code._22F3,
        "payload": "00123C01040404",
        "type": "boost_timer",
    },
    "medium_15": {
        "verb": "I",
        "code": Code._22F3,
        "payload": "00120F02040404",
        "type": "boost_timer",
    },
    "medium_30": {
        "verb": "I",
        "code": Code._22F3,
        "payload": "00121E02040404",
        "type": "boost_timer",
    },
    "medium_60": {
        "verb": "I",
        "code": Code._22F3,
        "payload": "00123C02040404",
        "type": "boost_timer",
    },
    "high_15": {
        "verb": "I",
        "code": Code._22F3,
        "payload": "00120F03040404",
        "type": "boost_timer",
    },
    "high_30": {
        "verb": "I",
        "code": Code._22F3,
        "payload": "00121E03040404",
        "type": "boost_timer",
    },
    "high_60": {
        "verb": "I",
        "code": Code._22F3,
        "payload": "00123C03040404",
        "type": "boost_timer",
    },
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
        payload: dict[str, Any],
        current_state: HvacState | None,
        msg_code: Code | str,
    ) -> dict[str, Any]:
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
        :type payload: dict[str, Any]
        :param current_state: The existing Read-Model for the device.
        :type current_state: HvacState | None
        :param msg_code: The hex opcode of the incoming message.
        :type msg_code: Code | str
        :returns: The safely mutated telemetry dictionary.
        :rtype: dict[str, Any]
        """
        mutated = dict(payload)
        if msg_code == Code._31D9 and "exhaust_fan_speed" in mutated:
            fan_mode = mutated.get("fan_mode")
            if mode := _31D9_ORCON_MODE_NAMES.get(str(fan_mode)):
                mutated["fan_mode"] = mode
            mutated["exhaust_fan_speed"] = None
        return super().apply_quirk(mutated, current_state, msg_code)

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


class OrconHrc350Strategy(OrconStrategy):
    """Orcon capability profile for VMD-15RMS64/HRC-350 units."""

    def ventilation_demand_payload(self, value: float) -> str:
        """Encode the first-domain high-resolution HRC-350 demand."""
        demand_raw = round(value * 200)
        return f"0000{demand_raw:02X}0001000000"
