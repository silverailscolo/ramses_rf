"""RAMSES RF - Heating and Evohome payload dataclasses.

This module contains strongly-typed dataclass representations for CH / Evohome
packet payloads.
"""

import struct
from dataclasses import dataclass
from datetime import datetime as dt
from typing import ClassVar, Self

from ramses_tx.helpers import hex_from_dtm

from .base import PayloadBase, parse_idx
from .dhw import DhwParamsPayload
from .registry import register_payload


@register_payload("3150")
@dataclass(frozen=True, slots=True)
class HeatDemandPayload(PayloadBase):
    """Heat demand payload (Opcode 3150).

    2-byte Heat Demand binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Zone Index / Domain (uint8)  : 00
      +1       B      1B   Heat demand percentage (uint8) : C8 (200)
      --------------------------------------------------------------
      Field-spaced hex : 00 C8
      Payload hex      : 00C8

    Protocol & Reassembly Notes:
      # 3150 (Actuator State) and 12B0 (Window Open) carry real zone_idx.
      # 3150 single heat-demand broadcasts are routinely emitted un-fragmented.
      # Sample Packet Logs:
      # .I --- 04:136513 --:------ 01:158182 3150 002 01CA
      # .I --- 02:000921 --:------ 01:191718 3150 002 0360

    :param demand_percent: Heat demand value (0-200, where 200 = 100%).
    :type demand_percent: int
    """

    domain_or_zone_idx: int | None
    demand_percent: int
    raw_extra: bytes | None = None

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack a 1-byte, 2-byte, or multi-byte heat demand payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked HeatDemandPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data is empty.
        """
        if not raw_data:
            raise ValueError("Payload data cannot be empty")
        if len(raw_data) == 1:
            return cls(domain_or_zone_idx=None, demand_percent=raw_data[0])
        extra = raw_data[2:] if len(raw_data) > 2 else None
        return cls(
            domain_or_zone_idx=raw_data[0],
            demand_percent=raw_data[1],
            raw_extra=extra,
        )

    def to_bytes(self) -> bytes:
        """Pack heat demand data into a binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        if self.domain_or_zone_idx is not None:
            buf = bytes([self.domain_or_zone_idx, self.demand_percent & 0xFF])
        else:
            buf = bytes([self.demand_percent & 0xFF])
        if self.raw_extra:
            buf += self.raw_extra
        return buf


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

    zone_idx: int | str | None
    temperature: float | bool | None

    def __post_init__(self) -> None:
        """Normalise index arguments."""
        if isinstance(self.zone_idx, str):
            object.__setattr__(self, "zone_idx", parse_idx(self.zone_idx))

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
            idx = parse_idx(self.zone_idx)
            return bytes([idx]) + temp_bytes
        return temp_bytes


