#!/usr/bin/env python3
"""RAMSES RF - a RAMSES-II protocol decoder & analyser."""

from __future__ import annotations

from datetime import timedelta as td
from enum import IntEnum
from typing import Final

from ramses_tx.const import (
    DEFAULT_MAX_ZONES as DEFAULT_MAX_ZONES,
    DEV_ROLE_MAP as DEV_ROLE_MAP,
    DEV_TYPE_MAP as DEV_TYPE_MAP,
    DEVICE_ID_REGEX as DEVICE_ID_REGEX,
    DOMAIN_TYPE_MAP as DOMAIN_TYPE_MAP,
    F9 as F9,
    FA as FA,
    FAN_MODE as FAN_MODE,  # deprecated, use SZ_FAN_MODE, to be removed in Q1 2026
    FC as FC,
    FF as FF,
    I_ as I_,
    RP as RP,
    RQ as RQ,
    SYS_MODE_MAP as SYS_MODE_MAP,
    SZ_ACCEPT as SZ_ACCEPT,
    SZ_ACTIVE as SZ_ACTIVE,
    SZ_ACTUATOR_ENABLED as SZ_ACTUATOR_ENABLED,
    SZ_ACTUATORS as SZ_ACTUATORS,
    SZ_BATTERY_LEVEL as SZ_BATTERY_LEVEL,
    SZ_BATTERY_LOW as SZ_BATTERY_LOW,
    SZ_BATTERY_STATE as SZ_BATTERY_STATE,
    SZ_CONFIRM as SZ_CONFIRM,
    SZ_DATETIME as SZ_DATETIME,
    SZ_DEVICE_ID as SZ_DEVICE_ID,
    SZ_DEVICE_ROLE as SZ_DEVICE_ROLE,
    SZ_DEVICES as SZ_DEVICES,
    SZ_DHW_IDX as SZ_DHW_IDX,
    SZ_DIFFERENTIAL as SZ_DIFFERENTIAL,
    SZ_DOMAIN_ID as SZ_DOMAIN_ID,
    SZ_DURATION as SZ_DURATION,
    SZ_FLAME_ON as SZ_FLAME_ON,
    SZ_HEAT_DEMAND as SZ_HEAT_DEMAND,
    SZ_LANGUAGE as SZ_LANGUAGE,
    SZ_MODE as SZ_MODE,
    SZ_MODULATION_LEVEL as SZ_MODULATION_LEVEL,
    SZ_NAME as SZ_NAME,
    SZ_OEM_CODE as SZ_OEM_CODE,
    SZ_OFFER as SZ_OFFER,
    SZ_OVERRUN as SZ_OVERRUN,
    SZ_PAYLOAD as SZ_PAYLOAD,
    SZ_PHASE as SZ_PHASE,
    SZ_PRESSURE as SZ_PRESSURE,
    SZ_RELAY_DEMAND as SZ_RELAY_DEMAND,
    SZ_RELAY_FAILSAFE as SZ_RELAY_FAILSAFE,
    SZ_SENSOR as SZ_SENSOR,
    SZ_SETPOINT as SZ_SETPOINT,
    SZ_SETPOINT_BOUNDS as SZ_SETPOINT_BOUNDS,
    SZ_SYSTEM_MODE as SZ_SYSTEM_MODE,
    SZ_TEMP_HIGH as SZ_TEMP_HIGH,
    SZ_TEMP_LOW as SZ_TEMP_LOW,
    SZ_TEMPERATURE as SZ_TEMPERATURE,
    SZ_UFH_IDX as SZ_UFH_IDX,
    SZ_UNKNOWN as SZ_UNKNOWN,
    SZ_UNTIL as SZ_UNTIL,
    SZ_VALUE as SZ_VALUE,
    SZ_WINDOW_OPEN as SZ_WINDOW_OPEN,
    SZ_ZONE_CLASS as SZ_ZONE_CLASS,
    SZ_ZONE_IDX as SZ_ZONE_IDX,
    SZ_ZONE_MASK as SZ_ZONE_MASK,
    SZ_ZONE_TYPE as SZ_ZONE_TYPE,
    SZ_ZONES as SZ_ZONES,
    W_ as W_,
    ZON_MODE_MAP as ZON_MODE_MAP,
    ZON_ROLE_MAP as ZON_ROLE_MAP,
    Code as Code,
    DevRole as DevRole,
    DevType as DevType,
    IndexT as IndexT,
    SystemType as SystemType,
    VerbT as VerbT,
    ZoneRole as ZoneRole,
)

# used by schedule.py...
SZ_FRAGMENT: Final = "fragment"
SZ_FRAG_NUMBER: Final = "frag_number"
SZ_FRAG_LENGTH: Final = "frag_length"
SZ_TOTAL_FRAGS: Final = "total_frags"

