"""RAMSES RF - OpenTherm state models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime as dt

from .state_base import _now_utc


@dataclass(frozen=True, slots=True)
class OpenThermState:
    """The immutable state of an OpenTherm Bridge (OTB) boiler matrix."""

    boiler_output_temp: float | None = None
    boiler_return_temp: float | None = None
    boiler_setpoint: float | None = None
    ch_max_setpoint: float | None = None
    ch_setpoint: float | None = None
    ch_water_pressure: float | None = None
    dhw_flow_rate: float | None = None
    dhw_setpoint: float | None = None
    dhw_temp: float | None = None
    max_rel_modulation: float | None = None
    oem_code: float | None = None
    outside_temp: float | None = None
    rel_modulation_level: float | None = None

    # Status Flags
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

    # Counter Metrics
    burner_hours: float | None = None
    burner_starts: float | None = None
    burner_failed_starts: float | None = None
    ch_pump_hours: float | None = None
    ch_pump_starts: float | None = None
    dhw_burner_hours: float | None = None
    dhw_burner_starts: float | None = None
    dhw_pump_hours: float | None = None
    dhw_pump_starts: float | None = None
    flame_signal_low: float | None = None

    last_updated: dt = field(default_factory=_now_utc)