@dataclass(frozen=True, slots=True)
class ScheduleFragmentPayload(PayloadBase):
    """Schedule fragment payload (Opcode 0404 fragment).

    Multi-byte schedule fragment binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Zone Index / Domain (uint8)  : 01
      +1       B      1B   Fragment Flags               : 20
      +2       H      2B   Padding                      : 00 00
      +4       B      1B   Fragment Length / Header     : 08
      +5       B      1B   Fragment Number (uint8)      : 01
      +6       B      1B   Total Fragments (uint8)      : 03
      +7       bytes  var  Fragment switchpoint bytes   : 68 81 ...
      --------------------------------------------------------------

    :param zone_idx: Zone/domain index byte.
    :type zone_idx: int
    :param frag_number: Fragment index number (1-based).
    :type frag_number: int
    :param total_frags: Total fragment count for schedule transfer.
    :type total_frags: int
    :param fragment_bytes: Raw binary fragment data bytes.
    :type fragment_bytes: bytes
    """

    zone_idx: int | str
    frag_number: int
    total_frags: int
    fragment_bytes: bytes
    _header_prefix: bytes | None = None

    def __post_init__(self) -> None:
        """Normalise index arguments."""
        if isinstance(self.zone_idx, str):
            object.__setattr__(self, "zone_idx", parse_idx(self.zone_idx))

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack schedule fragment binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked ScheduleFragmentPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 7 bytes.
        """
        if len(raw_data) < 7:
            raise ValueError(
                f"Invalid fragment payload length for 0404: {len(raw_data)}"
            )
        prefix = raw_data[1:4]
        zone_idx: int | str = (
            "HW" if raw_data[0] == 0 and prefix == b"\x23\x00\x08" else raw_data[0]
        )
        return cls(
            zone_idx=zone_idx,
            frag_number=raw_data[5],
            total_frags=raw_data[6],
            fragment_bytes=raw_data[7:],
            _header_prefix=prefix,
        )

    def to_bytes(self) -> bytes:
        """Pack schedule fragment data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        idx = parse_idx(self.zone_idx)
        prefix = (
            self._header_prefix
            if self._header_prefix is not None
            else (b"\x23\x00\x08" if idx == 0xFA else b"\x20\x00\x08")
        )
        byte_idx = 0x00 if prefix == b"\x23\x00\x08" and idx == 0xFA else idx
        hdr = (
            bytes([byte_idx])
            + prefix
            + bytes(
                [
                    len(self.fragment_bytes),
                    self.frag_number,
                    self.total_frags,
                ]
            )
        )
        return hdr + self.fragment_bytes


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
    def from_bytes(cls, raw_data: bytes) -> Self | ScheduleFragmentPayload:
        """Unpack a compressed 20-byte schedule switchpoint or fragment.

        :param raw_data: Raw schedule binary block.
        :type raw_data: bytes
        :returns: ScheduleSwitchpointPayload or ScheduleFragmentPayload instance.
        :rtype: Self | ScheduleFragmentPayload
        :raises ValueError: If raw_data length is invalid.
        """
        if len(raw_data) > 20:
            return ScheduleFragmentPayload.from_bytes(raw_data)
        if len(raw_data) != 20:
            raise ValueError(f"Invalid payload length for 0404: {len(raw_data)}")
        idx, dow, tod, val, _ = struct.unpack(cls._STRUCT_FMT, raw_data)
        return cls(
            zone_idx=idx,
            day_of_week=dow,
            time_of_day_mins=tod,
            setpoint_value=val,
        )

    @classmethod
    def from_switchpoint(
        cls,
        zone_idx: int | str,
        day_of_week: int,
        time_of_day_mins: int,
        setpoint: float | bool | None,
    ) -> Self:
        """Create a ScheduleSwitchpointPayload from switchpoint domain values.

        :param zone_idx: Zone or domain index byte or string.
        :type zone_idx: int | str
        :param day_of_week: Day of week integer (0-6).
        :type day_of_week: int
        :param time_of_day_mins: Time of day in minutes.
        :type time_of_day_mins: int
        :param setpoint: Temperature setpoint float, boolean state, or None.
        :type setpoint: float | bool | None
        :returns: A populated ScheduleSwitchpointPayload instance.
        :rtype: Self
        """
        idx = parse_idx(zone_idx)
        if isinstance(setpoint, bool):
            value = int(setpoint)
        elif isinstance(setpoint, (int, float)):
            value = int(setpoint * 100)
        else:
            value = 0
        return cls(
            zone_idx=idx,
            day_of_week=day_of_week,
            time_of_day_mins=time_of_day_mins,
            setpoint_value=value,
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

    Sample Packet Logs:
      # RQ --- 07:045960 01:145038 --:------ 10A0 006 00-1087-00-03E4  # RQ/RP, every 24h
      # RP --- 01:145038 07:045960 --:------ 10A0 006 00-109A-00-03E8
      # RP --- 10:048122 18:006402 --:------ 10A0 003 00-1B58
      # RQ --- 07:036831 23:100224 --:------ 10A0 006 01-1566-00-03E4  # non-evohome

    :param dhw_idx: Optional DHW index byte, or None.
    :type dhw_idx: int | None
    :param temperature: DHW temperature in °C, False if disabled, or None.
    :type temperature: float | bool | None
    """

    dhw_idx: int | str | None
    temperature: float | bool | None

    def __post_init__(self) -> None:
        """Normalise index arguments."""
        if isinstance(self.dhw_idx, str):
            object.__setattr__(self, "dhw_idx", parse_idx(self.dhw_idx))

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self | DhwParamsPayload:
        """Unpack DHW temperature or parameters binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked DhwTemperaturePayload or DhwParamsPayload instance.
        :rtype: Self | DhwParamsPayload
        :raises ValueError: If raw_data length is invalid.
        """
        if len(raw_data) >= 6:
            return DhwParamsPayload.from_bytes(raw_data)
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
            idx = parse_idx(self.dhw_idx)
            return bytes([idx]) + temp_bytes
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

    Sample Packet Logs & Parameter Map:
      # .I --- 01:145038 --:------ 01:145038 1030 016 0A-C80137-C9010F-CA0196-CB0100
      # .I --- --:------ --:------ 12:144017 1030 016 01-C80137-C9010F-CA0196-CB010F
      # RP --- 32:155617 18:005904 --:------ 1030 007 00-200100-21011F
      # Parameter IDs:
      #   C8: max_flow_setpoint (default 55, range 0-99 °C)
      #   C9: min_flow_setpoint (default 15, range 0-50 °C)
      #   CA: valve_run_time (default 150, range 0-240 sec, aka actuator_run_time)
      #   CB: pump_run_time (default 15, range 0-99 sec)

    :param sync_flag: System synchronization counter or status byte.
    :type sync_flag: int
    :param max_flow_setpoint: Maximum flow setpoint temperature in °C (Parameter C8), or None.
    :type max_flow_setpoint: int | None
    :param min_flow_setpoint: Minimum flow setpoint temperature in °C (Parameter C9), or None.
    :type min_flow_setpoint: int | None
    :param valve_run_time: Valve run time in seconds (Parameter CA), or None.
    :type valve_run_time: int | None
    :param pump_run_time: Pump run time in seconds (Parameter CB), or None.
    :type pump_run_time: int | None
    :param raw_extra: Optional raw payload bytes beyond sync_flag.
    :type raw_extra: bytes | None
    """

    sync_flag: int
    max_flow_setpoint: int | None = None
    min_flow_setpoint: int | None = None
    valve_run_time: int | None = None
    pump_run_time: int | None = None
    raw_extra: bytes | None = None

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack system sync / mixvalve config binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemSyncPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data is empty.
        """
        if not raw_data:
            raise ValueError("Payload data cannot be empty")

        max_flow = None
        min_flow = None
        v_time = None
        p_time = None
        extra = raw_data[1:] if len(raw_data) > 1 else None

        if len(raw_data) >= 4:
            i = 1
            while i + 2 < len(raw_data):
                param_id = raw_data[i]
                val = raw_data[i + 2]
                if param_id == 0xC8:
                    max_flow = val
                elif param_id == 0xC9:
                    min_flow = val
                elif param_id == 0xCA:
                    v_time = val
                elif param_id == 0xCB:
                    p_time = val
                i += 3

        return cls(
            sync_flag=raw_data[0],
            max_flow_setpoint=max_flow,
            min_flow_setpoint=min_flow,
            valve_run_time=v_time,
            pump_run_time=p_time,
            raw_extra=extra,
        )

    def to_bytes(self) -> bytes:
        """Pack system sync data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        res = bytes([self.sync_flag])
        if self.raw_extra is not None:
            res += self.raw_extra
        return res


@register_payload("1FC9")
@dataclass(frozen=True, slots=True)
class BindingPayload(PayloadBase):
    """Binding payload (Opcode 1FC9).

    Variable-length Binding binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Binding Type / Command Code  : 00
      +1       xB     vB   Binding Data Byte Sequence   : 10 E0 00 00 00
      --------------------------------------------------------------
      Field-spaced hex : 00 10E0000000
      Payload hex      : 0010E0000000

    Discovery & Protocol Notes:
      # 1FC9 (Binding) is used to pair devices to zones or controllers.
      # Sample Packet Logs:
      # .I --- 34:145039 --:------ 34:145039 1FC9 012 00-30C9-8A368F 00-1FC9-8A368F
      # .W --- 01:054173 34:145039 --:------ 1FC9 006 03-2309-04D39D

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

    Discovery & Protocol Notes:
      # 000A (Zone Info) is sent by THMs (22:) with their zone_idx as payload (e.g. RQ 000A 001 01).
      # CTL (01:) sends 000A with full zone configuration arrays.
      # Sample Packet Logs:
      # .I --- 01:158182 --:------ 01:158182 000A 048 001201F409C4011101F409C40...
      # .I --- 01:158182 --:------ 01:158182 000A 006 081001F409C4

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

    zone_idx: int | str
    zone_flags: int
    min_temp: float
    max_temp: float

    def __post_init__(self) -> None:
        """Normalise index arguments."""
        if isinstance(self.zone_idx, str):
            object.__setattr__(self, "zone_idx", parse_idx(self.zone_idx))

    @classmethod
    def _from_bytes_single(cls, raw_data: bytes, offset: int = 0) -> Self:
        """Unpack a single 6-byte zone config binary payload from offset.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :param offset: Byte offset within raw_data to unpack from.
        :type offset: int
        :returns: Unpacked ZoneConfigPayload instance.
        :rtype: Self
        """
        # Unpack idx, flags, min_temp, max_temp directly from offset
        idx, flags, min_raw, max_raw = struct.unpack_from(
            cls._STRUCT_FMT, raw_data, offset
        )
        return cls(
            zone_idx=idx,
            zone_flags=flags,
            min_temp=min_raw / 100.0,
            max_temp=max_raw / 100.0,
        )

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self | list[Self]:
        """Unpack zone config binary payload (single or multi-zone array).

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Single ZoneConfigPayload instance or list of instances.
        :rtype: Self | list[Self]
        :raises ValueError: If raw_data length is invalid.
        """
        if len(raw_data) < 6 or len(raw_data) % 6 != 0:
            raise ValueError(f"Invalid payload length for 000A: {len(raw_data)}")
        if len(raw_data) > 6:
            return [
                cls._from_bytes_single(raw_data, i) for i in range(0, len(raw_data), 6)
            ]

        return cls._from_bytes_single(raw_data, 0)

    def to_bytes(self) -> bytes:
        """Pack zone config data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        idx = parse_idx(self.zone_idx)
        min_raw = int(round(self.min_temp * 100.0))
        max_raw = int(round(self.max_temp * 100.0))
        return struct.pack(
            self._STRUCT_FMT,
            idx,
            self.zone_flags,
            min_raw,
            max_raw,
        )


@dataclass(frozen=True, slots=True)
class ZoneNamePayload(PayloadBase):
    """Zone name payload (Opcode 0004 W / 0004 RP name variant).

    22-byte Zone Name binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Zone Index (uint8)           : 00
      +1       B      1B   Flag Byte (uint8)            : 00
      +2       20s    20B  ASCII Zone Name (20B null-pad): 4C 6F 75 6E 67 65 00... ("Lounge")
      --------------------------------------------------------------

    :param zone_idx: Zone index byte.
    :type zone_idx: int | str
    :param name: ASCII Zone Name string (max 20 chars).
    :type name: str
    """

    zone_idx: int | str
    name: str

    def __post_init__(self) -> None:
        """Normalise index arguments."""
        if isinstance(self.zone_idx, str):
            object.__setattr__(self, "zone_idx", parse_idx(self.zone_idx))

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack zone name binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked ZoneNamePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 22 bytes.
        """
        if len(raw_data) < 22:
            raise ValueError(
                f"Invalid payload length for ZoneNamePayload: {len(raw_data)}"
            )
        # Unpack zone_idx (uint8), skip 1 pad byte, and extract 20-byte string
        idx, name_raw = struct.unpack_from(">Bx20s", raw_data, 0)
        name = name_raw.rstrip(b"\x00").decode("ascii", errors="replace")
        return cls(zone_idx=idx, name=name)

    def to_bytes(self) -> bytes:
        """Pack zone name data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        idx = parse_idx(self.zone_idx)
        name_bytes = self.name.encode("ascii", errors="replace")[:20].ljust(20, b"\x00")
        return bytes([idx, 0x00]) + name_bytes


@register_payload("0004")
@dataclass(frozen=True, slots=True)
class ZoneSetpointPayload(PayloadBase):
    """Zone target setpoint payload (Opcode 0004).

    3-byte Zone Setpoint binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Zone Index (uint8)           : 01
      +1       h      2B   Target Setpoint (int16*100)  : 07 D0 (20.00°C)
      --------------------------------------------------------------
      Field-spaced hex : 01 07D0
      Payload hex      : 0107D0

    :param zone_idx: Zone index byte.
    :type zone_idx: int | str
    :param setpoint_temp: Target temperature in °C.
    :type setpoint_temp: float
    """

    zone_idx: int | str
    setpoint_temp: float

    def __post_init__(self) -> None:
        """Normalise index arguments."""
        if isinstance(self.zone_idx, str):
            object.__setattr__(self, "zone_idx", parse_idx(self.zone_idx))

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self | ZoneNamePayload:
        """Unpack zone setpoint binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked ZoneSetpointPayload or ZoneNamePayload instance.
        :rtype: Self | ZoneNamePayload
        :raises ValueError: If raw_data length is less than 3 bytes.
        """
        if len(raw_data) >= 22:
            return ZoneNamePayload.from_bytes(raw_data)
        if len(raw_data) < 3:
            raise ValueError(f"Invalid payload length for 0004: {len(raw_data)}")
        # Unpack zone_idx (uint8) and setpoint_raw (int16) directly from offset 0
        idx, sp_raw = struct.unpack_from(">Bh", raw_data, 0)
        return cls(zone_idx=idx, setpoint_temp=sp_raw / 100.0)

    def to_bytes(self) -> bytes:
        """Pack zone setpoint data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        sp_raw = int(round(self.setpoint_temp * 100.0))
        idx = parse_idx(self.zone_idx)
        return bytes([idx]) + sp_raw.to_bytes(2, byteorder="big", signed=True)


@register_payload("12C0")
@dataclass(frozen=True, slots=True)
class OutdoorTempPayload(PayloadBase):
    """Outdoor temperature reading payload (Opcode 12C0).

    2-byte Outdoor Temp binary layout (Big-Endian):
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       h      2B   Outdoor Temperature (int16*100): 05 DC (15.00°C)
      --------------------------------------------------------------
      Field-spaced hex : 05DC
      Payload hex      : 05DC

    :param temperature: Outdoor temperature reading in °C.
    :type temperature: float
    """

    temperature: float

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack outdoor temperature binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked OutdoorTempPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 12C0: {len(raw_data)}")
        # Unpack 16-bit signed outdoor temperature directly from offset 0
        (temp_raw,) = struct.unpack_from(">h", raw_data, 0)
        return cls(temperature=temp_raw / 100.0)

    def to_bytes(self) -> bytes:
        """Pack outdoor temperature data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        temp_raw = int(round(self.temperature * 100.0))
        return temp_raw.to_bytes(2, byteorder="big", signed=True)


@register_payload("2309")
@dataclass(frozen=True, slots=True)
class SetPointInfoPayload(PayloadBase):
    """Set-point info payload (Opcode 2309).

    3-byte Set-point Info binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Zone Index (uint8)           : 00
      +1       h      2B   Setpoint Temp (int16*100)    : 08 34 (21.00°C)
      --------------------------------------------------------------
      Field-spaced hex : 00 0834
      Payload hex      : 000834

    :param zone_idx: Zone index byte.
    :type zone_idx: int
    :param setpoint_temp: Setpoint temperature in °C.
    :type setpoint_temp: float
    """

    zone_idx: int
    setpoint_temp: float

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack setpoint info binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SetPointInfoPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 3 bytes.
        """
        if len(raw_data) < 3:
            raise ValueError(f"Invalid payload length for 2309: {len(raw_data)}")
        idx = raw_data[0]
        sp_raw = int.from_bytes(raw_data[1:3], byteorder="big", signed=True)
        return cls(zone_idx=idx, setpoint_temp=sp_raw / 100.0)

    def to_bytes(self) -> bytes:
        """Pack setpoint info data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        sp_raw = int(round(self.setpoint_temp * 100.0))
        return bytes([self.zone_idx]) + sp_raw.to_bytes(2, byteorder="big", signed=True)


@register_payload("3200")
@dataclass(frozen=True, slots=True)
class BoilerRelayDemandPayload(PayloadBase):
    """Boiler relay heat demand payload (Opcode 3200).

    3-byte Boiler Relay Demand binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Relay Domain / Index (uint8) : 00
      +1       B      1B   Heat Demand Percentage       : C8 (200)
      +2       B      1B   Relay Flags                  : 00
      --------------------------------------------------------------
      Field-spaced hex : 00 C8 00
      Payload hex      : 00C800

    :param domain: Relay domain byte.
    :type domain: int
    :param demand_percent: Demand percentage value (0-200).
    :type demand_percent: int
    :param flags: Relay flags byte.
    :type flags: int
    """

    domain: int
    demand_percent: int
    flags: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack boiler relay demand binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked BoilerRelayDemandPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 3 bytes.
        """
        if len(raw_data) < 3:
            raise ValueError(f"Invalid payload length for 3200: {len(raw_data)}")
        return cls(domain=raw_data[0], demand_percent=raw_data[1], flags=raw_data[2])

    def to_bytes(self) -> bytes:
        """Pack boiler relay demand data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.domain, self.demand_percent, self.flags])


