"""RAMSES RF - CQRS Data Transfer Objects (DTOs)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime as dt

from ramses_rf.enums import ThermalMode


@dataclass(frozen=True, slots=True)
class ThermalDemandDTO:
    """CQRS Read-Model representation of zone or system thermal demand.

    :param thermal_demand: Active demand magnitude (0.0 to 1.0) or None.
    :type thermal_demand: float | None
    :param mode: Active thermal mode (HEAT, COOL, OFF).
    :type mode: ThermalMode
    :param ufx_idx: Circuit or zone index string if applicable.
    :type ufx_idx: str | None
    :param domain_id: System domain identifier if applicable.
    :type domain_id: str | None
    """

    thermal_demand: float | None = None
    mode: ThermalMode = ThermalMode.HEAT
    ufx_idx: str | None = None
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

    :param ufx_idx: Circuit index identifier.
    :type ufx_idx: str
    :param thermal_demand: Active demand magnitude (0.0 to 1.0) or None.
    :type thermal_demand: float | None
    :param mode: Active thermal mode (HEAT, COOL, OFF).
    :type mode: ThermalMode
    """

    ufx_idx: str
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
class ActuatorStateDTO:
    """DTO for heating/boiler actuator state (BDR91/OTB).

    :param modulation_level: Active modulation level percentage (0.0 to 1.0).
    :type modulation_level: float | None
    :param actuator_enabled: True if actuator output is enabled.
    :type actuator_enabled: bool | None
    :param ch_active: True if central heating call is active.
    :type ch_active: bool | None
    :param ch_enabled: True if central heating mode is enabled.
    :type ch_enabled: bool | None
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
    ch_enabled: bool | None = None
    dhw_active: bool | None = None
    flame_active: bool | None = None
    last_updated: dt | None = None
