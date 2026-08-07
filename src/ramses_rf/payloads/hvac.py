"""RAMSES RF - HVAC and Ventilation payload dataclasses.

This module contains strongly-typed dataclass representations for HVAC, ventilation,
air quality, and fan status packet payloads.
"""

import struct
from dataclasses import dataclass
from typing import ClassVar, Self

from .base import PayloadBase
from .registry import register_payload


@register_payload("01FF")
@dataclass(frozen=True, slots=True)
class SpiderThermostatPayload(PayloadBase):
    """Spider Thermostat payload (Opcode 01FF).

    5-byte Spider Thermostat binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Header / Domain              : 00
      +1       B      1B   Sub-Header / Flag            : 80
      +2       B      1B   Temperature (int8*2)         : 28 (20.0°C)
      +3       B      1B   Setpoint Min (int8*2)        : 0A (5.0°C)
      +4       B      1B   Setpoint Max (int8*2)        : 46 (35.0°C)
      --------------------------------------------------------------
      Field-spaced hex : 00 80 28 0A 46
      Payload hex      : 0080280A46

    :param temp: Temperature reading in °C.
    :type temp: float
    :param setpoint_min: Minimum setpoint bound in °C.
    :type setpoint_min: float
    :param setpoint_max: Maximum setpoint bound in °C.
    :type setpoint_max: float
    """

    temp: float
    setpoint_min: float
    setpoint_max: float

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack Spider thermostat binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SpiderThermostatPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 5 bytes.
        """
        if len(raw_data) < 5:
            raise ValueError(f"Invalid payload length for 01FF: {len(raw_data)}")
        temp_val = raw_data[2] / 2.0
        sp_min = raw_data[3] / 2.0
        sp_max = raw_data[4] / 2.0
        return cls(temp=temp_val, setpoint_min=sp_min, setpoint_max=sp_max)

    def to_bytes(self) -> bytes:
        """Pack Spider thermostat data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        t_raw = int(round(self.temp * 2.0))
        sp_min_raw = int(round(self.setpoint_min * 2.0))
        sp_max_raw = int(round(self.setpoint_max * 2.0))
        return bytes([0, 128, t_raw, sp_min_raw, sp_max_raw])


@register_payload("10D0")
@dataclass(frozen=True, slots=True)
class HvacFilterChangePayload(PayloadBase):
    """HVAC filter change counter payload (Opcode 10D0).

    6-byte Filter Change binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Header / Domain              : 00
      +1       B      1B   Remaining Days (uint8)       : B4 (180 days)
      +2       B      1B   Lifetime Days (uint8)        : B4 (180 days)
      +3       B      1B   Remaining Percent (uint8)    : C8 (100.0%)
      +4       2s     2B   Reserved / Trailer bytes     : 00 00
      --------------------------------------------------------------
      Field-spaced hex : 00 B4 B4 C8 0000
      Payload hex      : 00B4B4C80000

    :param remaining_days: Remaining filter days integer.
    :type remaining_days: int
    :param days_lifetime: Total filter lifetime days integer.
    :type days_lifetime: int
    :param remaining_percent: Remaining filter percentage.
    :type remaining_percent: float
    """

    remaining_days: int
    days_lifetime: int
    remaining_percent: float

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack HVAC filter change counter binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked HvacFilterChangePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 4 bytes.
        """
        if len(raw_data) < 4:
            raise ValueError(f"Invalid payload length for 10D0: {len(raw_data)}")
        rem_days = raw_data[1]
        life_days = raw_data[2]
        rem_pct = raw_data[3] / 2.0
        return cls(
            remaining_days=rem_days,
            days_lifetime=life_days,
            remaining_percent=rem_pct,
        )

    def to_bytes(self) -> bytes:
        """Pack HVAC filter change counter data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        rem_pct_raw = int(round(self.remaining_percent * 2.0))
        return bytes([0, self.remaining_days, self.days_lifetime, rem_pct_raw, 0, 0])