SZ_SCHEDULE: Final = "schedule"
SZ_CHANGE_COUNTER: Final = "change_counter"

SZ_SENSOR_FAULT: Final = "sensor_fault"


# used by 31DA (HVAC)
SZ_AIR_QUALITY: Final = "air_quality"
SZ_AIR_QUALITY_BASIS: Final = "air_quality_basis"
SZ_BOOST_TIMER: Final = "boost_timer"
SZ_BYPASS_MODE: Final = "bypass_mode"
SZ_BYPASS_POSITION: Final = "bypass_position"
SZ_BYPASS_STATE: Final = "bypass_state"
SZ_CO2_LEVEL: Final = "co2_level"
SZ_DEWPOINT_TEMP: Final = "dewpoint_temp"
SZ_EXHAUST_FAN_SPEED: Final = "exhaust_fan_speed"
SZ_EXHAUST_FLOW: Final = "exhaust_flow"
SZ_EXHAUST_TEMP: Final = "exhaust_temp"
SZ_FAN_INFO: Final = "fan_info"
SZ_FAN_MODE: Final = "fan_mode"
SZ_FAN_RATE: Final = "fan_rate"
SZ_FILTER_DIRTY: Final = "filter_dirty"
SZ_FROST_CYCLE: Final = "frost_cycle"
SZ_HAS_FAULT: Final = "has_fault"
SZ_FILTER_REMAINING: Final = "filter_remaining"
SZ_FILTER_REMAINING_PERCENT: Final = "filter_remaining_percent"
SZ_INDOOR_HUMIDITY: Final = "indoor_humidity"
SZ_INDOOR_TEMP: Final = "indoor_temp"
SZ_MINUTES: Final = "minutes"
SZ_OUTDOOR_HUMIDITY: Final = "outdoor_humidity"
SZ_OUTDOOR_TEMP: Final = "outdoor_temp"
SZ_POST_HEAT: Final = "post_heat"
SZ_PRE_HEAT: Final = "pre_heat"
SZ_PRESENCE_DETECTED: Final = "presence_detected"
SZ_REL_HUMIDITY: Final = "rel_humidity"
SZ_REMAINING_DAYS: Final = "days_remaining"
SZ_REMAINING_MINS: Final = "remaining_mins"
SZ_REMAINING_PERCENT: Final = "percent_remaining"
SZ_REQ_REASON: Final = "req_reason"
SZ_REQ_SPEED: Final = "req_speed"
SZ_SUPPLY_FAN_SPEED: Final = "supply_fan_speed"
SZ_SUPPLY_FLOW: Final = "supply_flow"
SZ_SUPPLY_TEMP: Final = "supply_temp"
SZ_SPEED_CAPABILITIES: Final = "speed_capabilities"


# used by OTB (OpenTherm Bridge)
SZ_BURNER_HOURS: Final = "burner_hours"
SZ_BURNER_STARTS: Final = "burner_starts"
SZ_BURNER_FAILED_STARTS: Final = "burner_failed_starts"
SZ_CH_PUMP_HOURS: Final = "ch_pump_hours"
SZ_CH_PUMP_STARTS: Final = "ch_pump_starts"
SZ_DHW_BURNER_HOURS: Final = "dhw_burner_hours"
SZ_DHW_BURNER_STARTS: Final = "dhw_burner_starts"
SZ_DHW_PUMP_HOURS: Final = "dhw_pump_hours"
SZ_DHW_PUMP_STARTS: Final = "dhw_pump_starts"
SZ_FLAME_SIGNAL_LOW: Final = "flame_signal_low"

SZ_BOILER_OUTPUT_TEMP: Final = "boiler_output_temp"
SZ_BOILER_RETURN_TEMP: Final = "boiler_return_temp"
SZ_BOILER_SETPOINT: Final = "boiler_setpoint"
SZ_CH_MAX_SETPOINT: Final = "ch_max_setpoint"
SZ_CH_SETPOINT: Final = "ch_setpoint"
SZ_CH_WATER_PRESSURE: Final = "ch_water_pressure"
SZ_DHW_FLOW_RATE: Final = "dhw_flow_rate"
SZ_DHW_SETPOINT: Final = "dhw_setpoint"
SZ_DHW_TEMP: Final = "dhw_temp"
SZ_MAX_REL_MODULATION: Final = "max_rel_modulation"
# SZ_OEM_CODE:Final[str] = "oem_code"
SZ_OUTSIDE_TEMP: Final = "outside_temp"
SZ_REL_MODULATION_LEVEL: Final = "rel_modulation_level"

