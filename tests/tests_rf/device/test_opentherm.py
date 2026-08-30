from datetime import UTC, datetime as dt, timedelta as td
from unittest.mock import MagicMock

import pytest

from ramses_rf.const import (
    HEARTBEAT_TIMEOUT_OTB,
    SZ_BOILER_OUTPUT_TEMP,
    SZ_CH_ACTIVE,
    SZ_CH_WATER_PRESSURE,
    SZ_FLAME_ACTIVE,
    SZ_HEAT_DEMAND,
    SZ_MAX_REL_MODULATION,
    SZ_OPENTHERM_PARAMS,
    SZ_OPENTHERM_SCHEMA,
    SZ_RAMSES_II_PARAMS,
    SZ_RAMSES_II_SCHEMA,
    SZ_REL_MODULATION_LEVEL,
)
from ramses_rf.devices import BdrSwitch, JimDevice, OtbGateway
from ramses_rf.models import (
    ActuatorState,
    BdrStateDTO,
    DemandState,
    JimStateDTO,
    OpenThermCounters,
    OpenThermFlags,
    OpenThermState,
    OpenThermStateDTO,
    OpenThermTemperatures,
)
from ramses_tx.address import Address


@pytest.fixture
def mock_gwy() -> MagicMock:
    """Return a mock Gateway for OTB device testing."""
    gwy = MagicMock()
    gwy.config = MagicMock()
    gwy.config.known_list = {}
    gwy.config.disable_discovery = True
    gwy.config.use_native_ot = "prefer"
    return gwy


@pytest.mark.asyncio
async def test_otb_gateway_grouped_properties(mock_gwy: MagicMock) -> None:
    """Verify OtbGateway exposes typed immutable grouped properties."""
    # Arrange
    addr = Address("10:048122")
    otb = OtbGateway(mock_gwy, addr)
    expected_flags = OpenThermFlags(
        ch_active=True, dhw_active=False, flame_active=True
    )
    expected_temps = OpenThermTemperatures(
        boiler_output=55.5, boiler_return=42.0
    )
    expected_counters = OpenThermCounters(burner_hours=120, burner_starts=450)

    # Act
    otb.opentherm_state = OpenThermState(
        flags=expected_flags,
        temperatures=expected_temps,
        counters=expected_counters,
    )

    # Assert
    assert otb.flags == expected_flags
    assert otb.temperatures == expected_temps
    assert otb.counters == expected_counters
    assert otb.flags.ch_active is True
    assert otb.temperatures.boiler_output == 55.5
    assert otb.counters.burner_hours == 120


@pytest.mark.asyncio
async def test_otb_gateway_individual_async_getters(
    mock_gwy: MagicMock,
) -> None:
    """Verify all individual async getters return correct values from OpenThermState."""
    # Arrange
    addr = Address("10:048122")
    otb = OtbGateway(mock_gwy, addr)
    otb.opentherm_state = OpenThermState(
        flags=OpenThermFlags(
            ch_active=True,
            ch_enabled=True,
            cooling_active=False,
            cooling_enabled=False,
            dhw_active=True,
            dhw_blocking=False,
            dhw_enabled=True,
            fault_present=False,
            flame_active=True,
            otc_active=True,
            summer_mode=False,
        ),
        temperatures=OpenThermTemperatures(
            boiler_output=62.5,
            boiler_return=48.0,
            boiler_setpoint=65.0,
            ch_max_setpoint=80.0,
            ch_setpoint=60.0,
            dhw=52.0,
            dhw_setpoint=55.0,
            outside=12.5,
        ),
        counters=OpenThermCounters(
            burner_failed_starts=2,
            burner_hours=320,
            burner_starts=1150,
            ch_pump_hours=400,
            ch_pump_starts=800,
            dhw_burner_hours=150,
            dhw_burner_starts=600,
            dhw_pump_hours=180,
            dhw_pump_starts=700,
            flame_signal_low=5,
        ),
        ch_water_pressure=1.8,
        dhw_flow_rate=9.5,
        max_rel_modulation=1.0,
        rel_modulation_level=0.45,
        oem_code=12,
    )

    # Act & Assert
    assert await otb.boiler_output_temp() == 62.5
    assert await otb.boiler_return_temp() == 48.0
    assert await otb.boiler_setpoint() == 65.0
    assert await otb.ch_max_setpoint() == 80.0
    assert await otb.ch_setpoint() == 60.0
    assert await otb.ch_water_pressure() == 1.8
    assert await otb.dhw_flow_rate() == 9.5
    assert await otb.dhw_setpoint() == 55.0
    assert await otb.dhw_temp() == 52.0
    assert await otb.max_rel_modulation() == 1.0
    assert await otb.oem_code() == 12.0
    assert await otb.outside_temp() == 12.5
    assert await otb.rel_modulation_level() == 0.45

    assert await otb.ch_active() is True
    assert await otb.ch_enabled() is True
    assert await otb.cooling_active() is False
    assert await otb.cooling_enabled() is False
    assert await otb.dhw_active() is True
    assert await otb.dhw_blocking() is False
    assert await otb.dhw_enabled() is True
    assert await otb.fault_present() is False
    assert await otb.flame_active() is True
    assert await otb.otc_active() is True
    assert await otb.summer_mode() is False


