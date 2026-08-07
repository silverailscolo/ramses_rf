"""RAMSES RF - System, Clock and Binding payload dataclasses.

This module contains strongly-typed dataclass representations for system clock,
device binding, fault log, and gateway heartbeat packet payloads.
"""

from dataclasses import dataclass
from typing import Self

from .base import PayloadBase
from .registry import register_payload


@register_payload("0001")
@dataclass(frozen=True, slots=True)
class SystemClockPayload(PayloadBase):
    """System clock payload (Opcode 0001).

    5-byte System Clock binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Header / Domain (uint8)      : 00
      +1       B      1B   Hour (uint8, 0-23)           : 0C (12 hours)
      +2       B      1B   Minute (uint8, 0-59)         : 1E (30 mins)
      +3       B      1B   Second (uint8, 0-59)         : 00 (0 secs)
      +4       B      1B   Day of Week (uint8, 1-7)     : 01 (Monday)
      --------------------------------------------------------------
      Field-spaced hex : 00 0C 1E 00 01
      Payload hex      : 000C1E0001

    :param hour: Hour integer (0-23).
    :type hour: int
    :param minute: Minute integer (0-59).
    :type minute: int
    :param second: Second integer (0-59).
    :type second: int
    :param day_of_week: Day of week integer (1-7).
    :type day_of_week: int
    """

    hour: int
    minute: int
    second: int
    day_of_week: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack system clock binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemClockPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 5 bytes.
        """
        if len(raw_data) < 5:
            raise ValueError(f"Invalid payload length for 0001: {len(raw_data)}")
        return cls(
            hour=raw_data[1],
            minute=raw_data[2],
            second=raw_data[3],
            day_of_week=raw_data[4],
        )

    def to_bytes(self) -> bytes:
        """Pack system clock data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([0, self.hour, self.minute, self.second, self.day_of_week])


@register_payload("0002")
@dataclass(frozen=True, slots=True)
class SystemDatePayload(PayloadBase):
    """System date payload (Opcode 0002).

    4-byte System Date binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Header / Domain              : 00
      +1       B      1B   Year (uint8, YY past 2000)   : 1A (2026)
      +2       B      1B   Month (uint8, 1-12)          : 08 (August)
      +3       B      1B   Day (uint8, 1-31)            : 07 (7th)
      --------------------------------------------------------------
      Field-spaced hex : 00 1A 08 07
      Payload hex      : 001A0807

    :param year: Year past 2000 integer.
    :type year: int
    :param month: Month integer (1-12).
    :type month: int
    :param day: Day integer (1-31).
    :type day: int
    """

    year: int
    month: int
    day: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack system date binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemDatePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 4 bytes.
        """
        if len(raw_data) < 4:
            raise ValueError(f"Invalid payload length for 0002: {len(raw_data)}")
        return cls(year=raw_data[1], month=raw_data[2], day=raw_data[3])

    def to_bytes(self) -> bytes:
        """Pack system date data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([0, self.year, self.month, self.day])


@register_payload("0006")
@dataclass(frozen=True, slots=True)
class SystemChangeCounterPayload(PayloadBase):
    """System change counter payload (Opcode 0006).

    3-byte System Change Counter binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Header / Domain              : 00
      +1       H      2B   Change Counter (uint16)      : 00 01 (1 change)
      --------------------------------------------------------------
      Field-spaced hex : 00 0001
      Payload hex      : 000001

    :param change_counter: System configuration change counter value.
    :type change_counter: int
    """

    change_counter: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack system change counter binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemChangeCounterPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 3 bytes.
        """
        if len(raw_data) < 3:
            raise ValueError(f"Invalid payload length for 0006: {len(raw_data)}")
        val = int.from_bytes(raw_data[1:3], byteorder="big", signed=False)
        return cls(change_counter=val)

    def to_bytes(self) -> bytes:
        """Pack system change counter data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([0]) + self.change_counter.to_bytes(
            2, byteorder="big", signed=False
        )


