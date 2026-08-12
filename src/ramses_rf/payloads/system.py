"""RAMSES RF - System, Clock and Binding payload dataclasses.

This module contains strongly-typed dataclass representations for system clock,
device binding, fault log, and gateway heartbeat packet payloads.
"""

import struct
from dataclasses import dataclass
from typing import Any, ClassVar, Self, cast

from ramses_tx.helpers import hex_from_dtm, hex_to_dtm

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

    Sample Packet Logs & Protocol Notes:
      # Sent by THM when in signal strength test mode (0505, except 1st pkt):
      # 12:39:56.099 061  W --- 12:010740 --:------ 12:010740 0001 005 0000000501
      # 13:48:45.518 074  W --- 12:010740 --:------ 12:010740 0001 005 0000000505
      # Sent by CTL before rf_check:
      # 15:12:47.769 053  W --- 01:145038 --:------ 01:145038 0001 005 FC00000505

    :param hour: Hour integer (0-23).
    :type hour: int
    :param minute: Minute integer (0-59).
    :type minute: int
    :param second: Second integer (0-59).
    :type second: int
    :param day_of_week: Day of week integer (1-7).
    :type day_of_week: int
    """

    _STRUCT_FMT: ClassVar[str] = ">BBBBB"

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
        _hdr, hr, mn, sc, dow = struct.unpack_from(cls._STRUCT_FMT, raw_data, 0)
        return cls(
            hour=hr,
            minute=mn,
            second=sc,
            day_of_week=dow,
        )

    def to_bytes(self) -> bytes:
        """Pack system clock data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return struct.pack(
            self._STRUCT_FMT, 0, self.hour, self.minute, self.second, self.day_of_week
        )


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

    _STRUCT_FMT: ClassVar[str] = ">BBBB"

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
        _hdr, yr, mo, dy = struct.unpack_from(cls._STRUCT_FMT, raw_data, 0)
        return cls(year=yr, month=mo, day=dy)

    def to_bytes(self) -> bytes:
        """Pack system date data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return struct.pack(self._STRUCT_FMT, 0, self.year, self.month, self.day)


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

    _STRUCT_FMT_4B: ClassVar[str] = ">BBH"
    _STRUCT_FMT_3B: ClassVar[str] = ">BH"

    change_counter: int | None = None
    _raw_prefix: bytes = b"\x00\x05"
    _raw_len: int = 2

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
        if raw_data[2:] == b"\xff\xff" or raw_data[1:] == b"\xff\xff\xff":
            val = None
        else:
            val = int.from_bytes(raw_data[2:], byteorder="big", signed=False)
        prefix = raw_data[:2]
        val_len = len(raw_data) - 2
        return cls(
            change_counter=val,
            _raw_prefix=prefix,
            _raw_len=val_len,
        )

    def to_bytes(self) -> bytes:
        """Pack system change counter data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        if self.change_counter is None:
            return b"\x00\x05\xff\xff"
        if self._raw_len == 2:
            p1, p2 = struct.unpack(">BB", self._raw_prefix)
            return struct.pack(self._STRUCT_FMT_4B, p1, p2, self.change_counter)
        return self._raw_prefix + self.change_counter.to_bytes(
            self._raw_len, byteorder="big", signed=False
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert system change counter payload to legacy dictionary layout.

        :returns: Decoded system change counter dictionary.
        :rtype: dict[str, Any]
        """
        return {"change_counter": self.change_counter}


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

    _STRUCT_FMT: ClassVar[str] = ">BB"

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
        dom, role = struct.unpack_from(cls._STRUCT_FMT, raw_data, 0)
        return cls(domain_idx=dom, role_code=role)

    def to_bytes(self) -> bytes:
        """Pack system role data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return struct.pack(self._STRUCT_FMT, self.domain_idx, self.role_code)


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

    _STRUCT_FMT: ClassVar[str] = ">BB"

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
        dom, flg = struct.unpack_from(cls._STRUCT_FMT, raw_data, 0)
        return cls(domain_idx=dom, flag_val=flg)

    def to_bytes(self) -> bytes:
        """Pack system flag data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return struct.pack(self._STRUCT_FMT, self.domain_idx, self.flag_val)


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

    _STRUCT_FMT_2B: ClassVar[str] = ">BB"

    language: str | None = None

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
        if len(raw_data) >= 3:
            lang = raw_data[1:3].decode("latin-1", errors="ignore")
        else:
            _hdr, l_code = struct.unpack_from(cls._STRUCT_FMT_2B, raw_data, 0)
            lang = f"{l_code:02x}"
        return cls(language=lang)

    def to_bytes(self) -> bytes:
        """Pack system language data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        if not self.language:
            return b"\x00\x00"
        return b"\x00" + self.language.encode("latin-1")

    def to_dict(self) -> dict[str, Any]:
        """Convert system language payload to legacy dictionary layout.

        :returns: Decoded system language dictionary.
        :rtype: dict[str, Any]
        """
        return {"language": self.language}


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

    _STRUCT_FMT: ClassVar[str] = ">BB"

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
        idx, val = struct.unpack_from(cls._STRUCT_FMT, raw_data, 0)
        return cls(param_idx=idx, param_val=val)

    def to_bytes(self) -> bytes:
        """Pack system parameter data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return struct.pack(self._STRUCT_FMT, self.param_idx, self.param_val)


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

    _STRUCT_FMT: ClassVar[str] = ">BB"

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
        code, flg = struct.unpack_from(cls._STRUCT_FMT, raw_data, 0)
        return cls(fault_code=code, flag_val=flg)

    def to_bytes(self) -> bytes:
        """Pack system fault data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return struct.pack(self._STRUCT_FMT, self.fault_code, self.flag_val)


@register_payload("0418")
@dataclass(frozen=True, slots=True)
class SystemFaultLogPayload(PayloadBase):
    """System fault log entry payload (Opcode 0418).

    Variable-length System Fault Log binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Log Index (uint8)            : 00
      +1       xB     vB   Fault Log Data Bytes         : 00 01 00 00
      --------------------------------------------------------------
      Field-spaced hex : 00 00010000
      Payload hex      : 0000010000

    :param log_idx: Fault log index byte.
    :type log_idx: int
    :param log_data: Fault log raw byte sequence.
    :type log_data: bytes
    """

    _STRUCT_FMT_HEADER: ClassVar[str] = ">B"

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
        (idx,) = struct.unpack_from(cls._STRUCT_FMT_HEADER, raw_data, 0)
        return cls(log_idx=idx, log_data=raw_data[1:])

    def to_bytes(self) -> bytes:
        """Pack system fault log data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return struct.pack(self._STRUCT_FMT_HEADER, self.log_idx) + self.log_data

    def to_dict(self, msg: Any = None) -> dict[str, Any]:
        """Convert fault log payload to legacy dictionary layout.

        :param msg: Optional message context object.
        :type msg: Any
        :returns: Decoded fault log dictionary.
        :rtype: dict[str, Any]
        """
        from ramses_rf.parsers.system import parser_0418

        verb = getattr(msg, "verb", " I") if msg is not None else " I"
        dummy_msg = type("DummyMsg", (), {"verb": verb})()

        idx_str = f"{self.log_idx:02X}"
        raw_hex = (bytes([self.log_idx]) + self.log_data).hex().upper()
        try:
            parsed = parser_0418(raw_hex, dummy_msg)
            if isinstance(parsed, dict):
                res: dict[str, Any] = dict(parsed)
                if "log_idx" not in res:
                    res["log_idx"] = idx_str
                return res
        except Exception:
            pass
        return {"log_idx": idx_str, "log_entry": None}


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

    _STRUCT_FMT: ClassVar[str] = ">BB"

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
        dom, ptr = struct.unpack_from(cls._STRUCT_FMT, raw_data, 0)
        return cls(domain_idx=dom, log_pointer=ptr)

    def to_bytes(self) -> bytes:
        """Pack system log index data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return struct.pack(self._STRUCT_FMT, self.domain_idx, self.log_pointer)


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

    _STRUCT_FMT: ClassVar[str] = ">BB"

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
        code, flg = struct.unpack_from(cls._STRUCT_FMT, raw_data, 0)
        return cls(state_code=code, flags=flg)

    def to_bytes(self) -> bytes:
        """Pack system status data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return struct.pack(self._STRUCT_FMT, self.state_code, self.flags)


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

    _STRUCT_FMT: ClassVar[str] = ">BB"

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
        dom, md = struct.unpack_from(cls._STRUCT_FMT, raw_data, 0)
        return cls(domain_idx=dom, mode=md)

    def to_bytes(self) -> bytes:
        """Pack system heat/cool data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return struct.pack(self._STRUCT_FMT, self.domain_idx, self.mode)


@register_payload("10E0")
@register_payload("10E1")
@dataclass(frozen=True, slots=True)
class SystemDeviceInfoPayload(PayloadBase):
    """System device information & firmware payload (Opcode 10E0, 10E1).

    Variable-length System Device Info binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Info Type Code (uint8)       : 00
      +1       xB     vB   Hardware/Firmware Info Bytes : 01 02 03
      --------------------------------------------------------------
      Field-spaced hex : 00 010203
      Payload hex      : 00010203

    :param info_type: Device info type byte.
    :type info_type: int
    :param info_bytes: Firmware and hardware information raw bytes.
    :type info_bytes: bytes
    """

    _STRUCT_FMT_HEADER: ClassVar[str] = ">B"

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
        (i_type,) = struct.unpack_from(cls._STRUCT_FMT_HEADER, raw_data, 0)
        return cls(info_type=i_type, info_bytes=raw_data[1:])

    def to_bytes(self) -> bytes:
        """Pack system device info data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return struct.pack(self._STRUCT_FMT_HEADER, self.info_type) + self.info_bytes

    def to_dict(self) -> dict[str, Any]:
        """Convert device info payload to legacy dictionary layout.

        :returns: Decoded device info dictionary.
        :rtype: dict[str, Any]
        """
        import re

        from ramses_tx.helpers import hex_to_date

        raw_payload = bytes([self.info_type]) + self.info_bytes
        hex_str = raw_payload.hex().upper()
        if hex_str == "00":
            return {}
        hex_str = re.sub("(00)*$", "", hex_str)
        if len(hex_str) < 36:
            return {"info_type": self.info_type, "info_bytes": self.info_bytes}
        desc_hex, _, _ = hex_str[36:].partition("00")
        if len(desc_hex) % 2 != 0:
            desc_hex += "0"
        try:
            desc = bytearray.fromhex(desc_hex).decode()
        except Exception:
            desc = ""
        return {
            "oem_code": hex_str[14:16],
            "manufacturer_sub_id": hex_str[6:8],
            "product_id": hex_str[8:10],
            "date_1": hex_to_date(hex_str[28:36]) or "0000-00-00",
            "date_2": hex_to_date(hex_str[20:28]) or "0000-00-00",
            "description": desc,
        }


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

    :param outdoor_temp: Outdoor temperature in °C, or None if invalid.
    :type outdoor_temp: float | None
    """

    _STRUCT_FMT: ClassVar[str] = ">h"

    outdoor_temp: float | None

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
        buf = raw_data[1:3] if len(raw_data) >= 3 else raw_data[0:2]
        if buf in (b"\x7f\xff", b"\x31\xff", b"\x7f\x7f"):
            return cls(outdoor_temp=None)
        (temp_raw,) = struct.unpack_from(cls._STRUCT_FMT, buf, 0)
        return cls(outdoor_temp=temp_raw / 100.0)

    def to_bytes(self) -> bytes:
        """Pack outdoor temperature data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        temp_raw = (
            0x7FFF
            if self.outdoor_temp is None
            else int(round(self.outdoor_temp * 100.0))
        )
        return struct.pack(self._STRUCT_FMT, temp_raw)

    def to_dict(self) -> dict[str, Any]:
        """Convert outdoor temperature payload to legacy dictionary layout.

        :returns: Decoded outdoor temperature dictionary.
        :rtype: dict[str, Any]
        """
        return {"outdoor_temp": self.outdoor_temp}


@register_payload("1F09")
@dataclass(frozen=True, slots=True)
class SystemSyncHeartbeatPayload(PayloadBase):
    """System synchronization heartbeat payload (Opcode 1F09).

    1-byte or 3-byte System Sync Heartbeat binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Sync Sequence Flag (uint8)   : 00
      +1       H      2B   Remaining Seconds (uint16*10): 05 14 (130.0s)
      --------------------------------------------------------------
      Field-spaced hex : 00 0514
      Payload hex      : 000514

    :param sync_sequence: Synchronization sequence flag.
    :type sync_sequence: int
    :param remaining_seconds: Remaining synchronization seconds, or None.
    :type remaining_seconds: float | None
    """

    _STRUCT_FMT_3B: ClassVar[str] = ">BH"
    _STRUCT_FMT_1B: ClassVar[str] = ">B"

    sync_sequence: int
    remaining_seconds: float | None = None

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
        if len(raw_data) >= 3:
            seq, secs_raw = struct.unpack_from(cls._STRUCT_FMT_3B, raw_data, 0)
            return cls(sync_sequence=seq, remaining_seconds=secs_raw / 10.0)
        (seq,) = struct.unpack_from(cls._STRUCT_FMT_1B, raw_data, 0)
        return cls(sync_sequence=seq)

    def to_bytes(self) -> bytes:
        """Pack system sync heartbeat data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        if self.remaining_seconds is not None:
            secs_raw = int(round(self.remaining_seconds * 10.0))
            return struct.pack(self._STRUCT_FMT_3B, self.sync_sequence, secs_raw)
        return struct.pack(self._STRUCT_FMT_1B, self.sync_sequence)

    def to_dict(self) -> dict[str, Any]:
        """Convert system sync heartbeat payload to legacy dictionary layout.

        :returns: Decoded system sync dictionary.
        :rtype: dict[str, Any]
        """
        if self.remaining_seconds is not None:
            return {"remaining_seconds": self.remaining_seconds}
        return {"sync_sequence": self.sync_sequence}


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

    _STRUCT_FMT_2B: ClassVar[str] = ">BB"

    config_idx: int
    config_val: int
    _raw_extra: bytes | None = None

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
        c_idx, c_val = struct.unpack_from(cls._STRUCT_FMT_2B, raw_data, 0)
        extra = raw_data[2:] if len(raw_data) > 2 else None
        return cls(config_idx=c_idx, config_val=c_val, _raw_extra=extra)

    def to_bytes(self) -> bytes:
        """Pack system config data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return struct.pack(self._STRUCT_FMT_2B, self.config_idx, self.config_val) + (
            self._raw_extra or b""
        )

    def to_dict(self, msg: Any = None) -> dict[str, Any]:
        """Convert system config payload to legacy dictionary layout.

        :param msg: Optional message context object.
        :type msg: Any
        :returns: Decoded system config dictionary.
        :rtype: dict[str, Any]
        """
        from ramses_rf.const import SYS_MODE_MAP

        mode_code = f"{self.config_idx:02X}"
        if mode_code in SYS_MODE_MAP:
            from ramses_rf.parsers.system import parser_2e04

            full_bytes = self.to_bytes()
            verb = getattr(msg, "verb", " I") if msg is not None else " I"
            dummy_msg = type("DummyMsg", (), {"verb": verb, "len": len(full_bytes)})()
            try:
                parsed = parser_2e04(full_bytes.hex().upper(), dummy_msg)
                if isinstance(parsed, dict):
                    return cast(dict[str, Any], parsed)
            except Exception:
                pass

            if mode_code in (
                SYS_MODE_MAP.AUTO,
                SYS_MODE_MAP.HEAT_OFF,
                SYS_MODE_MAP.AUTO_WITH_RESET,
            ):
                return {"system_mode": SYS_MODE_MAP[mode_code]}
            return {"system_mode": SYS_MODE_MAP[mode_code], "until": None}

        return {"config_idx": self.config_idx, "config_val": self.config_val}


@register_payload("313F")
@dataclass(frozen=True, slots=True)
class SystemDateTimePayload(PayloadBase):
    """System date and time payload (Opcode 313F).

    9-byte System Date & Time binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Domain / Header Index        : 00
      +1       B      1B   Sub-index / Flags            : F0
      +2       B      1B   Year | DST flag (0x80)       : 96 (22 | 0x80)
      +3       B      1B   Month (1-12)                 : 05
      +4       B      1B   Day (1-31)                   : 02
      +5       B      1B   Hours (0-23)                 : 0A (10)
      +6       B      1B   Minutes (0-59)               : 02
      +7       B      1B   Seconds (0-59)               : 36 (54)
      +8       B      1B   Padding / Reserved           : 00
      --------------------------------------------------------------
      Field-spaced hex : 00 F0 96 05 02 0A 02 36 00
      Payload hex      : 00F09605020A023600


    :param domain_idx: Domain/header index byte.
    :type domain_idx: str | int | None
    :param datetime_str: Formatted ISO datetime string (e.g., '2022-05-02T10:02:54').
    :type datetime_str: str | None
    :param is_dst: Daylight Saving Time active flag.
    :type is_dst: bool | None
    """

    _STRUCT_FMT_HEADER: ClassVar[str] = ">B"

    domain_idx: int
    datetime_str: str | None = None
    is_dst: bool | None = None

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack system date & time binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemDateTimePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 313F: {len(raw_data)}")

        (dom,) = struct.unpack_from(cls._STRUCT_FMT_HEADER, raw_data, 0)
        if len(raw_data) >= 9:
            hex_str = raw_data[2:9].hex().upper()
            dt_str = hex_to_dtm(hex_str)
            dst_flag = True if bool(raw_data[2] & 0x80) else None
            return cls(
                domain_idx=dom,
                datetime_str=dt_str,
                is_dst=dst_flag,
            )
        return cls(domain_idx=dom)

    def to_bytes(self) -> bytes:
        """Pack system date & time data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        if self.datetime_str is not None:
            dt_hex = hex_from_dtm(
                self.datetime_str, is_dst=self.is_dst or False, incl_seconds=True
            )
            return (
                struct.pack(self._STRUCT_FMT_HEADER, self.domain_idx)
                + b"\xf0"
                + bytes.fromhex(dt_hex)
            )
        return struct.pack(self._STRUCT_FMT_HEADER, self.domain_idx) + b"\x00"

    def to_dict(self) -> dict[str, Any]:
        """Convert system date & time payload to legacy dictionary layout.

        :returns: Decoded system date & time dictionary.
        :rtype: dict[str, Any]
        """
        res: dict[str, Any] = {}
        if self.datetime_str is not None:
            res["datetime"] = self.datetime_str
        if self.is_dst is not None:
            res["is_dst"] = self.is_dst
        return res


@dataclass(frozen=True, slots=True)
class SystemActuatorPayload(PayloadBase):
    """System actuator control payload.

    :param domain: Actuator domain byte.
    :type domain: int
    :param actuator_value: Actuator output value byte.
    :type actuator_value: int
    """

    _STRUCT_FMT: ClassVar[str] = ">BB"

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
            raise ValueError(f"Invalid payload length: {len(raw_data)}")
        dom, val = struct.unpack_from(cls._STRUCT_FMT, raw_data, 0)
        return cls(domain=dom, actuator_value=val)

    def to_bytes(self) -> bytes:
        """Pack system actuator data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return struct.pack(self._STRUCT_FMT, self.domain, self.actuator_value)


@register_payload("3222")
@dataclass(frozen=True, slots=True)
class SystemOpenThermBridgePayload(PayloadBase):
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

    _STRUCT_FMT: ClassVar[str] = ">BB"

    mode: int
    flags: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack system OpenTherm bridge binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemOpenThermBridgePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 3222: {len(raw_data)}")
        md, flg = struct.unpack_from(cls._STRUCT_FMT, raw_data, 0)
        return cls(mode=md, flags=flg)

    def to_bytes(self) -> bytes:
        """Pack system OpenTherm bridge data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return struct.pack(self._STRUCT_FMT, self.mode, self.flags)


@register_payload("7FFF")
@dataclass(frozen=True, slots=True)
class PuzzlePayload(PayloadBase):
    """Special puzzle / diagnostic payload (Opcode 7FFF).

    Variable-length Puzzle Diagnostic binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       2B     2B   Message Type Classification  : 00 01
      +2       xB     vB   Diagnostic Payload Bytes     : 00 FF
      --------------------------------------------------------------
      Field-spaced hex : 0001 00FF
      Payload hex      : 000100FF

    :param msg_type: Message type classification byte sequence.
    :type msg_type: bytes
    :param payload_data: Raw diagnostic payload byte sequence.
    :type payload_data: bytes
    """

    _STRUCT_FMT_HEADER: ClassVar[str] = ">2s"

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
        (m_type,) = struct.unpack_from(cls._STRUCT_FMT_HEADER, raw_data, 0)
        return cls(msg_type=m_type, payload_data=raw_data[2:])

    def to_bytes(self) -> bytes:
        """Pack puzzle diagnostic data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return struct.pack(self._STRUCT_FMT_HEADER, self.msg_type) + self.payload_data


@register_payload("0009")
@dataclass(frozen=True, slots=True)
class RelayFailsafePayload(PayloadBase):
    """Relay failsafe mode payload (Opcode 0009).

    2-byte Relay Failsafe binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Domain / Zone Index (uint8)  : 00
      +1       B      1B   Failsafe Enabled (0=No, 1=Yes): 01
      --------------------------------------------------------------
      Field-spaced hex : 00 01
      Payload hex      : 0001

    Sample Packet Logs:
      # .I --- 01:145038 --:------ 01:145038 0009 006 FC01FFF901FF
      # .I --- 01:145038 --:------ 01:145038 0009 003 0700FF
      # .I --- 23:100224 --:------ 23:100224 0009 003 0100FF  # 2-zone ST9520C
      # .I --- 10:040239 01:223036 --:------ 0009 003 000000
      # .I --- --:------ --:------ 12:227486 0009 003 0000FF

    :param domain_or_zone_idx: Domain or zone index byte.
    :type domain_or_zone_idx: int
    :param failsafe_enabled: Failsafe status flag boolean.
    :type failsafe_enabled: bool
    """

    _STRUCT_FMT: ClassVar[str] = ">BB"

    domain_or_zone_idx: int
    failsafe_enabled: bool

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack relay failsafe binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked RelayFailsafePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 0009: {len(raw_data)}")
        idx, flg = struct.unpack_from(cls._STRUCT_FMT, raw_data, 0)
        return cls(
            domain_or_zone_idx=idx,
            failsafe_enabled=bool(flg),
        )

    def to_bytes(self) -> bytes:
        """Pack relay failsafe data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return struct.pack(
            self._STRUCT_FMT, self.domain_or_zone_idx, int(self.failsafe_enabled)
        )


@register_payload("0204")
@dataclass(frozen=True, slots=True)
class SystemFrame0204Payload(PayloadBase):
    """System frame payload (Opcode 0204).

    Variable-length System Frame binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       xB     vB   Raw Payload Byte Sequence    : 00 01 02 03
      --------------------------------------------------------------
      Field-spaced hex : 00010203
      Payload hex      : 00010203

    :param raw_payload_bytes: Raw payload byte string.
    :type raw_payload_bytes: bytes
    """

    raw_payload_bytes: bytes

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack system frame 0204 binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemFrame0204Payload instance.
        :rtype: Self
        """
        return cls(raw_payload_bytes=raw_data)

    def to_bytes(self) -> bytes:
        """Pack system frame 0204 data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return self.raw_payload_bytes