@register_payload("10E2")
@dataclass(frozen=True, slots=True)
class HvacCounterPayload(PayloadBase):
    """HVAC pulse counter payload (Opcode 10E2).

    3-byte HVAC Counter binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Header / Domain              : 00
      +1       H      2B   Counter Value (uint16)       : AD 74
      --------------------------------------------------------------
      Field-spaced hex : 00 AD74
      Payload hex      : 00AD74

    :param counter: Cumulative HVAC operational counter value integer.
    :type counter: int
    """

    counter: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack HVAC pulse counter binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked HvacCounterPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 3 bytes.
        """
        if len(raw_data) < 3:
            raise ValueError(f"Invalid payload length for 10E2: {len(raw_data)}")
        val = int.from_bytes(raw_data[1:3], byteorder="big", signed=False)
        return cls(counter=val)

    def to_bytes(self) -> bytes:
        """Pack HVAC pulse counter data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([0]) + self.counter.to_bytes(2, byteorder="big", signed=False)


@register_payload("1280")
@dataclass(frozen=True, slots=True)
class OutdoorHumidityPayload(PayloadBase):
    """Outdoor humidity reading payload (Opcode 1280).

    2-byte Outdoor Humidity binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Header / Domain              : 00
      +1       B      1B   Humidity percentage (uint8)  : 64 (50.0%)
      --------------------------------------------------------------
      Field-spaced hex : 00 64
      Payload hex      : 0064

    :param humidity_percent: Outdoor relative humidity reading.
    :type humidity_percent: float
    """

    humidity_percent: float

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack outdoor humidity binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked OutdoorHumidityPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 1280: {len(raw_data)}")
        raw_val = raw_data[1]
        return cls(humidity_percent=raw_val / 2.0)

    def to_bytes(self) -> bytes:
        """Pack outdoor humidity data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        raw_val = int(round(self.humidity_percent * 2.0))
        return bytes([0, raw_val])


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
            raise ValueError(f"Invalid payload length for 1298: {len(raw_data)}")
        val = int.from_bytes(raw_data[:2], byteorder="big", signed=False)
        return cls(co2_ppm=val)

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


@register_payload("12C8")
@dataclass(frozen=True, slots=True)
class AirQualityBasisPayload(PayloadBase):
    """Air quality basis payload (Opcode 12C8).

    2-byte Air Quality Basis binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Air Quality Percent (uint8)  : 64 (50.0%)
      +1       B      1B   Basis Code Flag (uint8)      : 00
      --------------------------------------------------------------
      Field-spaced hex : 64 00
      Payload hex      : 6400

    :param air_quality_percent: Air quality measurement percentage.
    :type air_quality_percent: float
    :param basis_flag: Air quality basis classification flag.
    :type basis_flag: int
    """

    air_quality_percent: float
    basis_flag: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack air quality basis binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked AirQualityBasisPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 12C8: {len(raw_data)}")
        aq_pct = raw_data[0] / 2.0
        basis = raw_data[1]
        return cls(air_quality_percent=aq_pct, basis_flag=basis)

    def to_bytes(self) -> bytes:
        """Pack air quality basis data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        aq_raw = int(round(self.air_quality_percent * 2.0))
        return bytes([aq_raw, self.basis_flag])


@register_payload("1470")
@dataclass(frozen=True, slots=True)
class HvacProgrammeSchemePayload(PayloadBase):
    """HVAC programme schedule scheme payload (Opcode 1470).

    2-byte Programme Scheme binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Scheme Code (uint8)          : 0B
      +1       B      1B   Daily Setpoints (uint8)      : 03
      --------------------------------------------------------------
      Field-spaced hex : 0B 03
      Payload hex      : 0B03

    :param scheme_code: Schedule scheme classification code byte.
    :type scheme_code: int
    :param daily_setpoints: Daily setpoint count byte.
    :type daily_setpoints: int
    """

    scheme_code: int
    daily_setpoints: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack HVAC programme scheme binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked HvacProgrammeSchemePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 1470: {len(raw_data)}")
        return cls(scheme_code=raw_data[0], daily_setpoints=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack HVAC programme scheme data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.scheme_code, self.daily_setpoints])


