"""RAMSES RF - Heating and Evohome payload dataclasses.

This module contains strongly-typed dataclass representations for CH / Evohome
packet payloads.
"""

import struct
from dataclasses import dataclass
from typing import ClassVar, Self

from .base import PayloadBase
from .registry import register_payload


@register_payload("3150")
@dataclass(frozen=True, slots=True)
class HeatDemandPayload(PayloadBase):
    """Heat demand payload (Opcode 3150).

    1-byte Heat Demand binary layout (Simple Byte):
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Heat demand percentage (uint8) : C8 (200)
      --------------------------------------------------------------
      Field-spaced hex : C8
      Payload hex      : C8

    :param demand_percent: Heat demand value (0-200, where 200 = 100%).
    :type demand_percent: int
    """

    demand_percent: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack a simple 1-byte heat demand payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked HeatDemandPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data is empty.
        """
        if not raw_data:
            raise ValueError("Payload data cannot be empty")
        return cls(
            demand_percent=int.from_bytes(raw_data, byteorder="little"),
        )

    def to_bytes(self) -> bytes:
        """Pack a simple 1-byte heat demand payload.

        :returns: Packed 1-byte binary payload.
        :rtype: bytes
        """
        return self.demand_percent.to_bytes(1, byteorder="little")


@register_payload("30C9")
@dataclass(frozen=True, slots=True)
class TemperaturePayload(PayloadBase):
    """Temperature payload (Opcode 30C9).

    2-3 byte Zone Temp / Simple Temp binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Zone Index (optional uint8)  : 01
      +1       h      2B   Temperature (int16, degC*100): 07 D0 (20.00°C)
      --------------------------------------------------------------
      Field-spaced hex : 01 07D0
      Payload hex      : 0107D0

    :param zone_idx: Optional zone index byte, or None if simple temperature.
    :type zone_idx: int | None
    :param temperature: Temperature in °C, False if disabled, or None if N/A.
    :type temperature: float | bool | None
    """

    zone_idx: int | None
    temperature: float | bool | None

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack a temperature binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked TemperaturePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is invalid.
        """
        if len(raw_data) == 2:
            idx = None
            temp_bytes = raw_data
        elif len(raw_data) >= 3:
            idx = raw_data[0]
            temp_bytes = raw_data[1:3]
        else:
            raise ValueError(f"Invalid payload length for 30C9: {len(raw_data)}")

        temp_raw = int.from_bytes(temp_bytes, byteorder="big", signed=True)
        if temp_raw in (0x31FF, 0x7FFF):
            temp_val: float | bool | None = None
        elif temp_raw == 0x7EFF:
            temp_val = False
        else:
            temp_val = temp_raw / 100.0

        return cls(zone_idx=idx, temperature=temp_val)

    def to_bytes(self) -> bytes:
        """Pack temperature data into a binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        if self.temperature is None:
            temp_raw = 0x7FFF
        elif self.temperature is False:
            temp_raw = 0x7EFF
        else:
            temp_raw = int(round(self.temperature * 100.0))

        temp_bytes = temp_raw.to_bytes(2, byteorder="big", signed=True)
        if self.zone_idx is not None:
            return bytes([self.zone_idx]) + temp_bytes
        return temp_bytes


@register_payload("0404")
@dataclass(frozen=True, slots=True)
class ScheduleSwitchpointPayload(PayloadBase):
    """Schedule switchpoint payload (Opcode 0404).

    20-byte Schedule Switchpoint binary layout (Little-Endian):
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       4x     4B   Padding / Header bytes       : 00 00 00 00
      +4       B      1B   Zone/Domain index (uint8)    : 01
      +5       3x     3B   Padding bytes                : 00 00 00
      +8       B      1B   Day of week (uint8, 1-7)     : 01
      +9       3x     3B   Padding bytes                : 00 00 00
      +12      H      2B   Time of day (uint16 mins)    : 68 01
      +14      2x     2B   Padding bytes                : 00 00
      +16      H      2B   Setpoint value / state (u16) : D0 07
      +18      H      2B   Reserved / Trailer bytes     : 00 00
      --------------------------------------------------------------
      Field-spaced hex : 00000000 01 000000 01 000000 6801 0000 D007 0000
      Payload hex      : 00000000010000000100000068010000D0070000

    :param zone_idx: Zone/domain index byte.
    :type zone_idx: int
    :param day_of_week: Day of week integer (1-7).
    :type day_of_week: int
    :param time_of_day_mins: Time of day in minutes.
    :type time_of_day_mins: int
    :param setpoint_value: Setpoint value or state raw uint16.
    :type setpoint_value: int
    """

    _STRUCT_FMT: ClassVar[str] = "<xxxxBxxxBxxxHxxHH"

    zone_idx: int
    day_of_week: int
    time_of_day_mins: int
    setpoint_value: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack a compressed 20-byte RAMSES binary schedule switchpoint.

        :param raw_data: 20-byte schedule binary block.
        :type raw_data: bytes
        :returns: Unpacked ScheduleSwitchpointPayload instance.
        :rtype: Self
        """
        idx, dow, tod, val, _ = struct.unpack(cls._STRUCT_FMT, raw_data)
        return cls(
            zone_idx=idx,
            day_of_week=dow,
            time_of_day_mins=tod,
            setpoint_value=val,
        )

    def to_bytes(self) -> bytes:
        """Pack schedule switchpoint information into bytes.

        :returns: Packed 20-byte binary payload bytes.
        :rtype: bytes
        """
        return struct.pack(
            self._STRUCT_FMT,
            self.zone_idx,
            self.day_of_week,
            self.time_of_day_mins,
            self.setpoint_value,
            0,  # Reserved / trailer 2-byte field (0x0000)
        )


