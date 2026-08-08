"""RAMSES RF - OpenTherm bridge payload dataclasses.

This module contains strongly-typed dataclass representations for OpenTherm bridge
packet payloads.
"""

from dataclasses import dataclass
from typing import Self

from .base import PayloadBase
from .registry import register_payload


@register_payload("3220")
@dataclass(frozen=True, slots=True)
class OpenThermMsgPayload(PayloadBase):
    """OpenTherm message payload (Opcode 3220).

    2-4 byte OpenTherm frame binary layout (Big-Endian):
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Message ID / Data ID (uint8) : 19 (25 = Boiler temp)
      +1       B      1B   Message Type / Flags         : 00
      +2       2s     2B   Value bytes (uint16/float16) : 19 00 (25.0°C)
      --------------------------------------------------------------
      Field-spaced hex : 19 00 1900
      Payload hex      : 19001900

    :param msg_id: OpenTherm Message ID (Data ID 0-255).
    :type msg_id: int
    :param msg_type: OpenTherm Message Type flag byte.
    :type msg_type: int
    :param raw_value: Raw 2-byte OpenTherm value payload.
    :type raw_value: bytes
    """

    msg_id: int
    msg_type: int
    raw_value: bytes

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack an OpenTherm message binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked OpenThermMsgPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 3220: {len(raw_data)}")
        msg_id = raw_data[0]
        msg_type = raw_data[1]
        raw_val = raw_data[2:] if len(raw_data) >= 3 else b""
        return cls(msg_id=msg_id, msg_type=msg_type, raw_value=raw_val)

    def to_bytes(self) -> bytes:
        """Pack OpenTherm message data into a binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.msg_id, self.msg_type]) + self.raw_value