@register_payload("1F70")
@dataclass(frozen=True, slots=True)
class HvacProgrammeConfigPayload(PayloadBase):
    """HVAC programme schedule configuration payload (Opcode 1F70).

    4-byte Programme Config binary layout (Big-Endian):
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Day Index (uint8)            : 01
      +1       B      1B   Setpoint Index (uint8)       : 00
      +2       H      2B   Start Time Mins (uint16)     : 01 68 (360 mins)
      --------------------------------------------------------------
      Field-spaced hex : 01 00 0168
      Payload hex      : 01000168

    :param day_idx: Schedule day index byte.
    :type day_idx: int
    :param setpoint_idx: Schedule setpoint index byte.
    :type setpoint_idx: int
    :param start_time_mins: Start time in minutes past midnight.
    :type start_time_mins: int
    """

    day_idx: int
    setpoint_idx: int
    start_time_mins: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack HVAC programme config binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked HvacProgrammeConfigPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 4 bytes.
        """
        if len(raw_data) < 4:
            raise ValueError(f"Invalid payload length for 1F70: {len(raw_data)}")
        d_idx = raw_data[0]
        sp_idx = raw_data[1]
        t_mins = int.from_bytes(raw_data[2:4], byteorder="big", signed=False)
        return cls(day_idx=d_idx, setpoint_idx=sp_idx, start_time_mins=t_mins)

    def to_bytes(self) -> bytes:
        """Pack HVAC programme config data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.day_idx, self.setpoint_idx]) + self.start_time_mins.to_bytes(
            2, byteorder="big", signed=False
        )


@register_payload("1FCA")
@dataclass(frozen=True, slots=True)
class HvacDevicePairingPayload(PayloadBase):
    """HVAC device pairing configuration payload (Opcode 1FCA).

    Variable Device Pairing binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Pairing Type Code (uint8)    : 00
      +1       xs     Var  Paired Device Raw Bytes      : 01 02 03
      --------------------------------------------------------------
      Field-spaced hex : 00 010203
      Payload hex      : 00010203

    :param pairing_type: Pairing type code byte.
    :type pairing_type: int
    :param device_bytes: Paired device raw bytes sequence.
    :type device_bytes: bytes
    """

    pairing_type: int
    device_bytes: bytes

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack HVAC device pairing binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked HvacDevicePairingPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data is empty.
        """
        if not raw_data:
            raise ValueError("Payload data cannot be empty")
        return cls(pairing_type=raw_data[0], device_bytes=raw_data[1:])

    def to_bytes(self) -> bytes:
        """Pack HVAC device pairing data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.pairing_type]) + self.device_bytes


@register_payload("2210")
@dataclass(frozen=True, slots=True)
class HvacAutoRequestPayload(PayloadBase):
    """HVAC auto demand request payload (Opcode 2210).

    2-byte Auto Request binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Requested Fan Percent        : 64 (50.0%)
      +1       B      1B   Request Reason Code          : 02 (CO2)
      --------------------------------------------------------------
      Field-spaced hex : 64 02
      Payload hex      : 6402

    :param requested_fan_percent: Auto requested fan speed percentage.
    :type requested_fan_percent: float
    :param request_reason: Request reason classification code byte.
    :type request_reason: int
    """

    requested_fan_percent: float
    request_reason: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack HVAC auto request binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked HvacAutoRequestPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 2210: {len(raw_data)}")
        fan_pct = raw_data[0] / 2.0
        reason = raw_data[1]
        return cls(requested_fan_percent=fan_pct, request_reason=reason)

    def to_bytes(self) -> bytes:
        """Pack HVAC auto request data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        fan_raw = int(round(self.requested_fan_percent * 2.0))
        return bytes([fan_raw, self.request_reason])


@register_payload("22B0")
@dataclass(frozen=True, slots=True)
class HvacProgrammeEnabledPayload(PayloadBase):
    """HVAC programme enabled status payload (Opcode 22B0).

    2-byte Programme Enabled binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Header / Domain              : 00
      +1       B      1B   Enabled Flag (5=True, 6=False): 05
      --------------------------------------------------------------
      Field-spaced hex : 00 05
      Payload hex      : 0005

    :param enabled: True if schedule program calendar is enabled.
    :type enabled: bool
    """

    enabled: bool

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack HVAC programme enabled status binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked HvacProgrammeEnabledPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 22B0: {len(raw_data)}")
        is_enabled = raw_data[1] == 5
        return cls(enabled=is_enabled)

    def to_bytes(self) -> bytes:
        """Pack HVAC programme enabled status data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        code = 5 if self.enabled else 6
        return bytes([0, code])


