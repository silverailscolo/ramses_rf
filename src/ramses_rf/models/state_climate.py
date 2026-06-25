"""RAMSES RF - Climate/Heating state models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime as dt

from .state_base import _now_utc

# --- Compositional State Blocks ---


@dataclass(frozen=True, slots=True)
class TemperatureState:
    """State for entities that measure or target temperature."""

    temperature: float | None = None
    setpoint: float | None = None
    last_updated: dt = field(default_factory=_now_utc)


@dataclass(frozen=True, slots=True)
class TrvState:
    """State for TRV (Thermostatic Radiator Valve) entities."""

    window_open: bool | None = None
    last_updated: dt = field(default_factory=_now_utc)


@dataclass(frozen=True, slots=True)
class DemandState:
    """State for entities that request or actuate heat/cooling."""

    heat_demand: float | None = None
    relay_active: bool = False
    relay_demand: float | None = None
    relay_failsafe: bool | None = None
    last_updated: dt = field(default_factory=_now_utc)


@dataclass(frozen=True, slots=True)
class DhwState:
    """State for DHW (Domestic Hot Water) entities."""

    setpoint: float | None = None
    overrun: int | None = None
    differential: float | None = None
    mode: str | None = None
    active: bool | None = None
    until: dt | str | None = None
    temperature: float | None = None
    last_updated: dt = field(default_factory=_now_utc)


@dataclass(frozen=True, slots=True)
class SystemState:
    """State for central system controllers."""

    system_mode: str | None = None
    until: dt | str | None = None
    datetime: str | None = None
    language: str | None = None
    last_updated: dt = field(default_factory=_now_utc)


@dataclass(frozen=True, slots=True)
class PowerState:
    """Power and battery state for wireless entities."""

    battery_low: bool | None = None
    battery_level: float | None = None
    last_updated: dt = field(default_factory=_now_utc)


@dataclass(frozen=True, slots=True)
class ZoneState:
    """State for standard heating zones."""

    mode: str | None = None
    setpoint: float | None = None
    until: dt | str | None = None
    min_temp: float | None = None
    max_temp: float | None = None
    local_override: bool | None = None
    openwindow_function: bool | None = None
    multiroom_mode: bool | None = None
    last_updated: dt = field(default_factory=_now_utc)