@register_payload("000E")
@dataclass(frozen=True, slots=True)
class SystemRolePayload(PayloadBase):
    """System role assignment payload (Opcode 000E).

    2-byte System Role binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Domain Index (uint8)         : 00
      +1       B      1B   Role Code (uint8)            : 01
      --------------------------------------------------------------
      Field-spaced hex : 00 01
      Payload hex      : 0001

    :param domain_idx: System domain index byte.
    :type domain_idx: int
    :param role_code: Device role classification code byte.
    :type role_code: int
    """

    domain_idx: int
    role_code: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack system role binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemRolePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 000E: {len(raw_data)}")
        return cls(domain_idx=raw_data[0], role_code=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack system role data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.domain_idx, self.role_code])


@register_payload("0016")
@dataclass(frozen=True, slots=True)
class SystemFlagPayload(PayloadBase):
    """System status flags payload (Opcode 0016).

    2-byte System Flag binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Domain Index (uint8)         : 00
      +1       B      1B   Flag Value (uint8)           : 01
      --------------------------------------------------------------
      Field-spaced hex : 00 01
      Payload hex      : 0001

    :param domain_idx: System domain index byte.
    :type domain_idx: int
    :param flag_val: System flag byte value.
    :type flag_val: int
    """

    domain_idx: int
    flag_val: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack system flag binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemFlagPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 0016: {len(raw_data)}")
        return cls(domain_idx=raw_data[0], flag_val=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack system flag data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.domain_idx, self.flag_val])


@register_payload("0100")
@dataclass(frozen=True, slots=True)
class SystemLanguagePayload(PayloadBase):
    """System language and display configuration payload (Opcode 0100).

    2-byte Language binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Header / Domain              : 00
      +1       B      1B   Language Code (0=EN, 1=NL)   : 00
      --------------------------------------------------------------
      Field-spaced hex : 00 00
      Payload hex      : 0000

    :param language_code: Language identification code byte.
    :type language_code: int
    """

    language_code: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack system language binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemLanguagePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 0100: {len(raw_data)}")
        return cls(language_code=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack system language data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([0, self.language_code])


@register_payload("01D0")
@dataclass(frozen=True, slots=True)
class SystemParameterPayload(PayloadBase):
    """System configuration parameter payload (Opcode 01D0).

    2-byte System Parameter binary layout:
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
        """Unpack system parameter binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemParameterPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 01D0: {len(raw_data)}")
        return cls(param_idx=raw_data[0], param_val=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack system parameter data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.param_idx, self.param_val])


@register_payload("01E9")
@dataclass(frozen=True, slots=True)
class SystemFaultPayload(PayloadBase):
    """System fault alert payload (Opcode 01E9).

    2-byte System Fault binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Fault Code (uint8)           : 00
      +1       B      1B   Fault Severity / Flag        : 01
      --------------------------------------------------------------
      Field-spaced hex : 00 01
      Payload hex      : 0001

    :param fault_code: System fault code byte.
    :type fault_code: int
    :param flag_val: Fault flag byte.
    :type flag_val: int
    """

    fault_code: int
    flag_val: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack system fault binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemFaultPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 01E9: {len(raw_data)}")
        return cls(fault_code=raw_data[0], flag_val=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack system fault data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.fault_code, self.flag_val])


@register_payload("0418")
@dataclass(frozen=True, slots=True)
class SystemFaultLogPayload(PayloadBase):
    """System fault log entry payload (Opcode 0418).

    :param log_idx: Fault log index byte.
    :type log_idx: int
    :param log_data: Fault log raw byte sequence.
    :type log_data: bytes
    """

    log_idx: int
    log_data: bytes

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack system fault log binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemFaultLogPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data is empty.
        """
        if not raw_data:
            raise ValueError("Payload data cannot be empty")
        return cls(log_idx=raw_data[0], log_data=raw_data[1:])

    def to_bytes(self) -> bytes:
        """Pack system fault log data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.log_idx]) + self.log_data


