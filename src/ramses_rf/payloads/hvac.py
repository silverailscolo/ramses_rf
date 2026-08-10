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

    :param temp: Temperature reading in °C, or None if N/A.
    :type temp: float | None
    :param setpoint_min: Minimum setpoint bound in °C, or None if N/A.
    :type setpoint_min: float | None
    :param setpoint_max: Maximum setpoint bound in °C, or None if N/A.
    :type setpoint_max: float | None
    """

    temp: float | None
    setpoint_min: float | None
    setpoint_max: float | None

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
        temp_val = None if raw_data[2] in (0x7F, 0x80) else raw_data[2] / 2.0
        sp_min = None if raw_data[3] in (0x7F, 0x80) else raw_data[3] / 2.0
        sp_max = None if raw_data[4] in (0x7F, 0x80) else raw_data[4] / 2.0
        return cls(temp=temp_val, setpoint_min=sp_min, setpoint_max=sp_max)

    def to_bytes(self) -> bytes:
        """Pack Spider thermostat data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        t_raw = 0x7F if self.temp is None else int(round(self.temp * 2.0))
        sp_min_raw = (
            0x7F if self.setpoint_min is None else int(round(self.setpoint_min * 2.0))
        )
        sp_max_raw = (
            0x7F if self.setpoint_max is None else int(round(self.setpoint_max * 2.0))
        )
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

    :param remaining_days: Remaining filter days integer, or None if reset command.
    :type remaining_days: int | None
    :param days_lifetime: Total filter lifetime days integer, or None if reset command.
    :type days_lifetime: int | None
    :param remaining_percent: Remaining filter percentage, or None if reset command.
    :type remaining_percent: float | None
    :param reset_counter: True if reset command payload (00FF).
    :type reset_counter: bool
    """

    remaining_days: int | None = None
    days_lifetime: int | None = None
    remaining_percent: float | None = None
    reset_counter: bool = False

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack HVAC filter change counter binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked HvacFilterChangePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) == 2 and raw_data == b"\x00\xff":
            return cls(reset_counter=True)
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
        if self.reset_counter:
            return b"\x00\xff"
        rem_pct_raw = (
            int(round(self.remaining_percent * 2.0))
            if self.remaining_percent is not None
            else 0
        )
        return bytes(
            [
                0,
                self.remaining_days or 0,
                self.days_lifetime or 0,
                rem_pct_raw,
                0,
                0,
            ]
        )


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

    humidity_percent: float | None

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
        # PROTOCOL QUIRK: 0x00, 0xEF, and 0xFF are protocol sentinel
        # null-markers indicating an uninstalled or absent humidity
        # sensor. Zero atmospheric humidity (0.0%) is physically
        # impossible. Normalise sentinel bytes to None to prevent
        # invalid 0.0% domain states (see ramses-rf/ramses_cc#742).
        hum = None if raw_val in (0x00, 0xEF, 0xFF) else raw_val / 2.0
        return cls(humidity_percent=hum)

    def to_bytes(self) -> bytes:
        """Pack outdoor humidity data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        if self.humidity_percent is None:
            return bytes([0, 0x00])
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

    humidity_percent: float | None

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
        # PROTOCOL QUIRK: 0x00, 0xEF, and 0xFF are protocol sentinel
        # null-markers indicating an uninstalled or absent humidity
        # sensor. Zero atmospheric humidity (0.0%) is physically
        # impossible. Normalise sentinel bytes to None to prevent
        # invalid 0.0% domain states (see ramses-rf/ramses_cc#742).
        hum = None if raw_val in (0x00, 0xEF, 0xFF) else raw_val / 2.0
        return cls(humidity_percent=hum)

    def to_bytes(self) -> bytes:
        """Pack relative humidity data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        if self.humidity_percent is None:
            return bytes([0x00])
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
    :param mode_idx: Selected fan mode integer index, or None if unconfigured.
    :type mode_idx: int | None
    :param mode_max: Maximum supported fan mode integer index, or None if unconfigured.
    :type mode_max: int | None
    """

    header: int
    mode_idx: int | None
    mode_max: int | None

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
        raw_idx = raw_data[1]
        raw_max = raw_data[2]
        # PROTOCOL QUIRK: 0xFF, 0xFE, and 0xEF are protocol sentinel
        # null-markers indicating unconfigured or unrecognised fan mode
        # indices. Normalise sentinel bytes to None to preserve clean
        # mode representations (see ramses-rf/ramses_cc#723).
        mode_idx = None if raw_idx in (0xEF, 0xFE, 0xFF) else raw_idx
        mode_max = None if raw_max in (0xEF, 0xFE, 0xFF) else raw_max
        return cls(header=raw_data[0], mode_idx=mode_idx, mode_max=mode_max)

    def to_bytes(self) -> bytes:
        """Pack fan mode data into 3-byte binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        raw_idx = 0xFF if self.mode_idx is None else self.mode_idx
        raw_max = 0xFF if self.mode_max is None else self.mode_max
        return bytes([self.header, raw_idx, raw_max])


@register_payload("2411")
@dataclass(frozen=True, slots=True)
class HvacFanParamPayload(PayloadBase):
    """HVAC fan parameters payload (Opcode 2411).

    23-byte HVAC Fan Parameter binary layout (Big-Endian):
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Header / Flag byte           : 00
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

    Protocol Notes:
      # See: ramses-rf/ramses_rf#830
      # 4-byte boolean parameter values: 0 = False, 1 = True.
      # Sentinel values (e.g. 0x000000FF, 0xFFFFFFFF) indicate parameter N/A.

    :param param_id: Fan parameter identifier integer.
    :type param_id: int
    :param data_type: Parameter data type integer.
    :type data_type: int
    :param value_scaled: Current scaled parameter value integer, or None if sentinel/N/A.
    :type value_scaled: int | None
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
    value_scaled: int | None
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
        if len(raw_data) < 22:
            raise ValueError(f"Invalid payload length for 2411: {len(raw_data)}")
        parse_data = raw_data if len(raw_data) >= 23 else raw_data + b"\x20"
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
            # Unpack struct layout directly from offset 0 without buffer slicing
        ) = struct.unpack_from(cls._STRUCT_FMT, parse_data, 0)
        # PROTOCOL QUIRK: Sentinel values (e.g. 0x000000FF, 0xFFFFFFFF, -1)
        # indicate parameter N/A or unconfigured hardware setting.
        # Normalise sentinel values to None to prevent invalid parameter
        # states (see ramses-rf/ramses_rf#830).
        val_scaled = None if val_s in (0x000000FF, 0xFFFFFFFF, -1) else val_s
        return cls(
            param_id=p_id,
            data_type=d_type,
            value_scaled=val_scaled,
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
        val_s = -1 if self.value_scaled is None else self.value_scaled
        return struct.pack(
            self._STRUCT_FMT,
            0,
            self.param_id,
            0,
            self.data_type,
            val_s,
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
        # Unpack 16-bit unsigned air quality AQI directly from offset 0
        (aqi,) = struct.unpack_from(">H", raw_data, 0)
        return cls(air_quality_aqi=aqi)

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


@register_payload("12B0")
@dataclass(frozen=True, slots=True)
class WindowStatePayload(PayloadBase):
    """Window open state sensor payload (Opcode 12B0).

    3-byte Window State binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Zone Index (uint8)           : 00
      +1       B      1B   Window Open Flag (0=No,1=Yes): 00
      +2       B      1B   Trailing Flag Byte           : 00
      --------------------------------------------------------------
      Field-spaced hex : 00 00 00
      Payload hex      : 000000

    :param zone_idx: Zone index byte.
    :type zone_idx: int
    :param window_open: Window open status boolean, or None if unknown.
    :type window_open: bool | None
    """

    zone_idx: int
    window_open: bool | None

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack window state binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked WindowStatePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 12B0: {len(raw_data)}")
        val = None if raw_data[1:] == b"\xff\xff" else bool(raw_data[1])
        return cls(zone_idx=raw_data[0], window_open=val)

    def to_bytes(self) -> bytes:
        """Pack window state data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        if self.window_open is None:
            return bytes([self.zone_idx]) + b"\xff\xff"
        return bytes([self.zone_idx, int(self.window_open), 0x00])


@register_payload("2209")
@register_payload("22C9")
@dataclass(frozen=True, slots=True)
class SetpointBoundsPayload(PayloadBase):
    """Temperature setpoint bounds payload (Opcode 2209, 22C9).

    6-byte Setpoint Bounds binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   UFH / Zone Index             : 00
      +1       h      2B   Min Temp (int16*100)         : 01 F4 (5.00°C)
      +3       h      2B   Max Temp (int16*100)         : 0E 10 (36.00°C)
      +5       B      1B   Mode Code (uint8)            : 01 (Heat)
      --------------------------------------------------------------
      Field-spaced hex : 00 01F4 0E10 01
      Payload hex      : 0001F40E1001

    :param ufh_idx: UFH or zone index byte.
    :type ufh_idx: int
    :param min_temp: Minimum setpoint temperature bound in °C.
    :type min_temp: float
    :param max_temp: Maximum setpoint temperature bound in °C.
    :type max_temp: float
    :param mode_code: Mode code integer.
    :type mode_code: int
    """

    ufh_idx: int
    min_temp: float
    max_temp: float
    mode_code: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack setpoint bounds binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked SetpointBoundsPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 6 bytes.
        """
        if len(raw_data) < 6:
            raise ValueError(f"Invalid payload length for 22C9: {len(raw_data)}")
        # Unpack ufh_idx, min_temp, max_temp, mode_code directly from offset 0
        idx, min_t, max_t, mode_code = struct.unpack_from(">BhhB", raw_data, 0)
        return cls(
            ufh_idx=idx,
            min_temp=min_t / 100.0,
            max_temp=max_t / 100.0,
            mode_code=mode_code,
        )

    def to_bytes(self) -> bytes:
        """Pack setpoint bounds data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        min_b = int(round(self.min_temp * 100.0)).to_bytes(
            2, byteorder="big", signed=True
        )
        max_b = int(round(self.max_temp * 100.0)).to_bytes(
            2, byteorder="big", signed=True
        )
        return bytes([self.ufh_idx]) + min_b + max_b + bytes([self.mode_code])


@register_payload("2249")
@dataclass(frozen=True, slots=True)
class NowNextSetpointPayload(PayloadBase):
    """Current and upcoming setpoint payload (Opcode 2249).

    7-byte Now/Next Setpoint binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Zone Index (uint8)           : 00
      +1       h      2B   Setpoint Now (int16*100)     : 08 34 (21.00°C)
      +3       h      2B   Setpoint Next (int16*100)    : 07 D0 (20.00°C)
      +5       H      2B   Minutes Remaining uint16     : 00 3C (60m)
      --------------------------------------------------------------
      Field-spaced hex : 00 0834 07D0 003C
      Payload hex      : 00083407D0003C

    :param zone_idx: Zone index byte.
    :type zone_idx: int
    :param setpoint_now: Current target setpoint temperature in °C.
    :type setpoint_now: float
    :param setpoint_next: Upcoming scheduled setpoint temperature in °C.
    :type setpoint_next: float
    :param minutes_remaining: Minutes remaining until next switchpoint.
    :type minutes_remaining: int
    """

    zone_idx: int
    setpoint_now: float
    setpoint_next: float
    minutes_remaining: int

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack now/next setpoint binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked NowNextSetpointPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 7 bytes.
        """
        if len(raw_data) < 7:
            raise ValueError(f"Invalid payload length for 2249: {len(raw_data)}")
        # Unpack zone_idx, setpoint_now, setpoint_next, mins directly from offset 0
        idx, sp_now, sp_next, mins = struct.unpack_from(">BhhH", raw_data, 0)
        return cls(
            zone_idx=idx,
            setpoint_now=sp_now / 100.0,
            setpoint_next=sp_next / 100.0,
            minutes_remaining=mins,
        )

    def to_bytes(self) -> bytes:
        """Pack now/next setpoint data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        now_b = int(round(self.setpoint_now * 100.0)).to_bytes(
            2, byteorder="big", signed=True
        )
        next_b = int(round(self.setpoint_next * 100.0)).to_bytes(
            2, byteorder="big", signed=True
        )
        min_b = self.minutes_remaining.to_bytes(2, byteorder="big")
        return bytes([self.zone_idx]) + now_b + next_b + min_b


@register_payload("22D0")
@dataclass(frozen=True, slots=True)
class UfhSystemModePayload(PayloadBase):
    """Underfloor heating system mode payload (Opcode 22D0).

    2-byte UFH System Mode binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   UFH Index (uint8)            : 00
      +1       B      1B   Mode Flags (uint8)           : 14
      --------------------------------------------------------------
      Field-spaced hex : 00 14
      Payload hex      : 0014

    :param idx: UFH index byte.
    :type idx: int
    :param flags: Raw mode flags byte.
    :type flags: int
    :param cool_mode: Cool mode enabled flag boolean.
    :type cool_mode: bool
    :param heat_mode: Heat mode enabled flag boolean.
    :type heat_mode: bool
    :param is_active: UFH active status flag boolean.
    :type is_active: bool
    """

    idx: int
    flags: int
    cool_mode: bool
    heat_mode: bool
    is_active: bool

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack UFH system mode binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked UfhSystemModePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 22D0: {len(raw_data)}")
        flg = raw_data[1]
        return cls(
            idx=raw_data[0],
            flags=flg,
            cool_mode=bool(flg & 0x02),
            heat_mode=bool(flg & 0x04),
            is_active=bool(flg & 0x10),
        )

    def to_bytes(self) -> bytes:
        """Pack UFH system mode data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.idx, self.flags])


