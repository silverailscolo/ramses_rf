#!/usr/bin/env python3
"""RAMSES RF - Data models and configuration objects."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime as dt
from typing import Any

from ramses_rf.enums import TopologyAction
from ramses_rf.typing import DeviceIdT


@dataclass
class DeviceTraits:
    """Strictly typed traits for device instantiation."""

    device_class: str | None = None
    alias: str | None = None
    faked: bool | None = None
    scheme: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeviceTraits:
        """Construct DeviceTraits safely from a dynamically parsed
        dictionary.
        """
        return cls(
            device_class=data.get("class"),
            alias=data.get("alias"),
            faked=data.get("faked"),
            scheme=data.get("scheme"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize back to a dictionary.

        Useful for bridging the boundary into legacy methods expecting
        **kwargs.
        """
        result: dict[str, Any] = {}
        if self.device_class is not None:
            result["class"] = self.device_class
        if self.alias is not None:
            result["alias"] = self.alias
        if self.faked is not None:
            result["faked"] = self.faked
        if self.scheme is not None:
            result["scheme"] = self.scheme
        return result


def _now_utc() -> dt:
    """Return the current timezone-aware UTC datetime.

    This helper function is required for dataclass default factories.
    If `default=dt.now(UTC)` is used directly in a dataclass field,
    Python evaluates the function exactly once when the module is
    imported. As a result, every event instantiated during the
    runtime would share the exact same timestamp. By providing this
    zero-argument callable to `default_factory`, we ensure a fresh,
    accurate timestamp is generated every time an object is created.
    """
    return dt.now(UTC)


@dataclass(frozen=True, slots=True)
class TopologyChangedEvent:
    """Immutable event representing a structural change in the network
    graph.
    """

    # The structural action to perform
    action: TopologyAction

    # -- Entity Identifiers (Populated based on the Action) --

    # Used for single-device actions (e.g., PROMOTE_CLASS, UPDATE_TRAITS)
    device_id: DeviceIdT | None = None

    # Used together for structural relationship actions (e.g., BIND_DEVICE)
    parent_id: DeviceIdT | None = None
    child_id: DeviceIdT | None = None

    # -- Context & Observability --

    # Flexible domain-specific metadata (e.g., {"zone_idx": "01",
    # "is_sensor": True})
    metadata: dict[str, str | int | float | bool] = field(default_factory=dict)

    # The Tracing Triad (Observability & Debugging)
    event_id: uuid.UUID = field(default_factory=uuid.uuid4)
    correlation_id: uuid.UUID = field(default_factory=uuid.uuid4)
    # causation identifies the rule/engine that generated this guess
    # (e.g., "Rule_000C")
    causation: str = "TopologyBuilder"

    timestamp: dt = field(default_factory=_now_utc)


# --- Phase 2.95: CQRS Domain Read-Models and Events ---


@dataclass(frozen=True, slots=True)
class StateUpdatedEvent:
    """An immutable event representing a state update for an entity.

    Includes the OpenTelemetry tracing triad to guarantee perfect
    observability of the event lineage.
    """

    entity_id: str
    state: Any
    event_id: uuid.UUID = field(default_factory=uuid.uuid4)
    correlation_id: uuid.UUID = field(default_factory=uuid.uuid4)
    causation_id: uuid.UUID = field(default_factory=uuid.uuid4)
    timestamp: dt = field(default_factory=_now_utc)


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


# --- Nested Value Objects for Schedules ---


@dataclass(frozen=True, slots=True)
class SwitchPoint:
    """A single schedule setpoint rule."""

    time_of_day: str
    setpoint: float | None = None
    enabled: bool | None = None


@dataclass(frozen=True, slots=True)
class DailySchedule:
    """A daily schedule block containing immutable switchpoints."""

    day_of_week: int
    switchpoints: tuple[SwitchPoint, ...]


@dataclass(frozen=True, slots=True)
class ScheduleState:
    """The immutable state of a zone's 7-day schedule."""

    zone_idx: str
    days: tuple[DailySchedule, ...]
    version: int | None = None
    is_current: bool = False
    last_updated: dt = field(default_factory=_now_utc)


# --- Stateful Fault Logs ---


@dataclass(frozen=True, slots=True)
class FaultLogEntry:
    """An immutable record of a specific system fault."""

    timestamp: str
    fault_state: str  # e.g., "Restore", "Fault"
    fault_type: str
    domain_id: str | None = None
    device_id: str | None = None


@dataclass(frozen=True, slots=True)
class FaultLogState:
    """The immutable state of the system's 64-slot fault log."""

    entries: tuple[FaultLogEntry, ...] = field(default_factory=tuple)
    is_current: bool = False
    last_updated: dt = field(default_factory=_now_utc)

    @property
    def latest_fault(self) -> FaultLogEntry | None:
        """Convenience pointer for API consumers to grab the newest fault."""
        return self.entries[-1] if self.entries else None


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


@dataclass(frozen=True, slots=True)
class HvacState:
    """The immutable state of an HVAC ventilation or fan entity."""

    co2_level: int | None = None
    air_quality: float | None = None
    air_quality_basis: float | None = None
    bypass_mode: str | None = None
    bypass_position: float | str | None = None
    bypass_state: str | None = None
    exhaust_fan_speed: float | None = None
    exhaust_flow: float | None = None
    exhaust_temp: float | None = None
    fan_rate: str | None = None
    fan_mode: str | None = None
    fan_info: str | None = None
    indoor_humidity: float | None = None
    indoor_temp: float | None = None
    outdoor_humidity: float | None = None
    outdoor_temp: float | None = None
    post_heat: int | None = None
    pre_heat: int | None = None
    remaining_mins: int | None = None
    request_fan_speed: float | None = None
    request_reason: str | None = None
    speed_capabilities: int | None = None
    supply_fan_speed: float | None = None
    supply_flow: float | None = None
    supply_temp: float | None = None
    temperature: float | None = None
    dewpoint_temp: float | None = None
    presence_detected: bool | None = None
    filter_remaining_days: int | None = None
    filter_remaining_percent: float | None = None
    boost_timer_mins: int | None = None
    filter_dirty: bool | None = None
    frost_cycle: bool | None = None
    has_fault: bool | None = None

    last_updated: dt = field(default_factory=_now_utc)