@register_payload("042F")
@dataclass(frozen=True, slots=True)
class SystemLogIndexPayload(PayloadBase):
    """System log index payload (Opcode 042F).

    2-byte Log Index binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Log Domain Index (uint8)     : 00
      +1       B      1B   Log Pointer (uint8)          : 01
      --------------------------------------------------------------
      Field-spaced hex : 00 01
      Payload hex      : 0001

    :param domain_idx: Log domain index byte.
    :type domain_idx: int
    :param log_pointer: Current log entry pointer.
    :type log_pointer: int
    """

    domain_idx: int
    log_pointer: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack system log index binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemLogIndexPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 042F: {len(raw_data)}")
        return cls(domain_idx=raw_data[0], log_pointer=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack system log index data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.domain_idx, self.log_pointer])


@register_payload("0B04")
@dataclass(frozen=True, slots=True)
class SystemStatusPayload(PayloadBase):
    """System operational status payload (Opcode 0B04).

    2-byte System Status binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   System State Code (uint8)    : 00
      +1       B      1B   System Flags (uint8)         : 00
      --------------------------------------------------------------
      Field-spaced hex : 00 00
      Payload hex      : 0000

    :param state_code: System operational state code.
    :type state_code: int
    :param flags: System status flags.
    :type flags: int
    """

    state_code: int
    flags: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack system status binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemStatusPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 0B04: {len(raw_data)}")
        return cls(state_code=raw_data[0], flags=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack system status data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.state_code, self.flags])


@register_payload("1060")
@dataclass(frozen=True, slots=True)
class SystemHeatCoolPayload(PayloadBase):
    """System heat/cool operating mode payload (Opcode 1060).

    2-byte System Heat/Cool binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Domain Index (uint8)         : 00
      +1       B      1B   Mode (0=Heat, 1=Cool)        : 00
      --------------------------------------------------------------
      Field-spaced hex : 00 00
      Payload hex      : 0000

    :param domain_idx: System domain index byte.
    :type domain_idx: int
    :param mode: Operating mode (0 for heat, 1 for cool).
    :type mode: int
    """

    domain_idx: int
    mode: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack system heat/cool binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemHeatCoolPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 1060: {len(raw_data)}")
        return cls(domain_idx=raw_data[0], mode=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack system heat/cool data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.domain_idx, self.mode])


@register_payload("10E0")
@register_payload("10E1")
@dataclass(frozen=True, slots=True)
class SystemDeviceInfoPayload(PayloadBase):
    """System device information & firmware payload (Opcode 10E0, 10E1).

    :param info_type: Device info type byte.
    :type info_type: int
    :param info_bytes: Firmware and hardware information raw bytes.
    :type info_bytes: bytes
    """

    info_type: int
    info_bytes: bytes

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack system device info binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemDeviceInfoPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data is empty.
        """
        if not raw_data:
            raise ValueError("Payload data cannot be empty")
        return cls(info_type=raw_data[0], info_bytes=raw_data[1:])

    def to_bytes(self) -> bytes:
        """Pack system device info data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.info_type]) + self.info_bytes


