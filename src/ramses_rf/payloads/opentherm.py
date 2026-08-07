"""RAMSES RF - OpenTherm bridge payload dataclasses.

This module contains strongly-typed dataclass representations for OpenTherm bridge
and boiler gateway packet payloads.
"""

from dataclasses import dataclass
from typing import Self

from .base import PayloadBase
from .registry import register_payload


@register_payload("3220")
@dataclass(frozen=True, slots=True)
class OpenThermMsgPayload(PayloadBase):
    """OpenTherm message payload (Opcode 3220).

    4-byte OpenTherm Message binary layout (Big-Endian):
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   OpenTherm Msg Type           : 19
      +1       B      1B   OpenTherm Data ID            : 00
      +2       2s     2B   OpenTherm Raw Data Value     : 19 00
      --------------------------------------------------------------
      Field-spaced hex : 19 00 1900
      Payload hex      : 19001900

    :param msg_id: OpenTherm Data ID byte (0-255).
    :type msg_id: int
    :param msg_type: OpenTherm message type classification (0-7).
    :type msg_type: int
    :param raw_value: Raw 2-byte OpenTherm data value.
    :type raw_value: bytes
    """

    msg_id: int
    msg_type: int
    raw_value: bytes

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack 4-byte OpenTherm message binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked OpenThermMsgPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 4 bytes.
        """
        if len(raw_data) < 4:
            raise ValueError(f"Invalid payload length for 3220: {len(raw_data)}")

        m_type = (raw_data[0] >> 4) & 0x07
        m_id = raw_data[1]
        val = raw_data[2:4]

        return cls(msg_id=m_id, msg_type=m_type, raw_value=val)

    def to_bytes(self) -> bytes:
        """Pack OpenTherm message data into 4-byte binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        header_byte = (self.msg_type & 0x07) << 4
        return bytes([header_byte, self.msg_id]) + self.raw_value[:2]


@register_payload("0150")
@dataclass(frozen=True, slots=True)
class OpenthermStatusPayload(PayloadBase):
    """OpenTherm status payload (Opcode 0150).

    2-byte OpenTherm Status binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Master Status Flags (uint8)  : 01
      +1       B      1B   Slave Status Flags (uint8)   : 00
      --------------------------------------------------------------
      Field-spaced hex : 01 00
      Payload hex      : 0100

    :param master_status: Master status flags byte.
    :type master_status: int
    :param slave_status: Slave status flags byte.
    :type slave_status: int
    """

    master_status: int
    slave_status: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack OpenTherm status binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked OpenthermStatusPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 0150: {len(raw_data)}")
        return cls(master_status=raw_data[0], slave_status=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack OpenTherm status data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.master_status, self.slave_status])


@register_payload("1098")
@dataclass(frozen=True, slots=True)
class OpenthermSetpointPayload(PayloadBase):
    """OpenTherm control setpoint payload (Opcode 1098).

    2-byte OpenTherm Setpoint binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       h      2B   Setpoint Temperature (int16*100): 13 88 (50.00°C)
      --------------------------------------------------------------
      Field-spaced hex : 1388
      Payload hex      : 1388

    :param setpoint_temp: Target control setpoint temperature in °C.
    :type setpoint_temp: float
    """

    setpoint_temp: float

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack OpenTherm setpoint binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked OpenthermSetpointPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 1098: {len(raw_data)}")
        sp_raw = int.from_bytes(raw_data[:2], byteorder="big", signed=True)
        return cls(setpoint_temp=sp_raw / 100.0)

    def to_bytes(self) -> bytes:
        """Pack OpenTherm setpoint data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        sp_raw = int(round(self.setpoint_temp * 100.0))
        return sp_raw.to_bytes(2, byteorder="big", signed=True)


@register_payload("10B0")
@dataclass(frozen=True, slots=True)
class OpenthermTemperaturePayload(PayloadBase):
    """OpenTherm boiler water temperature payload (Opcode 10B0).

    2-byte OpenTherm Temperature binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       h      2B   Water Temperature (int16*100): 17 70 (60.00°C)
      --------------------------------------------------------------
      Field-spaced hex : 1770
      Payload hex      : 1770

    :param temperature: Water temperature reading in °C.
    :type temperature: float
    """

    temperature: float

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack OpenTherm temperature binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked OpenthermTemperaturePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 10B0: {len(raw_data)}")
        temp_raw = int.from_bytes(raw_data[:2], byteorder="big", signed=True)
        return cls(temperature=temp_raw / 100.0)

    def to_bytes(self) -> bytes:
        """Pack OpenTherm temperature data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        temp_raw = int(round(self.temperature * 100.0))
        return temp_raw.to_bytes(2, byteorder="big", signed=True)


@register_payload("1FD0")
@dataclass(frozen=True, slots=True)
class OpenthermDiagnosticsPayload(PayloadBase):
    """OpenTherm diagnostics payload (Opcode 1FD0).

    2-byte OpenTherm Diagnostics binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Diagnostic Code (uint8)      : 00
      +1       B      1B   Diagnostic Flags (uint8)     : 00
      --------------------------------------------------------------
      Field-spaced hex : 00 00
      Payload hex      : 0000

    :param diag_code: OpenTherm diagnostic code.
    :type diag_code: int
    :param flags: Diagnostic flags.
    :type flags: int
    """

    diag_code: int
    flags: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack OpenTherm diagnostics binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked OpenthermDiagnosticsPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 1FD0: {len(raw_data)}")
        return cls(diag_code=raw_data[0], flags=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack OpenTherm diagnostics data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.diag_code, self.flags])