SZ_CH_ACTIVE: Final = "ch_active"
SZ_CH_ENABLED: Final = "ch_enabled"
SZ_COOLING_ACTIVE: Final = "cooling_active"
SZ_COOLING_ENABLED: Final = "cooling_enabled"
SZ_DHW_ACTIVE: Final = "dhw_active"
SZ_DHW_BLOCKING: Final = "dhw_blocking"
SZ_DHW_ENABLED: Final = "dhw_enabled"
SZ_FAULT_PRESENT: Final = "fault_present"
SZ_FLAME_ACTIVE: Final = "flame_active"
SZ_SUMMER_MODE: Final = "summer_mode"
SZ_OTC_ACTIVE: Final = "otc_active"


# used by heat actuators / cycling
SZ_ACTUATOR_COUNTDOWN: Final = "actuator_countdown"
SZ_COOL_ACTIVE: Final = "cool_active"
SZ_CYCLE_COUNTDOWN: Final = "cycle_countdown"

__dev_mode__ = False  # NOTE: this is const.py


class Discover(IntEnum):
    """Flags for the discovery process."""

    NOTHING = 0
    SCHEMA = 1
    PARAMS = 2
    STATUS = 4
    FAULTS = 8
    SCHEDS = 16
    TRAITS = 32
    DEFAULT = 1 + 2 + 4


DONT_CREATE_MESSAGES: Final[int] = 3
DONT_CREATE_ENTITIES: Final[int] = 2
DONT_UPDATE_ENTITIES: Final[int] = 1

SZ_DISABLE_POLLING: Final = "disable_polling"
SZ_DISABLE_DISCOVERY: Final = "disable_discovery"
SZ_IS_BATTERY: Final = "is_battery"
SZ_POLLING_INTERVAL: Final = "polling_interval"

SCHED_REFRESH_INTERVAL: Final[int] = 3  # minutes

# 0004 (zone_name) and 1060 (device_battery) are intentionally excluded:
# they are low-volume (sent every ~6h and ~1/day respectively) and carry
# semi-static state.  Classifying them as high-volume caused cached packets
# older than 1h to be skipped during _restore_cached_packets, so zone names
# were lost on restart (issue 822) and battery states went Unknown after
# restart (issue 840 — battery devices send 1060 only 1/day, so the cached
# 1060 is almost always >1h old and was silently dropped on restore).
# See:
#   - https://github.com/ramses-rf/ramses_cc/issues/822  (0004 zone_name)
#   - https://github.com/ramses-rf/ramses_cc/issues/840  (1060 battery)
HIGH_VOLUME_STATUS_CODES: Final = (
    Code._2309,
    Code._2349,
    Code._30C9,
)

# Status codes for Worcester Bosch boilers - OT|OEM diagnostic code
WB_STATUS_CODES: Final[dict[str, str]] = {
    "200": "CH system is being heated.",
    "201": "DHW system is being heated.",
    "202": (
        "Anti rapid cycle mode. The boiler has commenced anti-cycle period for CH."
    ),
    "203": "System standby mode.",
    "204": "System waiting, appliance waiting for heating system to cool.",
    "208": "Appliance in service Test mode (Min/Max)",
    "265": (
        "EMS controller has forced stand-by-mode due to low heating "
        "load (power required is less than the minimum output)"
    ),
    "268": (
        "Component test mode (is running the manual component test as "
        "activated in the menus)."
    ),
    "270": "Power up mode (appliance is powering up).",
    "283": "Burner starting. The fan and the pump are being controlled.",
    "284": (
        "Gas valve(s) opened, flame must be detected within safety "
        "time. The gas valve is being controlled."
    ),
    "305": (
        "Anti fast cycle mode (DHW keep warm function). Diverter valve "
        "is held in DHW position for a period of time after DHW demand."
    ),
    "357": (
        "Appliance in air purge mode. Primary heat exchanger air "
        "venting program active - approximately 100 seconds."
    ),
    "358": (
        "Three way valve kick. If the 3-way valve hasn't moved in "
        "within 48 hours, the valve will operate once to prevent "
        "seizure"
    ),
}

# Device Availability Timeouts
HEARTBEAT_TIMEOUT_DEFAULT = td(hours=1)
HEARTBEAT_TIMEOUT_FILTER = td(hours=24)
HEARTBEAT_TIMEOUT_OTB = td(hours=24)
HEARTBEAT_TIMEOUT_TRV = td(hours=12)
HEARTBEAT_TIMEOUT_REMOTE = td(hours=24)
HEARTBEAT_TIMEOUT_SENSOR = td(hours=12)
GATEWAY_MESSAGE_TIMEOUT: td = td(minutes=10)
