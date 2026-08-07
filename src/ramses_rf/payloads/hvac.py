"""RAMSES RF - Ventilation and HVAC payload dataclasses.

This module contains strongly-typed dataclass representations for HVAC / ventilation
packet payloads.
"""

import struct
from dataclasses import dataclass
from typing import ClassVar, Self

from .base import PayloadBase
from .registry import register_payload


@register_payload("22F1")
@dataclass(frozen=True, slots=True)
class FanModePayload(PayloadBase):
    """Fan mode / speed payload (Opcode 22F1).

    2-3 byte Fan Mode (22F1) binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Header / Reserved            : 00
      +1       B      1B   Fan Mode Index               : 02
      +2       B      1B   Fan Mode Max (optional)      : 04
      --------------------------------------------------------------
      Field-spaced hex : 00 02 04
      Payload hex      : 000204

    :param header: Header / reserved prefix byte.
    :type header: int
    :param mode_idx: Current active fan mode index.
    :type mode_idx: int
    :param mode_max: Optional maximum mode limit byte, or None if omitted.
    :type mode_max: int | None
    """

    header: int
    mode_idx: int
    mode_max: int | None = None

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack a fan mode binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked FanModePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 22F1: {len(raw_data)}")
        header = raw_data[0]
        mode_idx = raw_data[1]
        mode_max = raw_data[2] if len(raw_data) >= 3 else None
        return cls(header=header, mode_idx=mode_idx, mode_max=mode_max)

    def to_bytes(self) -> bytes:
        """Pack fan mode data into a binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        if self.mode_max is not None:
            return bytes([self.header, self.mode_idx, self.mode_max])
        return bytes([self.header, self.mode_idx])


@register_payload("2411")
@dataclass(frozen=True, slots=True)
class HvacFanParamPayload(PayloadBase):
    """Command 2411 HVAC fan parameter payload.

    Command 2411 payload binary layout (Big-Endian):
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0      >B      1B   Leading zero byte            : 00
      +1       H      2B   Parameter ID                 : 00 0A
      +3       B      1B   Padding byte                 : 00
      +4       B      1B   Data type ID                 : 10
      +5       i      4B   Current value (int32)        : 00 00 00 05
      +9       i      4B   Minimum value (int32)        : 00 00 00 00
      +13      i      4B   Maximum value (int32)        : 00 00 00 64
      +17      i      4B   Precision scalar (int32)     : 00 00 00 01
      +21     2s      2B   Trailer bytes                : 00 01
      --------------------------------------------------------------
      Field-spaced hex : 00 000A 00 10 00000005 00000000 00000064 00000001 0001
      Payload hex      : 00000A0010000000050000000000000064000000010001

    :param param_id: Parameter ID uint16.
    :type param_id: int
    :param data_type: Data type ID byte.
    :type data_type: int
    :param value_scaled: Current scaled int32 value.
    :type value_scaled: int
    :param min_val_scaled: Minimum scaled int32 value.
    :type min_val_scaled: int
    :param max_val_scaled: Maximum scaled int32 value.
    :type max_val_scaled: int
    :param precision_scaled: Precision scalar int32 value.
    :type precision_scaled: int
    :param trailer_bytes: 2-byte trailer raw bytes.
    :type trailer_bytes: bytes
    """

    _STRUCT_FMT: ClassVar[str] = ">BHBBiiii2s"

    param_id: int
    data_type: int
    value_scaled: int
    min_val_scaled: int
    max_val_scaled: int
    precision_scaled: int
    trailer_bytes: bytes

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack HVAC fan parameter binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked HvacFanParamPayload instance.
        :rtype: Self
        """
        (
            _,
            param_id,
            _,
            data_type,
            val,
            min_val,
            max_val,
            precision,
            trailer,
        ) = struct.unpack(cls._STRUCT_FMT, raw_data)
        return cls(
            param_id=param_id,
            data_type=data_type,
            value_scaled=val,
            min_val_scaled=min_val,
            max_val_scaled=max_val,
            precision_scaled=precision,
            trailer_bytes=trailer,
        )

    def to_bytes(self) -> bytes:
        """Pack HVAC fan parameter data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return struct.pack(
            self._STRUCT_FMT,
            0x00,
            self.param_id,
            0x00,
            self.data_type,
            self.value_scaled,
            self.min_val_scaled,
            self.max_val_scaled,
            self.precision_scaled,
            self.trailer_bytes,
        )


@register_payload("1298")
@dataclass(frozen=True, slots=True)
class Co2Payload(PayloadBase):
    """CO2 sensor reading payload (Opcode 1298).

    2-byte CO2 binary layout (Big-Endian):
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       H      2B   CO2 level in PPM (uint16)    : 02 D0 (720 PPM)
      --------------------------------------------------------------
      Field-spaced hex : 02D0
      Payload hex      : 02D0

    :param co2_ppm: CO2 concentration level in PPM (parts per million).
    :type co2_ppm: int
    """

    co2_ppm: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack 2-byte CO2 sensor reading payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked Co2Payload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError("Invalid payload length for 1298: expected 2 bytes")
        return cls(co2_ppm=int.from_bytes(raw_data[:2], byteorder="big", signed=False))

    def to_bytes(self) -> bytes:
        """Pack CO2 sensor reading data into 2-byte binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return self.co2_ppm.to_bytes(2, byteorder="big", signed=False)


@register_payload("12A0")
@dataclass(frozen=True, slots=True)
class RelativeHumidityPayload(PayloadBase):
    """Relative humidity payload (Opcode 12A0).

    1-2 byte Relative Humidity binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Humidity percentage (uint8)  : 64 (50.0%)
      --------------------------------------------------------------
      Field-spaced hex : 64
      Payload hex      : 64

    :param humidity_percent: Relative humidity value (0.0 - 100.0%).
    :type humidity_percent: float
    """

    humidity_percent: float

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack relative humidity binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked RelativeHumidityPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data is empty.
        """
        if not raw_data:
            raise ValueError("Payload data cannot be empty")
        raw_val = raw_data[0]
        return cls(humidity_percent=raw_val / 2.0)

    def to_bytes(self) -> bytes:
        """Pack relative humidity data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        raw_val = int(round(self.humidity_percent * 2.0))
        return bytes([raw_val])
