"""RAMSES RF - Domestic Hot Water (DHW) payload dataclasses.

This module contains strongly-typed dataclass representations for Domestic Hot Water
packet payloads.
"""

import struct
from dataclasses import dataclass
from typing import Any, ClassVar, Self

from .base import PayloadBase, parse_idx
from .registry import register_payload


@register_payload("1260")
@dataclass(frozen=True, slots=True)
class DhwTempPayload(PayloadBase):
    """DHW cylinder temperature payload (Opcode 1260).

    3-byte DHW Temp binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   DHW Index (uint8)            : 00
      +1       h      2B   Temperature (int16*100)      : 08 37 (21.03°C)
      --------------------------------------------------------------
      Field-spaced hex : 00 0837
      Payload hex      : 000837

    Sample Packet Logs:
      # RQ --- 30:185469 01:037519 --:------ 1260 001 00
      # RP --- 01:037519 30:185469 --:------ 1260 003 000837
      # RQ --- 18:200202 10:067219 --:------ 1260 002 0000
      # RP --- 10:067219 18:200202 --:------ 1260 003 007FFF

    :param dhw_idx: DHW index byte.
    :type dhw_idx: int
    :param temperature: DHW cylinder temperature in °C, or None if invalid.
    :type temperature: float | None
    """

    _STRUCT_FMT: ClassVar[str] = ">Bh"

    dhw_idx: int
    temperature: float | None

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack DHW cylinder temperature binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked DhwTempPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 3 bytes.
        """
        if len(raw_data) < 3:
            raise ValueError(f"Invalid payload length for 1260: {len(raw_data)}")
        idx, temp_raw = struct.unpack_from(cls._STRUCT_FMT, raw_data, 0)
        temp_val = None if temp_raw in (0x31FF, 0x7FFF) else temp_raw / 100.0
        return cls(dhw_idx=idx, temperature=temp_val)

    def to_bytes(self) -> bytes:
        """Pack DHW cylinder temperature data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        temp_raw = (
            0x7FFF if self.temperature is None else int(round(self.temperature * 100.0))
        )
        return struct.pack(self._STRUCT_FMT, self.dhw_idx, temp_raw)

    def to_dict(self) -> dict[str, Any]:
        """Convert DHW temperature payload to legacy dictionary layout.

        :returns: Decoded DHW temperature dictionary.
        :rtype: dict[str, Any]
        """
        return {"temperature": self.temperature}


@register_payload("12F0")
@dataclass(frozen=True, slots=True)
class DhwFlowRatePayload(PayloadBase):
    """DHW flow rate payload (Opcode 12F0).

    3-byte DHW Flow Rate binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   DHW Index (uint8)            : 00
      +1       h      2B   Flow Rate (int16*100)        : 03 07 (7.75 L/min)
      --------------------------------------------------------------
      Field-spaced hex : 00 0307
      Payload hex      : 000307

    Sample Packet Logs:
      # RP --- 10:048122 18:006402 --:------ 12F0 003 000307

    :param dhw_idx: DHW index byte.
    :type dhw_idx: int
    :param dhw_flow_rate: DHW flow rate in L/min, or None if invalid.
    :type dhw_flow_rate: float | None
    """

    _STRUCT_FMT: ClassVar[str] = ">Bh"

    dhw_idx: int
    dhw_flow_rate: float | None

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack DHW flow rate binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked DhwFlowRatePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 3 bytes.
        """
        if len(raw_data) < 3:
            raise ValueError(f"Invalid payload length for 12F0: {len(raw_data)}")
        idx, flow_raw = struct.unpack_from(cls._STRUCT_FMT, raw_data, 0)
        val = None if flow_raw in (0x31FF, 0x7FFF) else flow_raw / 100.0
        return cls(dhw_idx=idx, dhw_flow_rate=val)

    def to_bytes(self) -> bytes:
        """Pack DHW flow rate data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        raw_val = (
            0x7FFF
            if self.dhw_flow_rate is None
            else int(round(self.dhw_flow_rate * 100.0))
        )
        return struct.pack(self._STRUCT_FMT, self.dhw_idx, raw_val)

    def to_dict(self) -> dict[str, Any]:
        """Convert DHW flow rate payload to legacy dictionary layout.

        :returns: Decoded DHW flow rate dictionary.
        :rtype: dict[str, Any]
        """
        return {"dhw_flow_rate": self.dhw_flow_rate}


