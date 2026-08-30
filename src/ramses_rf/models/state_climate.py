"""RAMSES RF - Climate/Heating state models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime as dt

from ramses_rf.enums import PumpRelayState, ThermalMode

from .state_base import _now_utc

# --- Compositional State Blocks ---


@dataclass(frozen=True, slots=True)
class TemperatureState:
    """State for entities that measure or target temperature.

    Tracks current observed temperature and target setpoint temperature
    readings.

    :param temperature: Observed temperature in degrees Celsius, or
        None.
    :type temperature: float | None
    :param setpoint: Target temperature in degrees Celsius, or None.
    :type setpoint: float | None
    :param last_updated: Timestamp when this state was last updated.
    :type last_updated: dt
    """

    temperature: float | None = None
    setpoint: float | None = None
    last_updated: dt = field(default_factory=_now_utc)


@dataclass(frozen=True, slots=True)
class TrvState:
    """State for TRV (Thermostatic Radiator Valve) entities.

    Tracks radiator valve specific telemetry, including local open
    window detection.

    :param window_open: Boolean indicating open window detection state.
    :type window_open: bool | None
    :param last_updated: Timestamp when this state was last updated.
    :type last_updated: dt
    """

    window_open: bool | None = None
    last_updated: dt = field(default_factory=_now_utc)


@dataclass(frozen=True, slots=True)
class DemandState:
    """State for entities that request or actuate heat/cooling.

    Tracks thermal heat demand and binary or proportioned relay demand
    telemetry.

    :param heat_demand: Proportional heat demand (0.0 to 1.0), or
        None.
    :type heat_demand: float | None
    :param relay_active: Boolean flag indicating active relay output.
    :type relay_active: bool
    :param relay_demand: Proportional relay demand (0.0 to 1.0), or
        None.
    :type relay_demand: float | None
    :param relay_failsafe: Failsafe relay mode status, or None.
    :type relay_failsafe: bool | None
    :param last_updated: Timestamp when this state was last updated.
    :type last_updated: dt
    """

    heat_demand: float | None = None
    relay_active: bool = False
    relay_demand: float | None = None
    relay_failsafe: bool | None = None
    last_updated: dt = field(default_factory=_now_utc)


@dataclass(frozen=True, slots=True)
class DhwState:
    """State for DHW (Domestic Hot Water) entities.

    Tracks hot water cylinder temperature, setpoint, differentials, and
    scheduled operating mode overrides.

    :param setpoint: Target DHW temperature in degrees Celsius, or
        None.
    :type setpoint: float | None
    :param overrun: Hot water pump overrun duration in minutes, or
        None.
    :type overrun: int | None
    :param differential: Temperature deadband differential, or None.
    :type differential: float | None
    :param mode: Hot water operating mode string, or None.
    :type mode: str | None
    :param active: Hot water heating active status, or None.
    :type active: bool | None
    :param until: Scheduled mode expiration datetime or string, or
        None.
    :type until: dt | str | None
    :param temperature: Hot water cylinder temperature in degrees
        Celsius.
    :type temperature: float | None
    :param last_updated: Timestamp when this state was last updated.
    :type last_updated: dt
    """

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
    """State for central system controllers.

    Tracks overall heating controller operating mode, active language,
    system clock datetime, and cooling mode flags.

    :param system_mode: Controller system mode (e.g. 'auto', 'away').
    :type system_mode: str | None
    :param until: Scheduled system mode expiration datetime or string.
    :type until: dt | str | None
    :param datetime: Controller system clock timestamp string, or None.
    :type datetime: str | None
    :param language: Controller display language code string, or None.
    :type language: str | None
    :param cooling_mode: System cooling mode active flag, or None.
    :type cooling_mode: bool | None
    :param last_updated: Timestamp when this state was last updated.
    :type last_updated: dt
    """

    system_mode: str | None = None
    until: dt | str | None = None
    datetime: str | None = None
    language: str | None = None
    cooling_mode: bool | None = None
    last_updated: dt = field(default_factory=_now_utc)


@dataclass(frozen=True, slots=True)
class PowerState:
    """Power and battery state for wireless entities.

    Tracks low battery alert status and remaining battery voltage or
    percentage.

    :param battery_low: Boolean flag indicating low battery condition.
    :type battery_low: bool | None
    :param battery_level: Battery charge percentage (0.0 to 1.0), or
        None.
    :type battery_level: float | None
    :param last_updated: Timestamp when this state was last updated.
    :type last_updated: dt
    """

    battery_low: bool | None = None
    battery_level: float | None = None
    last_updated: dt = field(default_factory=_now_utc)


@dataclass(frozen=True, slots=True)
class ZoneState:
    """State for standard heating zones.

    Tracks zone configuration parameters, setpoint temperature, mode
    overrides, and window detection features.

    :param name: Human-readable name assigned to the heating zone.
    :type name: str | None
    :param mode: Heating mode override string (e.g.
        'temporary_override').
    :type mode: str | None
    :param setpoint: Active target temperature in degrees Celsius, or
        None.
    :type setpoint: float | None
    :param until: Mode override expiration datetime or string, or None.
    :type until: dt | str | None
    :param min_temp: Minimum allowable setpoint temperature, or None.
    :type min_temp: float | None
    :param max_temp: Maximum allowable setpoint temperature, or None.
    :type max_temp: float | None
    :param local_override: Flag indicating setpoint changed at device.
    :type local_override: bool | None
    :param openwindow_function: Flag indicating open window function
        enabled.
    :type openwindow_function: bool | None
    :param multiroom_mode: Flag indicating multi-room mode enabled.
    :type multiroom_mode: bool | None
    :param last_updated: Timestamp when this state was last updated.
    :type last_updated: dt
    """

    name: str | None = None
    mode: str | None = None
    setpoint: float | None = None
    until: dt | str | None = None
    min_temp: float | None = None
    max_temp: float | None = None
    local_override: bool | None = None
    openwindow_function: bool | None = None
    multiroom_mode: bool | None = None
    last_updated: dt = field(default_factory=_now_utc)


@dataclass(frozen=True, slots=True)
class UfhCircuitState:
    """State for an individual Underfloor Heating (UFH) circuit.

    Represents circuit-level telemetry including heat demand, cooling
    demand, operating mode, setpoint temperatures, and zone binding.

    :param ufh_index: Two-character hexadecimal circuit index (e.g.
        '00', '01').
    :type ufh_index: str
    :param zone_index: Associated heating zone index, or None if unmapped.
    :type zone_index: str | None
    :param heat_demand: Heating demand percentage (0.0 to 1.0), or None.
    :type heat_demand: float | None
    :param cooling_demand: Cooling demand percentage (0.0 to 1.0), or
        None.
    :type cooling_demand: float | None
    :param circuit_mode: Circuit operating mode (e.g. ThermalMode.HEAT,
        'cooling'), or None.
    :type circuit_mode: ThermalMode | str | None
    :param setpoint: Target setpoint temperature in degrees Celsius, or
        None.
    :type setpoint: float | None
    :param min_temp: Minimum allowable setpoint temperature, or None.
    :type min_temp: float | None
    :param max_temp: Maximum allowable setpoint temperature, or None.
    :type max_temp: float | None
    :param flags: Raw configuration or mode flag integer, or None.
    :type flags: int | None
    :param last_updated: Timestamp when this circuit state was last
        updated.
    :type last_updated: dt
    """

    ufh_index: str
    zone_index: str | None = None
    heat_demand: float | None = None
    cooling_demand: float | None = None
    circuit_mode: ThermalMode | str | None = None
    setpoint: float | None = None
    min_temp: float | None = None
    max_temp: float | None = None
    flags: int | None = None
    last_updated: dt = field(default_factory=_now_utc)

    @property
    def circuit_index(self) -> str:
        """Return the UFH circuit index string.

        :returns: The UFH circuit index.
        :rtype: str
        """
        return self.ufh_index


@dataclass(frozen=True, slots=True)
class UfhState:
    """State for Underfloor Heating (UFH) controllers.

    Aggregates overall controller relay demand, pump state, and
    individual circuit telemetry mapped by circuit index.

    :param circuits: Dictionary of circuit states keyed by circuit
        index.
    :type circuits: dict[str, UfhCircuitState]
    :param heat_demands: Heating demands keyed by circuit index.
    :type heat_demands: dict[str, float | None]
    :param cooling_demands: Cooling demands keyed by circuit index.
    :type cooling_demands: dict[str, float | None]
    :param circuit_modes: Operating modes keyed by circuit index.
    :type circuit_modes: dict[str, ThermalMode | str | None]
    :param setpoints: Setpoint dictionaries keyed by circuit index.
    :type setpoints: dict[str, dict[str, float | None]]
    :param circuit_to_zone_map: Mapping from circuit index to zone index.
    :type circuit_to_zone_map: dict[str, str | None]
    :param relay_demand_fa: Domain FA boiler relay demand (0.0 to 1.0).
    :type relay_demand_fa: float | None
    :param relay_demand_fc: Domain FC heating relay demand (0.0 to 1.0).
    :type relay_demand_fc: float | None
    :param pump_relay_state: Overall pump relay actuation state.
    :type pump_relay_state: PumpRelayState | None
    :param last_updated: Timestamp when this controller state was last
        updated.
    :type last_updated: dt
    """

    circuits: dict[str, UfhCircuitState] = field(default_factory=dict)
    heat_demands: dict[str, float | None] = field(default_factory=dict)
    cooling_demands: dict[str, float | None] = field(default_factory=dict)
    circuit_modes: dict[str, ThermalMode | str | None] = field(
        default_factory=dict
    )
    setpoints: dict[str, dict[str, float | None]] = field(default_factory=dict)
    circuit_to_zone_map: dict[str, str | None] = field(default_factory=dict)
    relay_demand_fa: float | None = None
    relay_demand_fc: float | None = None
    pump_relay_state: PumpRelayState | None = None
    last_updated: dt = field(default_factory=_now_utc)


@dataclass(frozen=True, slots=True)
class ActuatorState:
    """State for boiler and heating actuators (e.g., BDR91).

    Tracks appliance relay modulation, central heating activation, hot
    water status, flame sensor telemetry, and cycle countdowns.

    :param modulation_level: Active boiler modulation level (0.0 to
        1.0).
    :type modulation_level: float | None
    :param actuator_enabled: Flag indicating actuator relay output
        enabled.
    :type actuator_enabled: bool | None
    :param ch_active: Flag indicating central heating demand active.
    :type ch_active: bool | None
    :param dhw_active: Flag indicating domestic hot water demand
        active.
    :type dhw_active: bool | None
    :param flame_active: Flag indicating active boiler burner flame.
    :type flame_active: bool | None
    :param actuator_countdown: Actuator timeout countdown integer.
    :type actuator_countdown: int | None
    :param cycle_countdown: Heating cycle countdown integer, or None.
    :type cycle_countdown: int | None
    :param last_updated: Timestamp when this state was last updated.
    :type last_updated: dt
    """

    modulation_level: float | None = None
    actuator_enabled: bool | None = None
    ch_active: bool | None = None
    dhw_active: bool | None = None
    flame_active: bool | None = None
    actuator_countdown: int | None = None
    cycle_countdown: int | None = None
    last_updated: dt = field(default_factory=_now_utc)
