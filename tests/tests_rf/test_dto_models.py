"""Unit tests for RAMSES RF CQRS Data Transfer Objects (DTOs)."""

from datetime import UTC, datetime as dt

from ramses_rf.enums import ThermalMode
from ramses_rf.models import (
    ActuatorCycleDTO,
    ActuatorStateDTO,
    ThermalDemandDTO,
    UfhCircuitDemandDTO,
    ZoneScheduleDTO,
)


def test_thermal_demand_dto_heat_mode() -> None:
    # Arrange
    mode = ThermalMode.HEAT
    magnitude = 0.75

    # Act
    dto = ThermalDemandDTO(thermal_demand=magnitude, mode=mode, ufh_index="01")

    # Assert
    assert dto.thermal_demand == 0.75
    assert dto.mode == ThermalMode.HEAT
    assert dto.heating_demand == 0.75
    assert dto.cooling_demand == 0.0
    assert dto.heat_demand == 0.75
    assert dto.ufh_index == "01"


def test_thermal_demand_dto_cool_mode() -> None:
    # Arrange
    mode = ThermalMode.COOL
    magnitude = 0.50

    # Act
    dto = ThermalDemandDTO(thermal_demand=magnitude, mode=mode, ufh_index="02")

    # Assert
    assert dto.thermal_demand == 0.50
    assert dto.mode == ThermalMode.COOL
    assert dto.heating_demand == 0.0
    assert dto.cooling_demand == 0.50
    assert dto.heat_demand == 0.0


def test_thermal_demand_dto_none_magnitude() -> None:
    # Arrange
    magnitude = None

    # Act
    dto = ThermalDemandDTO(thermal_demand=magnitude, mode=ThermalMode.HEAT)

    # Assert
    assert dto.thermal_demand is None
    assert dto.heating_demand is None
    assert dto.cooling_demand is None


def test_ufh_circuit_demand_dto() -> None:
    # Arrange
    index = "00"
    demand = 0.85

    # Act
    dto = UfhCircuitDemandDTO(ufh_index=index, thermal_demand=demand)

    # Assert
    assert dto.ufh_index == "00"
    assert dto.thermal_demand == 0.85
    assert dto.heating_demand == 0.85
    assert dto.cooling_demand == 0.0


def test_actuator_state_dto() -> None:
    # Arrange
    now = dt.now(UTC)

    # Act
    dto = ActuatorStateDTO(
        modulation_level=0.45,
        actuator_enabled=True,
        ch_active=True,
        flame_active=True,
        last_updated=now,
    )

    # Assert
    assert dto.modulation_level == 0.45
    assert dto.actuator_enabled is True
    assert dto.ch_active is True
    assert dto.flame_active is True
    assert dto.last_updated == now


def test_actuator_cycle_dto() -> None:
    # Arrange
    actuator_cd = 120
    cycle_cd = 300

    # Act
    dto = ActuatorCycleDTO(
        actuator_countdown=actuator_cd,
        cycle_countdown=cycle_cd,
        actuator_enabled=True,
        modulation_level=0.30,
    )

    # Assert
    assert dto.actuator_countdown == 120
    assert dto.cycle_countdown == 300
    assert dto.actuator_enabled is True
    assert dto.modulation_level == 0.30


def test_zone_schedule_dto() -> None:
    # Arrange
    zone_index = "01"
    raw_schedule = [{"day_of_week": 0, "switchpoints": []}]

    # Act
    dto = ZoneScheduleDTO(zone_index=zone_index, schedule=raw_schedule)

    # Assert
    assert dto.zone_index == "01"
    assert dto.schedule == raw_schedule
