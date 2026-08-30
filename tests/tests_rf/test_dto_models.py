"""Unit tests for RAMSES RF CQRS Data Transfer Objects (DTOs)."""

from datetime import UTC, datetime as dt

from ramses_rf.enums import ThermalMode
from ramses_rf.models import (
    ActuatorCycleDTO,
    BdrStateDTO,
    JimStateDTO,
    OpenThermStateDTO,
    ThermalDemandDTO,
    UfhCircuitDemandDTO,
    ZoneScheduleDTO,
)
from ramses_rf.models.state_opentherm import (
    OpenThermCounters,
    OpenThermFlags,
    OpenThermTemperatures,
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


def test_bdr_state_dto() -> None:
    # Arrange
    now = dt.now(UTC)

    # Act
    dto = BdrStateDTO(
        modulation_level=0.45,
        actuator_enabled=True,
        last_updated=now,
    )

    # Assert
    assert dto.modulation_level == 0.45
    assert dto.actuator_enabled is True
    assert dto.last_updated == now


def test_bdr_state_dto_defaults() -> None:
    # Arrange & Act
    dto = BdrStateDTO()

    # Assert
    assert dto.modulation_level is None
    assert dto.actuator_enabled is None
    assert dto.last_updated is None


def test_jim_state_dto_inheritance_and_fields() -> None:
    # Arrange
    now = dt.now(UTC)

    # Act
    dto = JimStateDTO(
        modulation_level=0.75,
        actuator_enabled=True,
        ch_active=True,
        dhw_active=False,
        flame_active=True,
        cooling_active=False,
        last_updated=now,
    )

    # Assert
    assert isinstance(dto, BdrStateDTO)
    assert dto.modulation_level == 0.75
    assert dto.actuator_enabled is True
    assert dto.ch_active is True
    assert dto.dhw_active is False
    assert dto.flame_active is True
    assert dto.cooling_active is False
    assert dto.last_updated == now


def test_opentherm_state_dto() -> None:
    # Arrange
    now = dt.now(UTC)
    flags = OpenThermFlags(ch_enabled=True, flame_active=True)
    temps = OpenThermTemperatures(boiler_output=62.5, dhw=48.0)
    counters = OpenThermCounters(burner_starts=150, burner_hours=320)

    # Act
    dto = OpenThermStateDTO(
        flags=flags,
        temperatures=temps,
        counters=counters,
        ch_water_pressure=1.8,
        dhw_flow_rate=11.2,
        max_rel_modulation=1.0,
        rel_modulation_level=0.65,
        oem_code=0,
        last_updated=now,
    )

    # Assert
    assert dto.flags.ch_enabled is True
    assert dto.flags.flame_active is True
    assert dto.temperatures.boiler_output == 62.5
    assert dto.temperatures.dhw == 48.0
    assert dto.counters.burner_starts == 150
    assert dto.counters.burner_hours == 320
    assert dto.ch_water_pressure == 1.8
    assert dto.dhw_flow_rate == 11.2
    assert dto.max_rel_modulation == 1.0
    assert dto.rel_modulation_level == 0.65
    assert dto.oem_code == 0
    assert dto.last_updated == now


def test_opentherm_state_dto_defaults() -> None:
    # Arrange & Act
    dto = OpenThermStateDTO()

    # Assert
    assert isinstance(dto.flags, OpenThermFlags)
    assert isinstance(dto.temperatures, OpenThermTemperatures)
    assert isinstance(dto.counters, OpenThermCounters)
    assert dto.ch_water_pressure is None
    assert dto.dhw_flow_rate is None
    assert dto.max_rel_modulation is None
    assert dto.rel_modulation_level is None
    assert dto.oem_code is None
    assert dto.last_updated is None


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