@pytest.mark.asyncio
async def test_otb_gateway_status_parity_and_absence_of_actuator_fields(
    mock_gwy: MagicMock,
) -> None:
    """Verify status dictionary schema and absence of legacy Actuator relay fields."""
    # Arrange
    addr = Address("10:048122")
    otb = OtbGateway(mock_gwy, addr)
    otb.demand_state = DemandState(heat_demand=0.65)
    otb.opentherm_state = OpenThermState(
        flags=OpenThermFlags(ch_active=True, flame_active=True),
        temperatures=OpenThermTemperatures(boiler_output=55.0),
        ch_water_pressure=1.5,
        rel_modulation_level=0.5,
    )

    # Act
    status = await otb.status()

    # Assert
    # Digital OpenTherm telemetry is populated
    assert status[SZ_HEAT_DEMAND] == 0.65
    assert status[SZ_BOILER_OUTPUT_TEMP] == 55.0
    assert status[SZ_CH_WATER_PRESSURE] == 1.5
    assert status[SZ_REL_MODULATION_LEVEL] == 0.5
    assert status[SZ_CH_ACTIVE] is True
    assert status[SZ_FLAME_ACTIVE] is True

    # Relay contact actuator fields must NOT be present
    assert "actuator_cycle" not in status
    assert "actuator_state" not in status
    assert "actuator_enabled" not in status
    assert "modulation_level" not in status


@pytest.mark.asyncio
async def test_otb_gateway_schema_and_params_constants(
    mock_gwy: MagicMock,
) -> None:
    """Verify schema and params use canonical non-truncated schema constants."""
    # Arrange
    addr = Address("10:048122")
    otb = OtbGateway(mock_gwy, addr)
    otb.opentherm_state = OpenThermState(max_rel_modulation=0.9)

    # Act
    schema = await otb.schema()
    params = await otb.params()

    # Assert
    assert SZ_OPENTHERM_SCHEMA in schema
    assert SZ_RAMSES_II_SCHEMA in schema
    assert schema[SZ_OPENTHERM_SCHEMA] == {}
    assert schema[SZ_RAMSES_II_SCHEMA] == {}

    assert SZ_OPENTHERM_PARAMS in params
    assert SZ_RAMSES_II_PARAMS in params
    assert params[SZ_RAMSES_II_PARAMS][SZ_MAX_REL_MODULATION] == 0.9


@pytest.mark.asyncio
async def test_otb_gateway_opentherm_state_dto(mock_gwy: MagicMock) -> None:
    """Verify opentherm_state_dto returns accurate hardware-pure OpenThermStateDTO."""
    # Arrange
    addr = Address("10:048122")
    otb = OtbGateway(mock_gwy, addr)
    timestamp = dt(2026, 8, 30, 12, 0, 0, tzinfo=UTC)
    otb.opentherm_state = OpenThermState(
        flags=OpenThermFlags(ch_active=True, flame_active=True),
        temperatures=OpenThermTemperatures(boiler_output=58.0),
        counters=OpenThermCounters(burner_hours=200),
        ch_water_pressure=1.6,
        dhw_flow_rate=0.0,
        max_rel_modulation=1.0,
        rel_modulation_level=0.35,
        oem_code=4,
        last_updated=timestamp,
    )

    # Act
    dto = await otb.opentherm_state_dto()

    # Assert
    assert isinstance(dto, OpenThermStateDTO)
    assert dto.flags.ch_active is True
    assert dto.temperatures.boiler_output == 58.0
    assert dto.counters.burner_hours == 200
    assert dto.ch_water_pressure == 1.6
    assert dto.dhw_flow_rate == 0.0
    assert dto.max_rel_modulation == 1.0
    assert dto.rel_modulation_level == 0.35
    assert dto.oem_code == 4
    assert dto.last_updated == timestamp


@pytest.mark.asyncio
async def test_otb_gateway_domain_and_hardware_isolation(
    mock_gwy: MagicMock,
) -> None:
    """Verify BDR91, JIM, and OTB hardware models remain strictly isolated."""
    # Arrange
    bdr_addr = Address("13:000001")
    jim_addr = Address("08:000001")
    otb_addr = Address("10:000001")

    bdr = BdrSwitch(mock_gwy, bdr_addr)
    jim = JimDevice(mock_gwy, jim_addr)
    otb = OtbGateway(mock_gwy, otb_addr)

    bdr.act_state = ActuatorState(modulation_level=0.8, actuator_enabled=True)
    jim.act_state = ActuatorState(
        modulation_level=0.5, actuator_enabled=True, flame_active=True
    )
    otb.opentherm_state = OpenThermState(
        flags=OpenThermFlags(flame_active=True), rel_modulation_level=0.3
    )

    # Act
    bdr_dto = await bdr.bdr_state()
    jim_dto = await jim.jim_state()
    otb_dto = await otb.opentherm_state_dto()

    # Assert
    assert isinstance(bdr_dto, BdrStateDTO)
    assert isinstance(jim_dto, JimStateDTO)
    assert isinstance(otb_dto, OpenThermStateDTO)

    # BDR91 has no OpenTherm state or JIM state
    assert not hasattr(bdr, "opentherm_state_dto")
    assert not hasattr(bdr, "jim_state")

    # JIM has no OpenTherm state
    assert not hasattr(jim, "opentherm_state_dto")

    # OTB has no BDR or JIM relay state
    assert not hasattr(otb, "bdr_state")
    assert not hasattr(otb, "jim_state")
    assert not hasattr(otb, "actuator_state")
    assert not hasattr(otb, "actuator_cycle")


def test_otb_gateway_heartbeat_timeout(mock_gwy: MagicMock) -> None:
    """Verify heartbeat_timeout property returns HEARTBEAT_TIMEOUT_OTB."""
    # Arrange
    addr = Address("10:048122")
    otb = OtbGateway(mock_gwy, addr)

    # Act
    timeout = otb.heartbeat_timeout

    # Assert
    assert timeout == HEARTBEAT_TIMEOUT_OTB
    assert timeout == td(hours=24)