@register_payload("0005")
@dataclass(frozen=True, slots=True)
class SystemZonesPayload(PayloadBase):
    """System zones type and mask payload (Opcode 0005).

    4-byte System Zones binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Header / Index               : 00
      +1       B      1B   Zone Type / Class ID         : 00
      +2       H      2B   Zone Mask uint16             : 01 00
      --------------------------------------------------------------
      Field-spaced hex : 00 00 0100
      Payload hex      : 00000100

    Sample Packet Logs & Protocol Notes:
      # .I --- 01:145038 --:------ 01:145038 0005 004 00000100
      # RP --- 02:017205 18:073736 --:------ 0005 004 0009001F
      # .I --- 34:064023 --:------ 34:064023 0005 012 000A0000-000F0000-00100000
      # Note: ATC928G1000 (1st gen monochrome model) uses 3-byte payload (max 8 zones).
      # UFC devices use seqx[2:4] for UFH zone mapping.

    :param zone_type: Zone type code byte.
    :type zone_type: int
    :param zone_mask: Bitmask of zones present.
    :type zone_mask: int
    :param zone_class_id: Class identifier byte for zone.
    :type zone_class_id: int
    """

    zone_type: int
    zone_mask: int
    zone_class_id: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack system zones binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SystemZonesPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 3 bytes.
        """
        if len(raw_data) < 3:
            raise ValueError(f"Invalid payload length for 0005: {len(raw_data)}")
        mask = (
            int.from_bytes(raw_data[2:4], byteorder="little")
            if len(raw_data) >= 4
            else raw_data[2]
        )
        return cls(
            zone_type=raw_data[1],
            zone_mask=mask,
            zone_class_id=raw_data[1],
        )

    def to_bytes(self) -> bytes:
        """Pack system zones data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([0x00, self.zone_type]) + self.zone_mask.to_bytes(
            2, byteorder="little"
        )