@dataclass(frozen=True, slots=True)
class DhwConfigPayload(PayloadBase):
    """DHW configuration payload.

    3-byte DHW Config binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   DHW Index (uint8)            : 00
      +1       h      2B   Setpoint Temp (int16*100)    : 13 88 (50.00°C)
      --------------------------------------------------------------
      Field-spaced hex : 00 1388
      Payload hex      : 001388

    Sample Packet Logs:
      # RP --- 10:023327 18:131597 --:------ 12F0 003 000307
      # RP --- 10:023327 18:131597 --:------ 12F0 003 000023
      # RP --- 10:051349 18:135447 --:------ 12F0 003 00059F

    :param dhw_idx: DHW index byte.
    :type dhw_idx: int
    :param setpoint_temp: Target DHW setpoint temperature in °C.
    :type setpoint_temp: float
    """

    _STRUCT_FMT: ClassVar[str] = ">Bh"

    dhw_idx: int
    setpoint_temp: float

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack DHW config binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked DhwConfigPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 3 bytes.
        """
        if len(raw_data) < 3:
            raise ValueError(
                f"Invalid payload length for DhwConfigPayload: {len(raw_data)}"
            )
        idx, setpoint_raw = struct.unpack_from(cls._STRUCT_FMT, raw_data, 0)
        return cls(dhw_idx=idx, setpoint_temp=setpoint_raw / 100.0)

    def to_bytes(self) -> bytes:
        """Pack DHW config data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        sp_raw = int(round(self.setpoint_temp * 100.0))
        return struct.pack(self._STRUCT_FMT, self.dhw_idx, sp_raw)


@register_payload("10A0")
@dataclass(frozen=True, slots=True)
class DhwParamsPayload(PayloadBase):
    """DHW parameters payload (Opcode 10A0 W/RP payload).

    3-byte or 6-byte DHW Parameters binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   DHW Index (uint8)            : 00
      +1       h      2B   Setpoint Temp (int16*100)    : 13 88 (50.00°C)
      +3       B      1B   Overrun minutes (optional)   : 00
      +4       h      2B   Differential °C (optional)   : 03 E4 (10.00°C)
      --------------------------------------------------------------
      Field-spaced hex : 00 1388 00 03E4
      Payload hex      : 0013880003E4

    Sample Packet Logs:
      # RQ --- 07:045960 01:145038 --:------ 10A0 006 0013740003E4
      # RP --- 01:145038 07:045960 --:------ 10A0 006 00109A0003E8
      # RP --- 10:048122 18:006402 --:------ 10A0 003 001B58

    :param dhw_idx: DHW index byte.
    :type dhw_idx: int | str
    :param setpoint: Target setpoint temperature in °C.
    :type setpoint: float
    :param overrun: Overrun time in minutes (default 0).
    :type overrun: int
    :param differential: Temperature differential in °C (default 0.0).
    :type differential: float
    """

    _STRUCT_FMT_SHORT: ClassVar[str] = ">Bh"
    _STRUCT_FMT_LONG: ClassVar[str] = ">BhBh"

    dhw_idx: int | str
    setpoint: float | None
    overrun: int = 0
    differential: float = 0.0

    def __post_init__(self) -> None:
        """Normalise index arguments."""
        if isinstance(self.dhw_idx, str):
            object.__setattr__(self, "dhw_idx", parse_idx(self.dhw_idx))

    @classmethod
    def _parse_sp(cls, sp_raw: int) -> float | None:
        """Decode raw setpoint temperature."""
        if sp_raw in (0x31FF, 0x7FFF, 0x639C):
            return None
        return sp_raw / 100.0

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack DHW parameters binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked DhwParamsPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 3 bytes.
        """
        if len(raw_data) < 3:
            raise ValueError(f"Invalid payload length for 10A0: {len(raw_data)}")
        if len(raw_data) >= 6:
            idx, sp_raw, overrun, diff_raw = struct.unpack_from(
                cls._STRUCT_FMT_LONG, raw_data, 0
            )
            return cls(
                dhw_idx=idx,
                setpoint=cls._parse_sp(sp_raw),
                overrun=overrun,
                differential=diff_raw / 100.0,
            )
        idx, sp_raw = struct.unpack_from(cls._STRUCT_FMT_SHORT, raw_data, 0)
        return cls(dhw_idx=idx, setpoint=cls._parse_sp(sp_raw))

    def to_bytes(self) -> bytes:
        """Pack DHW parameters data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        sp_raw = 0x7FFF if self.setpoint is None else int(round(self.setpoint * 100.0))
        idx = parse_idx(self.dhw_idx)
        if self.overrun != 0 or self.differential != 0.0:
            diff_raw = int(round(self.differential * 100.0))
            return struct.pack(
                self._STRUCT_FMT_LONG, idx, sp_raw, self.overrun, diff_raw
            )
        return struct.pack(self._STRUCT_FMT_SHORT, idx, sp_raw)

    def to_dict(self) -> dict[str, Any]:
        """Convert DHW parameters payload to legacy dictionary layout.

        :returns: Decoded DHW parameters dictionary.
        :rtype: dict[str, Any]
        """
        res: dict[str, Any] = {"setpoint": self.setpoint}
        if self.overrun != 0 or self.differential != 0.0:
            res["overrun"] = self.overrun
            res["differential"] = self.differential
        return res


