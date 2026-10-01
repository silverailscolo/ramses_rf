"""RAMSES RF - OpenTherm state models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime as dt


@dataclass(frozen=True)
class OpenThermFlags:
    """Immutable representation of OpenTherm status flags."""

    ch_active: bool | None = None
    ch_enabled: bool | None = None
    cooling_active: bool | None = None
    cooling_enabled: bool | None = None
    dhw_active: bool | None = None
    dhw_blocking: bool | None = None
    dhw_enabled: bool | None = None
    fault_present: bool | None = None
    flame_active: bool | None = None
    otc_active: bool | None = None
    summer_mode: bool | None = None


@dataclass(frozen=True)
class OpenThermFaultFlags:
    """Immutable representation of OpenTherm application fault flags.

    Mirrors msg_id 0x05 high-byte bits 0-5 (LSB-first).
    """

    service_request: bool | None = None
    lockout_reset: bool | None = None
    low_water_pressure: bool | None = None
    gas_flame_fault: bool | None = None
    air_pressure_fault: bool | None = None
    water_over_temperature: bool | None = None


@dataclass(frozen=True)
class OpenThermTemperatures:
    """Immutable representation of OpenTherm temperatures."""

    boiler_exhaust: float | None = None
    boiler_output: float | None = None
    boiler_return: float | None = None
    boiler_setpoint: float | None = None
    ch_max_setpoint: float | None = None
    ch_setpoint: float | None = None
    dhw: float | None = None
    dhw_setpoint: float | None = None
    outside: float | None = None


@dataclass(frozen=True)
class OpenThermCounters:
    """Immutable representation of OpenTherm counters."""

    burner_failed_starts: int | None = None
    burner_hours: int | None = None
    burner_starts: int | None = None
    ch_pump_hours: int | None = None
    ch_pump_starts: int | None = None
    dhw_burner_hours: int | None = None
    dhw_burner_starts: int | None = None
    dhw_pump_hours: int | None = None
    dhw_pump_starts: int | None = None
    flame_signal_low: int | None = None


@dataclass(frozen=True, slots=True)
class OpenThermState:
    """The immutable state of an OpenTherm Bridge (OTB) boiler matrix."""

    last_updated: dt | None = None
    flags: OpenThermFlags = field(default_factory=OpenThermFlags)
    faults: OpenThermFaultFlags = field(default_factory=OpenThermFaultFlags)
    temperatures: OpenThermTemperatures = field(
        default_factory=OpenThermTemperatures
    )
    counters: OpenThermCounters = field(default_factory=OpenThermCounters)
    ch_water_pressure: float | None = None
    dhw_flow_rate: float | None = None
    max_rel_modulation: float | None = None
    rel_modulation_level: float | None = None
    oem_code: int | None = None
    oem_fault_code: int | None = None
