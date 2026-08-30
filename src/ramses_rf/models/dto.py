"""RAMSES RF - CQRS Data Transfer Objects (DTOs)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime as dt
from typing import Any

from ramses_rf.enums import ThermalMode


@dataclass(frozen=True, slots=True)
class ThermalDemandDTO:
    """CQRS Read-Model representation of zone or system thermal demand.

    :param thermal_demand: Active demand magnitude (0.0 to 1.0) or None.
    :type thermal_demand: float | None
    :param mode: Active thermal mode (HEAT, COOL, OFF).
    :type mode: ThermalMode
    :param ufh_index: Circuit or zone index string if applicable.
    :type ufh_index: str | None
    :param domain_id: System domain identifier if applicable.
    :type domain_id: str | None
    """

    thermal_demand: float | None = None
    mode: ThermalMode = ThermalMode.HEAT
    ufh_index: str | None = None
    domain_id: str | None = None

    @property
    def heating_demand(self) -> float | None:
        """Return heating demand magnitude (0.0 if cooling or off).

        :returns: Demand magnitude for heating mode.
        :rtype: float | None
        """
        if self.thermal_demand is None:
            return None
        return self.thermal_demand if self.mode == ThermalMode.HEAT else 0.0

    @property
    def cooling_demand(self) -> float | None:
        """Return cooling demand magnitude (0.0 if heating or off).

        :returns: Demand magnitude for cooling mode.
        :rtype: float | None
        """
        if self.thermal_demand is None:
            return None
        return self.thermal_demand if self.mode == ThermalMode.COOL else 0.0

    @property
    def heat_demand(self) -> float | None:
        """Deprecated backward compatibility alias for heating_demand.

        :returns: Demand magnitude for heating mode.
        :rtype: float | None
        """
        return self.heating_demand


@dataclass(frozen=True, slots=True)
class UfhCircuitDemandDTO:
    """DTO for an Underfloor Heating (UFH) circuit demand.

    :param ufh_index: Circuit index identifier.
    :type ufh_index: str
    :param thermal_demand: Active demand magnitude (0.0 to 1.0) or None.
    :type thermal_demand: float | None
    :param mode: Active thermal mode (HEAT, COOL, OFF).
    :type mode: ThermalMode
    """

    ufh_index: str
    thermal_demand: float | None = None
    mode: ThermalMode = ThermalMode.HEAT

    @property
    def heating_demand(self) -> float | None:
        """Return heating demand magnitude (0.0 if cooling or off).

        :returns: Demand magnitude for heating mode.
        :rtype: float | None
        """
        if self.thermal_demand is None:
            return None
        return self.thermal_demand if self.mode == ThermalMode.HEAT else 0.0

    @property
    def cooling_demand(self) -> float | None:
        """Return cooling demand magnitude (0.0 if heating or off).

        :returns: Demand magnitude for cooling mode.
        :rtype: float | None
        """
        if self.thermal_demand is None:
            return None
        return self.thermal_demand if self.mode == ThermalMode.COOL else 0.0

    @property
    def heat_demand(self) -> float | None:
        """Deprecated backward compatibility alias for heating_demand.

        :returns: Demand magnitude for heating mode.
        :rtype: float | None
        """
        return self.heating_demand


@dataclass(frozen=True, slots=True)
class UfhCircuitDTO:
    """CQRS DTO representing a complete UFH circuit snapshot.

    :param ufh_index: Two-character hex circuit identifier.
    :type ufh_index: str
    :param zone_index: Associated heating zone index, or None.
    :type zone_index: str | None
    :param heat_demand: Heating demand (0.0 to 1.0), or None.
    :type heat_demand: float | None
    :param cooling_demand: Cooling demand (0.0 to 1.0), or None.
    :type cooling_demand: float | None
    :param circuit_mode: Thermal operating mode or None.
    :type circuit_mode: ThermalMode | str | None
    :param setpoint: Target setpoint temperature or None.
    :type setpoint: float | None
    :param min_temp: Minimum allowable setpoint or None.
    :type min_temp: float | None
    :param max_temp: Maximum allowable setpoint or None.
    :type max_temp: float | None
    :param flags: Raw mode/config flags or None.
    :type flags: int | None
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

    @property
    def circuit_index(self) -> str:
        """Return the UFH circuit index string.

        :returns: The UFH circuit index.
        :rtype: str
        """
        return self.ufh_index


@dataclass(frozen=True, slots=True)
class ActuatorStateDTO:
    """DTO for heating relay actuator state (e.g. BDR91).

    :param modulation_level: Active modulation level percentage (0.0
        to 1.0).
    :type modulation_level: float | None
    :param actuator_enabled: True if actuator output is enabled.
    :type actuator_enabled: bool | None
    :param ch_active: True if central heating call is active.
    :type ch_active: bool | None
    :param dhw_active: True if domestic hot water call is active.
    :type dhw_active: bool | None
    :param flame_active: True if boiler flame is active.
    :type flame_active: bool | None
    :param last_updated: Timestamp of last state update.
    :type last_updated: dt | None
    """

    modulation_level: float | None = None
    actuator_enabled: bool | None = None
    ch_active: bool | None = None
    dhw_active: bool | None = None
    flame_active: bool | None = None
    last_updated: dt | None = None


@dataclass(frozen=True, slots=True)
class ActuatorCycleDTO:
    """DTO for heating actuator cycle parameters (command 3EF1).

    :param actuator_countdown: Remaining actuator run countdown.
    :type actuator_countdown: int | None
    :param cycle_countdown: Remaining cycle countdown.
    :type cycle_countdown: int | None
    :param actuator_enabled: True if actuator state output is enabled.
    :type actuator_enabled: bool | None
    :param modulation_level: Active modulation level (0.0 to 1.0).
    :type modulation_level: float | None
    """

    actuator_countdown: int | None = None
    cycle_countdown: int | None = None
    actuator_enabled: bool | None = None
    modulation_level: float | None = None


@dataclass(frozen=True, slots=True)
class ZoneScheduleDTO:
    """CQRS DTO wrapping zone or system weekly schedule payload.

    :param zone_index: Zone index string (e.g. '00', 'HW').
    :type zone_index: str
    :param schedule: Weekly schedule list of daily switchpoint dicts.
    :type schedule: list[dict[str, Any]]
    """

    zone_index: str
    schedule: list[dict[str, Any]]