@register_payload("1F41")
@dataclass(frozen=True, slots=True)
class DhwStatePayload(PayloadBase):
    """DHW state payload (Opcode 1F41).

    2-byte DHW State binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   DHW Index (uint8)            : 00
      +1       B      1B   DHW Active Flag (0=Off, 1=On): 01
      --------------------------------------------------------------
      Field-spaced hex : 00 01
      Payload hex      : 0001

    Sample Packet Logs:
      # RP --- 01:145038 18:013393 --:------ 1F41 006 00FF00FFFFFF  # no stored DHW
      # Note: Evohome DHW acknowledges W 1F41 with I 1F41 rather than RP 1F41.

    :param dhw_idx: DHW index byte.
    :type dhw_idx: int
    :param active_flag: DHW active status flag byte.
    :type active_flag: int
    """

    _STRUCT_FMT: ClassVar[str] = ">BB"

    dhw_idx: int
    active_flag: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack DHW state binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked DhwStatePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 1F41: {len(raw_data)}")
        idx, active = struct.unpack_from(cls._STRUCT_FMT, raw_data, 0)
        return cls(dhw_idx=idx, active_flag=active)

    def to_bytes(self) -> bytes:
        """Pack DHW state data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return struct.pack(self._STRUCT_FMT, self.dhw_idx, self.active_flag)


@register_payload("11F0")
@dataclass(frozen=True, slots=True)
class DhwHeatpumpRelayPayload(PayloadBase):
    """Heatpump relay status payload (Opcode 11F0).

    9-byte Heatpump Relay Status binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       9B     9B   Raw Relay Status Byte Array  : 00 00 09 00 00 00 00 00 00
      --------------------------------------------------------------
      Field-spaced hex : 00 00 09 00 00 00 00 00 00
      Payload hex      : 000009000000000000

    :param raw_status_bytes: Raw status bytes sequence.
    :type raw_status_bytes: bytes
    """

    raw_status_bytes: bytes

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack heatpump relay status binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked DhwHeatpumpRelayPayload instance.
        :rtype: Self
        """
        return cls(raw_status_bytes=raw_data)

    def to_bytes(self) -> bytes:
        """Pack heatpump relay status data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return self.raw_status_bytes