@register_payload("1290")
@dataclass(frozen=True, slots=True)
class SystemOutdoorTempPayload(PayloadBase):
    """System outdoor temperature sensor payload (Opcode 1290).

    2-byte Outdoor Temp binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       h      2B   Outdoor Temperature (int16*100): 05 DC (15.00°C)
      --------------------------------------------------------------
      Field-spaced hex : 05DC
      Payload hex      : 05DC

    :param temperature: Outdoor temperature in °C.
    :type temperature: float
    """

    temperature: float

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack outdoor temperature binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemOutdoorTempPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 1290: {len(raw_data)}")
        temp_raw = int.from_bytes(raw_data[:2], byteorder="big", signed=True)
        return cls(temperature=temp_raw / 100.0)

    def to_bytes(self) -> bytes:
        """Pack outdoor temperature data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        temp_raw = int(round(self.temperature * 100.0))
        return temp_raw.to_bytes(2, byteorder="big", signed=True)


@register_payload("1F09")
@dataclass(frozen=True, slots=True)
class SystemSyncHeartbeatPayload(PayloadBase):
    """System synchronization heartbeat payload (Opcode 1F09).

    1-byte System Sync Heartbeat binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Sync Sequence Flag (uint8)   : 00
      --------------------------------------------------------------
      Field-spaced hex : 00
      Payload hex      : 00

    :param sync_sequence: Synchronization sequence flag.
    :type sync_sequence: int
    """

    sync_sequence: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack system sync heartbeat binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemSyncHeartbeatPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data is empty.
        """
        if not raw_data:
            raise ValueError("Payload data cannot be empty")
        return cls(sync_sequence=raw_data[0])

    def to_bytes(self) -> bytes:
        """Pack system sync heartbeat data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.sync_sequence])


@register_payload("2E04")
@register_payload("2E10")
@dataclass(frozen=True, slots=True)
class SystemConfigPayload(PayloadBase):
    """System configuration parameter payload (Opcode 2E04, 2E10).

    2-byte System Config binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Config Index (uint8)         : 00
      +1       B      1B   Config Value (uint8)         : 00
      --------------------------------------------------------------
      Field-spaced hex : 00 00
      Payload hex      : 0000

    :param config_idx: Configuration index byte.
    :type config_idx: int
    :param config_val: Configuration value byte.
    :type config_val: int
    """

    config_idx: int
    config_val: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack system config binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemConfigPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length: {len(raw_data)}")
        return cls(config_idx=raw_data[0], config_val=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack system config data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.config_idx, self.config_val])


@register_payload("313F")
@dataclass(frozen=True, slots=True)
class SystemActuatorPayload(PayloadBase):
    """System actuator control payload (Opcode 313F).

    2-byte System Actuator binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Actuator Domain (uint8)      : 00
      +1       B      1B   Actuator Value (uint8)       : C8 (200)
      --------------------------------------------------------------
      Field-spaced hex : 00 C8
      Payload hex      : 00C8

    :param domain: Actuator domain byte.
    :type domain: int
    :param actuator_value: Actuator output value byte.
    :type actuator_value: int
    """

    domain: int
    actuator_value: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack system actuator binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemActuatorPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 313F: {len(raw_data)}")
        return cls(domain=raw_data[0], actuator_value=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack system actuator data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.domain, self.actuator_value])


@register_payload("3222")
@dataclass(frozen=True, slots=True)
class SystemOpenthermBridgePayload(PayloadBase):
    """System OpenTherm bridge status payload (Opcode 3222).

    2-byte System OpenTherm Bridge binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Bridge Mode (uint8)          : 00
      +1       B      1B   Bridge Status Flags (uint8)  : 00
      --------------------------------------------------------------
      Field-spaced hex : 00 00
      Payload hex      : 0000

    :param mode: Bridge mode byte.
    :type mode: int
    :param flags: Bridge status flags byte.
    :type flags: int
    """

    mode: int
    flags: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack system OpenTherm bridge binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemOpenthermBridgePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 3222: {len(raw_data)}")
        return cls(mode=raw_data[0], flags=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack system OpenTherm bridge data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.mode, self.flags])


@register_payload("7FFF")
@dataclass(frozen=True, slots=True)
class PuzzlePayload(PayloadBase):
    """Special puzzle / diagnostic payload (Opcode 7FFF).

    :param msg_type: Message type classification byte sequence.
    :type msg_type: bytes
    :param payload_data: Raw diagnostic payload byte sequence.
    :type payload_data: bytes
    """

    msg_type: bytes
    payload_data: bytes

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack puzzle diagnostic binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked PuzzlePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 7FFF: {len(raw_data)}")
        return cls(msg_type=raw_data[:2], payload_data=raw_data[2:])

    def to_bytes(self) -> bytes:
        """Pack puzzle diagnostic data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return self.msg_type + self.payload_data