@register_payload("22E0")
@register_payload("22E5")
@register_payload("22E9")
@dataclass(frozen=True, slots=True)
class HvacVentilationStatusPayload(PayloadBase):
    """HVAC ventilation status payload (Opcode 22E0, 22E5, 22E9).

    2-byte Ventilation Status binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Fan Speed / Flow Mode        : 01
      +1       B      1B   Status Flags / State         : 00
      --------------------------------------------------------------
      Field-spaced hex : 01 00
      Payload hex      : 0100

    :param flow_mode: Current ventilation flow mode byte.
    :type flow_mode: int
    :param status_flags: Status flags byte.
    :type status_flags: int
    """

    flow_mode: int
    status_flags: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack ventilation status binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked HvacVentilationStatusPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length: {len(raw_data)}")
        return cls(flow_mode=raw_data[0], status_flags=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack ventilation status data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.flow_mode, self.status_flags])


@register_payload("22F1")
@register_payload("22F2")
@register_payload("22F3")
@register_payload("22F4")
@register_payload("22F7")
@register_payload("22F8")
@dataclass(frozen=True, slots=True)
class FanModePayload(PayloadBase):
    """Fan mode and speed setting payload (Opcode 22F1, 22F2-22F8).

    3-byte Fan Mode binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Header / Domain (uint8)      : 00
      +1       B      1B   Fan Mode Index (uint8)       : 02 (Mode 2)
      +2       B      1B   Max Fan Mode (uint8)         : 04 (4 Modes)
      --------------------------------------------------------------
      Field-spaced hex : 00 02 04
      Payload hex      : 000204

    :param header: Domain or header index byte.
    :type header: int
    :param mode_idx: Selected fan mode integer index.
    :type mode_idx: int
    :param mode_max: Maximum supported fan mode integer index.
    :type mode_max: int
    """

    header: int
    mode_idx: int
    mode_max: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack fan mode binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked FanModePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 3 bytes.
        """
        if len(raw_data) < 3:
            raise ValueError(f"Invalid payload length for 22F1: {len(raw_data)}")
        return cls(header=raw_data[0], mode_idx=raw_data[1], mode_max=raw_data[2])

    def to_bytes(self) -> bytes:
        """Pack fan mode data into 3-byte binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.header, self.mode_idx, self.mode_max])


@register_payload("2411")
@dataclass(frozen=True, slots=True)
class HvacFanParamPayload(PayloadBase):
    """HVAC fan parameters payload (Opcode 2411).

    23-byte HVAC Fan Parameter binary layout (Big-Endian):
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       >B     1B   Parameter Index (uint8)      : 00
      +1       H      2B   Parameter ID (uint16)        : 00 0A (Param 10)
      +3       B      1B   Flags (uint8)                : 00
      +4       B      1B   Data Type (uint8)            : 10
      +5       i      4B   Scaled Value (int32)         : 00 00 00 05 (5)
      +9       i      4B   Min Value Scaled (int32)     : 00 00 00 00 (0)
      +13      i      4B   Max Value Scaled (int32)     : 00 00 00 64 (100)
      +17      i      4B   Precision Scaled (int32)     : 00 00 00 01 (1)
      +21      2s     2B   Reserved / Trailer bytes     : 00 01
      --------------------------------------------------------------
      Field-spaced hex : 00 000A 00 10 00000005 00000000 00000064 00000001 0001
      Payload hex      : 00000A0010000000050000000000000064000000010001

    :param param_id: Fan parameter identifier integer.
    :type param_id: int
    :param data_type: Parameter data type integer.
    :type data_type: int
    :param value_scaled: Current scaled parameter value integer.
    :type value_scaled: int
    :param min_val_scaled: Minimum allowed scaled parameter value integer.
    :type min_val_scaled: int
    :param max_val_scaled: Maximum allowed scaled parameter value integer.
    :type max_val_scaled: int
    :param precision_scaled: Parameter scaling precision integer.
    :type precision_scaled: int
    :param trailer_bytes: Reserved trailer bytes sequence.
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
        """Unpack 23-byte HVAC fan parameters binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked HvacFanParamPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 23 bytes.
        """
        if len(raw_data) < 23:
            raise ValueError(f"Invalid payload length for 2411: {len(raw_data)}")
        (
            _,
            p_id,
            _,
            d_type,
            val_s,
            min_s,
            max_s,
            prec_s,
            trailer,
        ) = struct.unpack(cls._STRUCT_FMT, raw_data[:23])
        return cls(
            param_id=p_id,
            data_type=d_type,
            value_scaled=val_s,
            min_val_scaled=min_s,
            max_val_scaled=max_s,
            precision_scaled=prec_s,
            trailer_bytes=trailer,
        )

    def to_bytes(self) -> bytes:
        """Pack HVAC fan parameters data into 23-byte binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return struct.pack(
            self._STRUCT_FMT,
            0,
            self.param_id,
            0,
            self.data_type,
            self.value_scaled,
            self.min_val_scaled,
            self.max_val_scaled,
            self.precision_scaled,
            self.trailer_bytes,
        )