@register_payload("0008")
@dataclass(frozen=True, slots=True)
class RelayDemandPayload(PayloadBase):
    """Relay demand payload (Opcode 0008).

    2-byte Relay Demand binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Domain / Zone Index (uint8)  : 00
      +1       B      1B   Relay Demand uint8 (0-200)   : 64 (50%)
      --------------------------------------------------------------
      Field-spaced hex : 00 64
      Payload hex      : 0064

    Sample Packet Logs & Protocol Notes:
      # See: https://www.domoticaforum.eu/viewtopic.php?f=7&t=5806&start=105#p73681
      # .I --- 01:145038 --:------ 01:145038 0008 002 0314
      # .I --- 01:145038 --:------ 01:145038 0008 002 F914
      # .I --- 01:054173 --:------ 01:054173 0008 002 FA00
      # .I --- 01:145038 --:------ 01:145038 0008 002 FC14
      # RP --- 13:109598 18:199952 --:------ 0008 002 0000
      # RP --- 13:109598 18:199952 --:------ 0008 002 00C8
      # Note: 0008[2:4] maps to 3EF0[2:4] and 3EF1[10:12]. Honeywell Jasper (JST) uses 13-byte variant.

    :param domain_or_zone_idx: Domain or zone index byte.
    :type domain_or_zone_idx: int
    :param demand_percent: Heat demand percentage (0.0 - 100.0).
    :type demand_percent: float
    :param raw_extra: Optional trailing payload bytes for 13-byte Jasper payloads.
    :type raw_extra: bytes | None
    """

    domain_or_zone_idx: int
    demand_percent: float
    raw_extra: bytes | None = None

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack relay demand binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked RelayDemandPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 0008: {len(raw_data)}")
        extra = raw_data[2:] if len(raw_data) > 2 else None
        return cls(
            domain_or_zone_idx=raw_data[0],
            demand_percent=raw_data[1] / 200.0,
            raw_extra=extra,
        )

    def to_bytes(self) -> bytes:
        """Pack relay demand data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        demand_raw = min(200, max(0, int(round(self.demand_percent * 200.0))))
        res = bytes([self.domain_or_zone_idx, demand_raw])
        if self.raw_extra is not None:
            res += self.raw_extra
        return res


@register_payload("000C")
@dataclass(frozen=True, slots=True)
class ZoneDevicesPayload(PayloadBase):
    """Zone device mapping payload (Opcode 000C).

    6-byte Zone Devices binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Zone Index (uint8)           : 00
      +1       B      1B   Device Role ID               : 00
      +2       3B     3B   Device ID uint24             : 10 DA F5
      +5       B      1B   Flags / Trailing Byte        : 00
      --------------------------------------------------------------
      Field-spaced hex : 00 00 10DAF5 00
      Payload hex      : 000010DAF500

    Discovery & Domain Mapping Notes:
      # .I --- 34:092243 --:------ 34:092243 000C 018 00-0A-7F-FFFFFF 00-0F-7F-FFFFFF 00-10-7F-FFFFFF
      # RP --- 01:145038 18:013393 --:------ 000C 006 00-00-00-10DAFD
      # RP --- 01:145038 18:013393 --:------ 000C 012 01-00-00-10DAF5 01-00-00-10DAFB
      # Domain mappings:
      #   Role 0F (APP) -> domain FC (appliance_control / boiler relay)
      #   Role 0E (HTG) -> domain FA (hotwater_valve)
      #   Role 10 (HT1) -> heating_valve
      # Authoritative 000C FA bindings override 3B00/3EF0 hints (issue #834).
      # TODO: 000C sent to a UFC device represents ufh_idx rather than zone_idx.

    :param zone_idx: Zone index byte.
    :type zone_idx: int
    :param device_role_id: Device role identifier byte.
    :type device_role_id: int
    :param device_id_raw: Raw 24-bit integer representation of device ID.
    :type device_id_raw: int
    """

    zone_idx: int
    device_role_id: int
    device_id_raw: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack zone devices binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked ZoneDevicesPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 5 bytes.
        """
        if len(raw_data) < 5:
            raise ValueError(f"Invalid payload length for 000C: {len(raw_data)}")
        dev_id = int.from_bytes(raw_data[2:5], byteorder="big")
        return cls(
            zone_idx=raw_data[0],
            device_role_id=raw_data[1],
            device_id_raw=dev_id,
        )

    def to_bytes(self) -> bytes:
        """Pack zone devices data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        dev_bytes = self.device_id_raw.to_bytes(3, byteorder="big")
        return bytes([self.zone_idx, self.device_role_id]) + dev_bytes + b"\x00"


@register_payload("1081")
@dataclass(frozen=True, slots=True)
class MaxChSetpointPayload(PayloadBase):
    """Maximum CH supply setpoint temperature payload (Opcode 1081).

    3-byte Max CH Setpoint binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Header / Index               : 00
      +1       h      2B   Setpoint Temp (int16*100)    : 1F 40 (80.00°C)
      --------------------------------------------------------------
      Field-spaced hex : 00 1F40
      Payload hex      : 001F40

    :param setpoint_temp: Maximum CH setpoint temperature in °C.
    :type setpoint_temp: float
    """

    setpoint_temp: float

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack max CH setpoint binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked MaxChSetpointPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 3 bytes.
        """
        if len(raw_data) < 3:
            raise ValueError(f"Invalid payload length for 1081: {len(raw_data)}")
        temp_raw = int.from_bytes(raw_data[1:3], byteorder="big", signed=True)
        return cls(setpoint_temp=temp_raw / 100.0)

    def to_bytes(self) -> bytes:
        """Pack max CH setpoint data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        temp_raw = int(round(self.setpoint_temp * 100.0))
        return b"\x00" + temp_raw.to_bytes(2, byteorder="big", signed=True)


@register_payload("1090")
@dataclass(frozen=True, slots=True)
class Opcode1090Payload(PayloadBase):
    """Dual temperature status payload (Opcode 1090).

    5-byte Opcode 1090 binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Header / Index               : 00
      +1       h      2B   Temperature 0 (int16*100)    : 07 D0 (20.00°C)
      +3       h      2B   Temperature 1 (int16*100)    : 01 F4 (5.00°C)
      --------------------------------------------------------------
      Field-spaced hex : 00 07D0 01F4
      Payload hex      : 0007D001F4

    :param temp_0: First temperature value in °C.
    :type temp_0: float
    :param temp_1: Second temperature value in °C.
    :type temp_1: float
    """

    temp_0: float
    temp_1: float

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack opcode 1090 binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked Opcode1090Payload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 5 bytes.
        """
        if len(raw_data) < 5:
            raise ValueError(f"Invalid payload length for 1090: {len(raw_data)}")
        t0_raw = int.from_bytes(raw_data[1:3], byteorder="big", signed=True)
        t1_raw = int.from_bytes(raw_data[3:5], byteorder="big", signed=True)
        return cls(temp_0=t0_raw / 100.0, temp_1=t1_raw / 100.0)

    def to_bytes(self) -> bytes:
        """Pack opcode 1090 data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        t0_bytes = int(round(self.temp_0 * 100.0)).to_bytes(
            2, byteorder="big", signed=True
        )
        t1_bytes = int(round(self.temp_1 * 100.0)).to_bytes(
            2, byteorder="big", signed=True
        )
        return b"\x00" + t0_bytes + t1_bytes


@register_payload("1100")
@dataclass(frozen=True, slots=True)
class TpiParamsPayload(PayloadBase):
    """TPI control parameter payload (Opcode 1100).

    5-byte TPI Parameters binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Domain ID                    : FC
      +1       B      1B   Cycle Rate (cycles/hr * 4)   : 18 (6 cph)
      +2       B      1B   Min On Time (min * 4)        : 04 (1 min)
      +3       B      1B   Min Off Time (min * 4)       : 04 (1 min)
      +4       B      1B   Flags / Trailing             : 00
      --------------------------------------------------------------
      Field-spaced hex : FC 18 04 04 00
      Payload hex      : FC18040400

    Protocol Notes & Sample Packet Logs:
      # Domain ID is normally FC.
      # Honeywell Jasper (JIM) devices emit non-standard variants.
      #  I --- 01:172368 --:------ 01:172368 1100 008 FC180400007FFF00
      #  I --- 01:172368 13:040439 --:------ 1100 008 FC042814007FFF00
      # RQ --- 01:145038 13:163733 --:------ 1100 008 00180400007FFF01  # boiler relay
      # RP --- 13:163733 01:145038 --:------ 1100 008 00180400FF7FFF01
      # RQ --- 01:145038 13:035462 --:------ 1100 008 FC240428007FFF01  # not boiler relay
      # RP --- 13:035462 01:145038 --:------ 1100 008 00240428007FFF01

    :param domain_id: Domain identifier byte.
    :type domain_id: int
    :param cycle_rate: Cycle rate in cycles per hour.
    :type cycle_rate: int
    :param min_on_time: Minimum on-time in minutes.
    :type min_on_time: float
    :param min_off_time: Minimum off-time in minutes.
    :type min_off_time: float
    :param proportional_band_width: Optional proportional bandwidth value.
    :type proportional_band_width: float | None
    """

    domain_id: int
    cycle_rate: int
    min_on_time: float
    min_off_time: float
    proportional_band_width: float | None

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack TPI params binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked TpiParamsPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 4 bytes.
        """
        if len(raw_data) < 4:
            raise ValueError(f"Invalid payload length for 1100: {len(raw_data)}")
        crate = raw_data[1] // 4
        on_time = raw_data[2] / 4.0
        off_time = raw_data[3] / 4.0
        pbw = None
        if len(raw_data) >= 7:
            pbw_raw = int.from_bytes(raw_data[5:7], byteorder="big", signed=True)
            pbw = pbw_raw / 100.0
        return cls(
            domain_id=raw_data[0],
            cycle_rate=crate,
            min_on_time=on_time,
            min_off_time=off_time,
            proportional_band_width=pbw,
        )

    def to_bytes(self) -> bytes:
        """Pack TPI params data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        res = bytes(
            [
                self.domain_id,
                min(255, max(0, self.cycle_rate * 4)),
                min(255, max(0, int(round(self.min_on_time * 4.0)))),
                min(255, max(0, int(round(self.min_off_time * 4.0)))),
                0x00,
            ]
        )
        if self.proportional_band_width is not None:
            pbw_raw = int(round(self.proportional_band_width * 100.0))
            res += pbw_raw.to_bytes(2, byteorder="big", signed=True)
        return res


@register_payload("1300")
@dataclass(frozen=True, slots=True)
class ChPressurePayload(PayloadBase):
    """Central heating system pressure payload (Opcode 1300).

    3-byte CH Pressure binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Header / Index               : 00
      +1       h      2B   Pressure in Bar (int16*100)  : 00 EA (2.34 Bar)
      --------------------------------------------------------------
      Field-spaced hex : 00 00EA
      Payload hex      : 0000EA

    :param pressure_bar: CH system pressure in Bar, or None if invalid.
    :type pressure_bar: float | None
    """

    pressure_bar: float | None

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack CH pressure binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked ChPressurePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 3 bytes.
        """
        if len(raw_data) < 3:
            raise ValueError(f"Invalid payload length for 1300: {len(raw_data)}")
        if raw_data[1:3] == b"\x09\xf6":
            return cls(pressure_bar=None)
        val_raw = int.from_bytes(raw_data[1:3], byteorder="big", signed=True)
        return cls(pressure_bar=val_raw / 100.0)

    def to_bytes(self) -> bytes:
        """Pack CH pressure data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        if self.pressure_bar is None:
            return b"\x00\x09\xf6"
        val_raw = int(round(self.pressure_bar * 100.0))
        return b"\x00" + val_raw.to_bytes(2, byteorder="big", signed=True)


@register_payload("2349")
@dataclass(frozen=True, slots=True)
class ZoneModePayload(PayloadBase):
    """Zone operating mode and override payload (Opcode 2349).

    7-byte Zone Mode binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Zone Index (uint8)           : 00
      +1       h      2B   Setpoint Temp (int16*100)    : 08 34 (21.00°C)
      +3       B      1B   Zone Mode Code (uint8)       : 00 (Follow)
      +4       3B     3B   Duration / Until Bytes       : FF FF FF
      --------------------------------------------------------------
      Field-spaced hex : 00 0834 00 FFFFFF
      Payload hex      : 00083400FFFFFF

    Protocol Notes & Sample Packet Logs:
      # Hometronic controllers do not react to W/2349 but require W/2309 instead.
      # RP --- 30:258557 34:225071 --:------ 2349 013 007FFF00FFFFFFFFFFFFFFFFFF
      # RP --- 30:253184 34:010943 --:------ 2349 013 00064000FFFFFF00110E0507E5
      # RQ --- 34:225071 30:258557 --:------ 2349 001 00
      # .I --- 10:067219 --:------ 10:067219 2349 004 00000001
      # .W --- 18:141846 01:050858 --:------ 2349 013 02-0960-04-FFFFFF-0409160607E5

    :param zone_idx: Zone index byte.
    :type zone_idx: int
    :param setpoint_temp: Target setpoint temperature in °C.
    :type setpoint_temp: float
    :param mode_code: Zone mode code integer.
    :type mode_code: int
    :param duration_minutes: Override duration in minutes, if present.
    :type duration_minutes: int | None
    """

    zone_idx: int | str
    setpoint_temp: float | None
    mode_code: int | str
    duration_minutes: int | None = None
    until_dtm: str | dt | bytes | None = None

    def __post_init__(self) -> None:
        """Normalise index arguments."""
        if isinstance(self.zone_idx, str):
            object.__setattr__(self, "zone_idx", parse_idx(self.zone_idx))
        if isinstance(self.mode_code, str):
            object.__setattr__(self, "mode_code", int(self.mode_code, 16))

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack zone mode binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked ZoneModePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 4 bytes.
        """
        if len(raw_data) < 4:
            raise ValueError(f"Invalid payload length for 2349: {len(raw_data)}")
        sp_raw = int.from_bytes(raw_data[1:3], byteorder="big", signed=True)
        setpoint = None if sp_raw in (0x31FF, 0x7FFF) else sp_raw / 100.0
        mode = raw_data[3]
        dur = None
        if len(raw_data) >= 7 and raw_data[4:7] != b"\xff\xff\xff":
            dur = int.from_bytes(raw_data[4:7], byteorder="big")
        until_raw = None
        if len(raw_data) >= 13:
            until_raw = raw_data[7:13].hex().upper()
        return cls(
            zone_idx=raw_data[0],
            setpoint_temp=setpoint,
            mode_code=mode,
            duration_minutes=dur,
            until_dtm=until_raw,
        )

    def to_bytes(self) -> bytes:
        """Pack zone mode data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        idx = parse_idx(self.zone_idx)
        if self.setpoint_temp is None:
            sp_raw = 0x7FFF
        else:
            sp_raw = int(round(self.setpoint_temp * 100.0))
        mode = (
            int(self.mode_code, 16)
            if isinstance(self.mode_code, str)
            else self.mode_code
        )
        res = (
            bytes([idx])
            + sp_raw.to_bytes(2, byteorder="big", signed=True)
            + bytes([mode])
        )
        if self.duration_minutes is not None:
            res += self.duration_minutes.to_bytes(3, byteorder="big")
        else:
            res += b"\xff\xff\xff"
        if self.until_dtm is not None:
            if isinstance(self.until_dtm, bytes):
                res += self.until_dtm
            elif (
                isinstance(self.until_dtm, str)
                and len(self.until_dtm) == 12
                and all(c in "0123456789ABCDEFabcdef" for c in self.until_dtm)
            ):
                res += bytes.fromhex(self.until_dtm)
            else:
                res += bytes.fromhex(hex_from_dtm(self.until_dtm))
        return res


@register_payload("2389")
@dataclass(frozen=True, slots=True)
class SetpointOverridePayload(PayloadBase):
    """Target setpoint override payload (Opcode 2389).

    3-byte Setpoint Override binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Domain / Zone Index (uint8)  : 00
      +1       h      2B   Target Temp (int16*100)      : 07 D0 (20.00°C)
      --------------------------------------------------------------
      Field-spaced hex : 00 07D0
      Payload hex      : 0007D0

    :param domain_or_zone_idx: Domain or zone index byte.
    :type domain_or_zone_idx: int
    :param target_temp: Target temperature in °C.
    :type target_temp: float
    """

    domain_or_zone_idx: int
    target_temp: float

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack setpoint override binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SetpointOverridePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 3 bytes.
        """
        if len(raw_data) < 3:
            raise ValueError(f"Invalid payload length for 2389: {len(raw_data)}")
        temp_raw = int.from_bytes(raw_data[1:3], byteorder="big", signed=True)
        return cls(
            domain_or_zone_idx=raw_data[0],
            target_temp=temp_raw / 100.0,
        )

    def to_bytes(self) -> bytes:
        """Pack setpoint override data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        temp_raw = int(round(self.target_temp * 100.0))
        return bytes([self.domain_or_zone_idx]) + temp_raw.to_bytes(
            2, byteorder="big", signed=True
        )


@register_payload("3B00")
@dataclass(frozen=True, slots=True)
class ActuatorSyncPayload(PayloadBase):
    """TPI cycle actuator sync payload (Opcode 3B00).

    2-byte Actuator Sync binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Domain ID / Header           : FC
      +1       B      1B   Sync Flag / Command          : C8 (200)
      --------------------------------------------------------------
      Field-spaced hex : FC C8
      Payload hex      : FCC8

    Protocol & Heuristic Notes:
      # 3B00/3EF0 FC broadcasts are emitted by system timing masters and heater relays.
      # Hotwater valves (FA) also broadcast 3B00/3EF0, so 000C binding table overrides 3B00 hints.
      # Sample Packet Logs:
      # 053  I --- 13:209679 --:------ 13:209679 3B00 002 00C8
      # 045  I --- 01:158182 --:------ 01:158182 3B00 002 FCC8

    :param domain_id: Domain identifier byte.
    :type domain_id: int
    :param sync_flag: Sync flag byte.
    :type sync_flag: int
    """

    domain_id: int
    sync_flag: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack actuator sync binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked ActuatorSyncPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 3B00: {len(raw_data)}")
        return cls(domain_id=raw_data[0], sync_flag=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack actuator sync data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.domain_id, self.sync_flag])


@register_payload("3EF0")
@dataclass(frozen=True, slots=True)
class ActuatorStatePayload(PayloadBase):
    """Actuator modulation state payload (Opcode 3EF0).

    3-byte Actuator State binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Domain / Zone Index          : 00
      +1       B      1B   Modulation Level (0-200)     : 64 (50%)
      +2       B      1B   Flags / Status Byte          : FF
      --------------------------------------------------------------
      Field-spaced hex : 00 64 FF
      Payload hex      : 0064FF

    Protocol Notes:
      # Honeywell Jasper (JIM) devices emit 4-byte payload containing flags_3.
      # Header context payload[:2] is normally 00.

    :param domain_id: Domain or zone index byte.
    :type domain_id: int
    :param modulation_level: Modulation level percentage (0.0 - 100.0).
    :type modulation_level: float
    :param flags_2: Secondary status flag byte.
    :type flags_2: int
    :param flags_3: Optional tertiary status flag byte.
    :type flags_3: int | None
    """

    domain_id: int
    modulation_level: float
    flags_2: int
    flags_3: int | None

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack actuator state binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked ActuatorStatePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 3 bytes.
        """
        if len(raw_data) < 3:
            raise ValueError(f"Invalid payload length for 3EF0: {len(raw_data)}")
        mod = raw_data[1] / 200.0
        f2 = raw_data[2]
        f3 = raw_data[3] if len(raw_data) >= 4 else None
        return cls(
            domain_id=raw_data[0],
            modulation_level=mod,
            flags_2=f2,
            flags_3=f3,
        )

    def to_bytes(self) -> bytes:
        """Pack actuator state data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        mod_raw = min(200, max(0, int(round(self.modulation_level * 200.0))))
        res = bytes([self.domain_id, mod_raw, self.flags_2])
        if self.flags_3 is not None:
            res += bytes([self.flags_3])
        return res


@register_payload("3EF1")
@dataclass(frozen=True, slots=True)
class ActuatorCyclePayload(PayloadBase):
    """Actuator cycle and countdown payload (Opcode 3EF1).

    6-byte Actuator Cycle binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       H      2B   Cycle Countdown Sec (uint16) : 00 3C (60s)
      +2       H      2B   Actuator Countdown (uint16)  : 00 3C (60s)
      +4       B      1B   Header / Flags               : 10
      +5       B      1B   Modulation Level uint8       : 64 (100%)
      --------------------------------------------------------------
      Field-spaced hex : 003C 003C 10 64
      Payload hex      : 003C003C1064

    Sample Packet Logs:
      # RP --- 13:109598 18:002563 --:------ 3EF1 007 0000BF-00BFC8FF
      # RP --- 10:048122 18:140805 --:------ 3EF1 007 007FFF-003C2A10  # 10:s RP always 7FFF
      # RP --- 13:109598 18:199952 --:------ 3EF1 007 0001B8-01B800FF  # 13:s RP
      # RQ --- 31:004811 13:077615 --:------ 3EF1 001 00
      # RP --- 13:077615 31:004811 --:------ 3EF1 007 00024D001300FF
      # RQ --- 22:068154 13:031208 --:------ 3EF1 002 0000
      # RP --- 13:031208 22:068154 --:------ 3EF1 007 00024E00E000FF

    :param cycle_countdown_sec: Cycle countdown in seconds.
    :type cycle_countdown_sec: int | None
    :param actuator_countdown_sec: Actuator countdown in seconds.
    :type actuator_countdown_sec: int | None
    :param modulation_level: Modulation level fraction (0.0 - 1.0).
    :type modulation_level: float
    """

    cycle_countdown_sec: int | None
    actuator_countdown_sec: int | None
    modulation_level: float

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack actuator cycle binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked ActuatorCyclePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 6 bytes.
        """
        if len(raw_data) < 6:
            raise ValueError(f"Invalid payload length for 3EF1: {len(raw_data)}")
        c_down = (
            None
            if raw_data[0:2] == b"\x7f\xff"
            else int.from_bytes(raw_data[0:2], byteorder="big")
        )
        a_down = (
            None
            if raw_data[2:4] == b"\x7f\xff"
            else int.from_bytes(raw_data[2:4], byteorder="big")
        )
        mod = raw_data[5] / 100.0
        return cls(
            cycle_countdown_sec=c_down,
            actuator_countdown_sec=a_down,
            modulation_level=mod,
        )

    def to_bytes(self) -> bytes:
        """Pack actuator cycle data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        c_bytes = (
            b"\x7f\xff"
            if self.cycle_countdown_sec is None
            else self.cycle_countdown_sec.to_bytes(2, byteorder="big")
        )
        a_bytes = (
            b"\x7f\xff"
            if self.actuator_countdown_sec is None
            else self.actuator_countdown_sec.to_bytes(2, byteorder="big")
        )
        mod_raw = min(100, max(0, int(round(self.modulation_level * 100.0))))
        return c_bytes + a_bytes + b"\x10" + bytes([mod_raw])