@register_payload("22D9")
@dataclass(frozen=True, slots=True)
class DesiredBoilerSetpointPayload(PayloadBase):
    """Target boiler setpoint temperature payload (Opcode 22D9).

    3-byte Desired Boiler Setpoint binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Domain / Zone Index (uint8)  : 00
      +1       h      2B   Target Temp (int16*100)      : 19 64 (65.00°C)
      --------------------------------------------------------------
      Field-spaced hex : 00 1964
      Payload hex      : 001964

    :param domain_or_zone_idx: Domain or zone index byte.
    :type domain_or_zone_idx: int
    :param target_temp: Target boiler temperature setpoint in °C.
    :type target_temp: float
    """

    domain_or_zone_idx: int
    target_temp: float

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack desired boiler setpoint binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked DesiredBoilerSetpointPayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 3 bytes.
        """
        if len(raw_data) < 3:
            raise ValueError(f"Invalid payload length for 22D9: {len(raw_data)}")
        t_raw = int.from_bytes(raw_data[1:3], byteorder="big", signed=True)
        return cls(
            domain_or_zone_idx=raw_data[0],
            target_temp=t_raw / 100.0,
        )

    def to_bytes(self) -> bytes:
        """Pack desired boiler setpoint data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        t_raw = int(round(self.target_temp * 100.0))
        return bytes([self.domain_or_zone_idx]) + t_raw.to_bytes(
            2, byteorder="big", signed=True
        )