@register_payload("10A0")
@dataclass(frozen=True, slots=True)
class DhwTemperaturePayload(PayloadBase):
    """DHW Temperature payload (Opcode 10A0).

    2-3 byte DHW Temp binary layout (Big-Endian):
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   DHW Index (optional uint8)   : 00
      +1       h      2B   Temperature (int16, degC*100): 0E D8 (38.00°C)
      --------------------------------------------------------------
      Field-spaced hex : 00 0ED8
      Payload hex      : 000ED8

    :param dhw_idx: Optional DHW index byte, or None.
    :type dhw_idx: int | None
    :param temperature: DHW temperature in °C, False if disabled, or None.
    :type temperature: float | bool | None
    """

    dhw_idx: int | None
    temperature: float | bool | None

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack DHW temperature binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked DhwTemperaturePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is invalid.
        """
        if len(raw_data) == 2:
            idx = None
            temp_bytes = raw_data
        elif len(raw_data) >= 3:
            idx = raw_data[0]
            temp_bytes = raw_data[1:3]
        else:
            raise ValueError(f"Invalid payload length for 10A0: {len(raw_data)}")

        temp_raw = int.from_bytes(temp_bytes, byteorder="big", signed=True)
        if temp_raw in (0x31FF, 0x7FFF):
            temp_val: float | bool | None = None
        elif temp_raw == 0x7EFF:
            temp_val = False
        else:
            temp_val = temp_raw / 100.0

        return cls(dhw_idx=idx, temperature=temp_val)

    def to_bytes(self) -> bytes:
        """Pack DHW temperature data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        if self.temperature is None:
            temp_raw = 0x7FFF
        elif self.temperature is False:
            temp_raw = 0x7EFF
        else:
            temp_raw = int(round(self.temperature * 100.0))

        temp_bytes = temp_raw.to_bytes(2, byteorder="big", signed=True)
        if self.dhw_idx is not None:
            return bytes([self.dhw_idx]) + temp_bytes
        return temp_bytes


@register_payload("1030")
@dataclass(frozen=True, slots=True)
class SystemSyncPayload(PayloadBase):
    """System Sync payload (Opcode 1030).

    1-byte System Sync binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Sync Flag / Counter (uint8)  : 00
      --------------------------------------------------------------
      Field-spaced hex : 00
      Payload hex      : 00

    :param sync_flag: System synchronization counter or status byte.
    :type sync_flag: int
    """

    sync_flag: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack system sync binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemSyncPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data is empty.
        """
        if not raw_data:
            raise ValueError("Payload data cannot be empty")
        return cls(sync_flag=raw_data[0])

    def to_bytes(self) -> bytes:
        """Pack system sync data into a 1-byte binary payload.

        :returns: Packed 1-byte binary payload.
        :rtype: bytes
        """
        return bytes([self.sync_flag])


@register_payload("1FC9")
@dataclass(frozen=True, slots=True)
class BindingPayload(PayloadBase):
    """Binding payload (Opcode 1FC9).

    Encapsulates binding offer / confirmation metadata between devices.

    :param binding_type: Binding type or domain byte.
    :type binding_type: int
    :param binding_data: Binding payload raw byte data.
    :type binding_data: bytes
    """

    binding_type: int
    binding_data: bytes

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack binding binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked BindingPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data is empty.
        """
        if not raw_data:
            raise ValueError("Payload data cannot be empty")
        b_type = raw_data[0]
        b_data = raw_data[1:]
        return cls(binding_type=b_type, binding_data=b_data)

    def to_bytes(self) -> bytes:
        """Pack binding data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.binding_type]) + self.binding_data


@register_payload("000A")
@dataclass(frozen=True, slots=True)
class ZoneConfigPayload(PayloadBase):
    """Zone configuration payload (Opcode 000A).

    6-byte Zone Config binary layout (Big-Endian):
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Zone Index (uint8)           : 00
      +1       B      1B   Zone Type / Flags            : 00
      +2       h      2B   Min Temp (int16, degC*100)   : 01 F4 (5.00°C)
      +4       h      2B   Max Temp (int16, degC*100)   : 0D B8 (35.00°C)
      --------------------------------------------------------------
      Field-spaced hex : 00 00 01F4 0DB8
      Payload hex      : 000001F40DB8

    :param zone_idx: Zone index integer.
    :type zone_idx: int
    :param zone_flags: Zone flags byte.
    :type zone_flags: int
    :param min_temp: Minimum zone temperature setting in °C.
    :type min_temp: float
    :param max_temp: Maximum zone temperature setting in °C.
    :type max_temp: float
    """

    _STRUCT_FMT: ClassVar[str] = ">BBhh"

    zone_idx: int
    zone_flags: int
    min_temp: float
    max_temp: float

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack zone config binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked ZoneConfigPayload instance.
        :rtype: Self
        """
        idx, flags, min_raw, max_raw = struct.unpack(cls._STRUCT_FMT, raw_data)
        return cls(
            zone_idx=idx,
            zone_flags=flags,
            min_temp=min_raw / 100.0,
            max_temp=max_raw / 100.0,
        )

    def to_bytes(self) -> bytes:
        """Pack zone config data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        min_raw = int(round(self.min_temp * 100.0))
        max_raw = int(round(self.max_temp * 100.0))
        return struct.pack(
            self._STRUCT_FMT,
            self.zone_idx,
            self.zone_flags,
            min_raw,
            max_raw,
        )
