"""RAMSES RF - Ventilation and HVAC payload dataclasses.

This module contains strongly-typed dataclass representations for HVAC / ventilation
packet payloads.
"""

from dataclasses import dataclass
from typing import Self

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
