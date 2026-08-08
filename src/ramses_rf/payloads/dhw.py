"""RAMSES RF - Domestic Hot Water (DHW) payload dataclasses.

This module contains strongly-typed dataclass representations for Domestic Hot Water
packet payloads.
"""

from dataclasses import dataclass
from typing import Self

from .base import PayloadBase
from .registry import register_payload


@register_payload("1260")
@dataclass(frozen=True, slots=True)
class DhwModePayload(PayloadBase):
    """DHW mode and override payload (Opcode 1260).

    3-byte DHW Mode binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   DHW Index (uint8)            : 00
      +1       B      1B   DHW Mode / Override Flag     : 01
      +2       B      1B   DHW State / Enabled          : 01
      --------------------------------------------------------------
      Field-spaced hex : 00 01 01
      Payload hex      : 000101

    Sample Packet Logs:
      # RQ --- 30:185469 01:037519 --:------ 1260 001 00
      # RP --- 01:037519 30:185469 --:------ 1260 003 000837
      # RQ --- 18:200202 10:067219 --:------ 1260 002 0000
      # RP --- 10:067219 18:200202 --:------ 1260 003 007FFF

    :param dhw_idx: DHW index byte.
    :type dhw_idx: int
    :param mode: Mode or override flag byte.
    :type mode: int
    :param state: DHW state byte (enabled/disabled).
    :type state: int
    """

    dhw_idx: int
    mode: int
    state: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack DHW mode binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked DhwModePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 3 bytes.
        """
        if len(raw_data) < 3:
            raise ValueError(f"Invalid payload length for 1260: {len(raw_data)}")
        return cls(dhw_idx=raw_data[0], mode=raw_data[1], state=raw_data[2])

    def to_bytes(self) -> bytes:
        """Pack DHW mode data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.dhw_idx, self.mode, self.state])


@register_payload("12F0")
@dataclass(frozen=True, slots=True)
class DhwConfigPayload(PayloadBase):
    """DHW configuration payload (Opcode 12F0).

    3-byte DHW Config binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   DHW Index (uint8)            : 00
      +1       h      2B   Target Setpoint (int16*100)  : 13 88 (50.00°C)
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
            raise ValueError(f"Invalid payload length for 12F0: {len(raw_data)}")
        idx = raw_data[0]
        setpoint_raw = int.from_bytes(raw_data[1:3], byteorder="big", signed=True)
        return cls(dhw_idx=idx, setpoint_temp=setpoint_raw / 100.0)

    def to_bytes(self) -> bytes:
        """Pack DHW config data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        setpoint_raw = int(round(self.setpoint_temp * 100.0))
        return bytes([self.dhw_idx]) + setpoint_raw.to_bytes(
            2, byteorder="big", signed=True
        )


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
        return cls(dhw_idx=raw_data[0], active_flag=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack DHW state data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.dhw_idx, self.active_flag])


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