@register_payload("3110")
@register_payload("3120")
@register_payload("313E")
@dataclass(frozen=True, slots=True)
class HvacAirQualityPayload(PayloadBase):
    """HVAC indoor air quality sensor payload (Opcode 3110, 3120, 313E).

    2-byte Air Quality binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       H      2B   Air Quality Index / VOC      : 00 C8 (200 AQI)
      --------------------------------------------------------------
      Field-spaced hex : 00C8
      Payload hex      : 00C8

    :param air_quality_aqi: Air quality index / VOC measurement value.
    :type air_quality_aqi: int
    """

    air_quality_aqi: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack air quality binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked HvacAirQualityPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length: {len(raw_data)}")
        return cls(
            air_quality_aqi=int.from_bytes(raw_data[:2], byteorder="big", signed=False)
        )

    def to_bytes(self) -> bytes:
        """Pack air quality data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return self.air_quality_aqi.to_bytes(2, byteorder="big", signed=False)


@register_payload("31D9")
@register_payload("31DA")
@register_payload("31E0")
@dataclass(frozen=True, slots=True)
class HvacBypassStatePayload(PayloadBase):
    """HVAC bypass damper state payload (Opcode 31D9, 31DA, 31E0).

    2-byte Bypass State binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Bypass Position (0-100%)     : 64 (100%)
      +1       B      1B   Bypass Mode Flags            : 00
      --------------------------------------------------------------
      Field-spaced hex : 64 00
      Payload hex      : 6400

    :param bypass_position: Bypass damper position percentage (0-100).
    :type bypass_position: int
    :param mode_flags: Bypass mode flags byte.
    :type mode_flags: int
    """

    bypass_position: int
    mode_flags: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack bypass damper state binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked HvacBypassStatePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length: {len(raw_data)}")
        return cls(bypass_position=raw_data[0], mode_flags=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack bypass damper state data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.bypass_position, self.mode_flags])


@register_payload("4401")
@dataclass(frozen=True, slots=True)
class HvacFaultLogEntryPayload(PayloadBase):
    """HVAC fault log entry payload (Opcode 4401).

    2-byte Fault Log Entry binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Fault Index (uint8)          : 00
      +1       B      1B   Fault Code (uint8)           : 01
      --------------------------------------------------------------
      Field-spaced hex : 00 01
      Payload hex      : 0001

    :param fault_idx: Fault log index byte.
    :type fault_idx: int
    :param fault_code: HVAC fault code integer.
    :type fault_code: int
    """

    fault_idx: int
    fault_code: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack HVAC fault log entry binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked HvacFaultLogEntryPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 4401: {len(raw_data)}")
        return cls(fault_idx=raw_data[0], fault_code=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack HVAC fault log entry data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.fault_idx, self.fault_code])


@register_payload("4E01")
@register_payload("4E02")
@register_payload("4E04")
@register_payload("4E0D")
@register_payload("4E14")
@register_payload("4E15")
@register_payload("4E16")
@register_payload("4E20")
@register_payload("4E21")
@dataclass(frozen=True, slots=True)
class HvacFaultStatusPayload(PayloadBase):
    """HVAC fault log status payload (Opcode 4E01, 4E02-4E21).

    2-byte Fault Status binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Fault Code (uint8)           : 00
      +1       B      1B   Severity / Flags             : 00
      --------------------------------------------------------------
      Field-spaced hex : 00 00
      Payload hex      : 0000

    :param fault_code: HVAC fault code.
    :type fault_code: int
    :param flags: Fault status flags.
    :type flags: int
    """

    fault_code: int
    flags: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack fault status binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked HvacFaultStatusPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length: {len(raw_data)}")
        return cls(fault_code=raw_data[0], flags=raw_data[1])

    def to_bytes(self) -> bytes:
        """Pack fault status data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.fault_code, self.flags])