@register_payload("2D49")
@dataclass(frozen=True, slots=True)
class CoolingStatePayload(PayloadBase):
    """Cooling relay state payload (Opcode 2D49).

    2-byte Cooling State binary layout:
      Offset  Format  Len  Description                    Sample Hex
      --------------------------------------------------------------
      +0       B      1B   Domain / Zone Index (uint8)  : 00
      +1       B      1B   Cooling Active (0=No, 1=Yes) : 01
      --------------------------------------------------------------
      Field-spaced hex : 00 01
      Payload hex      : 0001

    :param domain_or_zone_idx: Domain or zone index byte.
    :type domain_or_zone_idx: int
    :param state: Cooling state boolean.
    :type state: bool
    """

    domain_or_zone_idx: int
    state: bool

    @classmethod
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack cooling state binary payload.

        :param raw_data: Raw binary byte string.
        :type raw_data: bytes
        :returns: Unpacked CoolingStatePayload instance.
        :rtype: Self
        :raises ValueError: If raw_data length is less than 2 bytes.
        """
        if len(raw_data) < 2:
            raise ValueError(f"Invalid payload length for 2D49: {len(raw_data)}")
        return cls(
            domain_or_zone_idx=raw_data[0],
            state=bool(raw_data[1]),
        )

    def to_bytes(self) -> bytes:
        """Pack cooling state data into binary payload.

        :returns: Packed binary payload bytes.
        :rtype: bytes
        """
        return bytes([self.domain_or_zone_idx, 0xC8 if self.state else 0x00])
