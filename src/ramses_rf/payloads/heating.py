"""RAMSES RF - Heating and Evohome payload dataclasses.

This module contains strongly-typed dataclass representations for CH / Evohome
packet payloads.
"""

from dataclasses import dataclass
from typing import Self

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