@register_payload("1FD4")
@dataclass(frozen=True, slots=True)
class OpenthermFaultFlagsPayload(PayloadBase):
    """OpenTherm fault flags payload (Opcode 1FD4).

    2-byte OpenTherm Fault Flags binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Fault Code (uint8)           : 00
      +1       B      1B   Fault Flags (uint8)          : 00
      --------------------------------------------------------------
      Field-spaced hex : 00 00
      Payload hex      : 0000

    :param fault_code: Fault code byte.
    :type fault_code: int
    :param flags: Fault flags byte.
    :type flags: int
    """

    fault_code: int
    flags: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack OpenTherm fault flags binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked OpenthermFaultFlagsPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 1FD4: {len(raw_data)}")
        return cls(fault_code=raw_data[0], flags=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack OpenTherm fault flags data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.fault_code, self.flags])


@register_payload("2400")
@dataclass(frozen=True, slots=True)
class OpenthermConfigPayload(PayloadBase):
    """OpenTherm configuration parameter payload (Opcode 2400).

    2-byte OpenTherm Configuration binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Parameter Index (uint8)      : 00
      +1       B      1B   Parameter Value (uint8)      : 64 (100)
      --------------------------------------------------------------
      Field-spaced hex : 00 64
      Payload hex      : 0064

    :param param_idx: Parameter index byte.
    :type param_idx: int
    :param param_value: Parameter value byte.
    :type param_value: int
    """

    param_idx: int
    param_value: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack OpenTherm configuration binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked OpenthermConfigPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 2400: {len(raw_data)}")
        return cls(param_idx=raw_data[0], param_value=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack OpenTherm configuration data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.param_idx, self.param_value])


@register_payload("2401")
@dataclass(frozen=True, slots=True)
class OpenthermParamsPayload(PayloadBase):
    """OpenTherm operational parameters payload (Opcode 2401).

    2-byte OpenTherm Parameters binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Parameter Index (uint8)      : 00
      +1       B      1B   Parameter Value (uint8)      : 01
      --------------------------------------------------------------
      Field-spaced hex : 00 01
      Payload hex      : 0001

    :param param_idx: Parameter index byte.
    :type param_idx: int
    :param param_val: Parameter value byte.
    :type param_val: int
    """

    param_idx: int
    param_val: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack OpenTherm parameters binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked OpenthermParamsPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 2401: {len(raw_data)}")
        return cls(param_idx=raw_data[0], param_val=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack OpenTherm parameters data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.param_idx, self.param_val])


@register_payload("2410")
@dataclass(frozen=True, slots=True)
class OpenthermCapacityPayload(PayloadBase):
    """OpenTherm capacity payload (Opcode 2410).

    2-byte OpenTherm Capacity binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Capacity Index (uint8)       : 00
      +1       B      1B   Capacity Value (uint8)       : 64 (100)
      --------------------------------------------------------------
      Field-spaced hex : 00 64
      Payload hex      : 0064

    :param capacity_idx: Capacity index byte.
    :type capacity_idx: int
    :param capacity_val: Capacity value byte.
    :type capacity_val: int
    """

    capacity_idx: int
    capacity_val: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack OpenTherm capacity binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked OpenthermCapacityPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 2410: {len(raw_data)}")
        return cls(capacity_idx=raw_data[0], capacity_val=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack OpenTherm capacity data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.capacity_idx, self.capacity_val])


@register_payload("2420")
@dataclass(frozen=True, slots=True)
class OpenthermModulationPayload(PayloadBase):
    """OpenTherm modulation payload (Opcode 2420).

    2-byte OpenTherm Modulation binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Modulation Index (uint8)     : 00
      +1       B      1B   Modulation Percent (uint8)   : C8 (100%)
      --------------------------------------------------------------
      Field-spaced hex : 00 C8
      Payload hex      : 00C8

    :param mod_idx: Modulation index byte.
    :type mod_idx: int
    :param mod_percent: Modulation percentage byte.
    :type mod_percent: int
    """

    mod_idx: int
    mod_percent: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack OpenTherm modulation binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked OpenthermModulationPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 2420: {len(raw_data)}")
        return cls(mod_idx=raw_data[0], mod_percent=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack OpenTherm modulation data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.mod_idx, self.mod_percent])


@register_payload("3221")
@dataclass(frozen=True, slots=True)
class OpenthermFrameExPayload(PayloadBase):
    """OpenTherm extended frame payload (Opcode 3221).

    2-byte OpenTherm Frame Ex binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Frame Code (uint8)           : 00
      +1       B      1B   Frame Flags (uint8)          : 00
      --------------------------------------------------------------
      Field-spaced hex : 00 00
      Payload hex      : 0000

    :param frame_code: Frame code byte.
    :type frame_code: int
    :param flags: Frame flags byte.
    :type flags: int
    """

    frame_code: int
    flags: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack OpenTherm extended frame binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked OpenthermFrameExPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 3221: {len(raw_data)}")
        return cls(frame_code=raw_data[0], flags=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack OpenTherm extended frame data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.frame_code, self.flags])


@register_payload("3223")
@dataclass(frozen=True, slots=True)
class OpenthermBridgeStatusPayload(PayloadBase):
    """OpenTherm bridge operational status payload (Opcode 3223).

    2-byte OpenTherm Bridge Status binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Bridge Status Code (uint8)   : 00
      +1       B      1B   Bridge Flags (uint8)         : 00
      --------------------------------------------------------------
      Field-spaced hex : 00 00
      Payload hex      : 0000

    :param status_code: Bridge status code integer.
    :type status_code: int
    :param flags: Bridge flags byte.
    :type flags: int
    """

    status_code: int
    flags: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack OpenTherm bridge status binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked OpenthermBridgeStatusPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 3223: {len(raw_data)}")
        return cls(status_code=raw_data[0], flags=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack OpenTherm bridge status data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.status_code, self.flags])
