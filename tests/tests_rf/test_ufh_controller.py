from unittest.mock import MagicMock

import pytest

from ramses_rf.const import SZ_CIRCUITS, SZ_HEAT_DEMAND, SZ_RELAY_DEMAND
from ramses_rf.devices.heat_controllers import UfhCircuit, UfhController
from ramses_rf.enums import PumpRelayState, ThermalMode
from ramses_rf.models import (
    UfhCircuitDemandDTO,
    UfhCircuitDTO,
    UfhCircuitState,
    UfhState,
)
from ramses_tx.address import Address


def _make_mock_ufc(device_id: str = "02:000921") -> UfhController:
    """Create a mock UfhController instance with mock gateway and message store."""
    gwy = MagicMock()
    msg_store = MagicMock()
    gwy.msg_transport = None
    gwy._msg_db = None
    gwy._transport = None
    gwy.message_store = msg_store

    ufc = UfhController(gwy, Address(device_id))
    return ufc


@pytest.mark.asyncio
async def test_ufh_controller_initialization_and_circuits_property() -> None:
    # Arrange
    ufc = _make_mock_ufc("02:000921")

    # Act
    circuits = ufc.circuits

    # Assert
    assert isinstance(circuits, list)
    assert len(circuits) == 0
    assert ufc.childs == circuits


@pytest.mark.asyncio
async def test_ufh_controller_get_circuit_creates_and_caches() -> None:
    # Arrange
    ufc = _make_mock_ufc("02:000921")

    # Act - Create circuit 00
    circuit_00 = ufc.get_circuit("00")

    # Assert
    assert isinstance(circuit_00, UfhCircuit)
    assert circuit_00.ufh_index == "00"
    assert circuit_00.circuit_index == "00"
    assert circuit_00.ufc is ufc
    assert ufc.child_by_id["00"] is circuit_00
    assert circuit_00 in ufc.circuits

    # Act - Retrieve existing circuit 00 (idempotent)
    cached_circuit = ufc.get_circuit("00")

    # Assert
    assert cached_circuit is circuit_00
    assert len(ufc.circuits) == 1


@pytest.mark.asyncio
async def test_ufh_controller_thermal_demands_and_cooling_demands() -> None:
    # Arrange
    ufc = _make_mock_ufc("02:000921")
    ufc.ufh_state = UfhState(
        heat_demands={"00": 0.85, "01": 0.50},
        cooling_demands={"00": 0.0, "01": 0.70},
        circuit_modes={"00": ThermalMode.HEAT, "01": ThermalMode.COOL},
    )

    # Act
    heat_demands = await ufc.thermal_demands()
    cool_demands = await ufc.cooling_demands()
    modes = await ufc.circuit_modes()

    # Assert
    assert heat_demands is not None
    assert len(heat_demands) == 2
    assert heat_demands[0] == UfhCircuitDemandDTO(
        ufh_index="00",
        thermal_demand=0.85,
        mode=ThermalMode.HEAT,
    )
    assert heat_demands[1] == UfhCircuitDemandDTO(
        ufh_index="01",
        thermal_demand=0.50,
        mode=ThermalMode.HEAT,
    )

    assert cool_demands is not None
    assert len(cool_demands) == 2
    assert cool_demands[0] == UfhCircuitDemandDTO(
        ufh_index="00",
        thermal_demand=0.0,
        mode=ThermalMode.COOL,
    )
    assert cool_demands[1] == UfhCircuitDemandDTO(
        ufh_index="01",
        thermal_demand=0.70,
        mode=ThermalMode.COOL,
    )

    assert modes is not None
    assert modes["00"] == ThermalMode.HEAT
    assert modes["01"] == ThermalMode.COOL


@pytest.mark.asyncio
async def test_ufh_controller_pump_relay_state_prioritizes_ufh_state() -> None:
    # Arrange
    ufc = _make_mock_ufc("02:000921")
    ufc.ufh_state = UfhState(
        pump_relay_state=PumpRelayState.HEATING,
    )

    # Act
    pump_state = await ufc.pump_relay_state()

    # Assert
    assert pump_state == PumpRelayState.HEATING


@pytest.mark.asyncio
async def test_ufh_controller_schema_params_and_status() -> None:
    # Arrange
    ufc = _make_mock_ufc("02:000921")
    ufc.ufh_state = UfhState(
        relay_demand_fa=0.60,
        setpoints={"00": {"setpoint": 21.0}},
    )

    # Act
    schema = await ufc.schema()
    params = await ufc.params()
    status = await ufc.status()

    # Assert
    assert isinstance(schema, dict)
    assert SZ_CIRCUITS in schema

    assert isinstance(params, dict)
    assert SZ_CIRCUITS in params
    assert params[SZ_CIRCUITS] == {"00": {"setpoint": 21.0}}

    assert await ufc.heat_demand_fa() == 0.60
    assert await ufc.relay_demand_fa() == 0.60
    assert await ufc.heat_demand_fc() == await ufc.heat_demand()

    assert isinstance(status, dict)
    assert SZ_HEAT_DEMAND in status
    assert SZ_RELAY_DEMAND in status
    assert f"{SZ_RELAY_DEMAND}_fa" in status
    assert status[f"{SZ_RELAY_DEMAND}_fa"] == 0.60


@pytest.mark.asyncio
async def test_ufh_circuit_properties_delegation_to_cqrs_state() -> None:
    # Arrange
    ufc = _make_mock_ufc("02:000921")
    circuit = ufc.get_circuit("02")
    ufc.ufh_state = UfhState(
        circuits={
            "02": UfhCircuitState(
                ufh_index="02",
                zone_index="03",
                heat_demand=0.65,
                cooling_demand=0.15,
                circuit_mode=ThermalMode.HEAT,
                setpoint=22.5,
                min_temp=12.0,
                max_temp=26.0,
                flags=3,
            )
        }
    )

    # Act & Assert
    assert circuit.ufh_index == "02"
    assert circuit.circuit_index == "02"
    assert circuit.zone_index == "03"
    assert circuit.heat_demand == 0.65
    assert circuit.cooling_demand == 0.15
    assert circuit.circuit_mode == ThermalMode.HEAT
    assert circuit.setpoint == 22.5
    assert circuit.min_temp == 12.0
    assert circuit.max_temp == 26.0
    assert circuit.flags == 3


@pytest.mark.asyncio
async def test_ufh_circuit_set_zone_and_update_schema() -> None:
    # Arrange
    ufc = _make_mock_ufc("02:000921")
    circuit = ufc.get_circuit("00")
    mock_zone = MagicMock()
    mock_zone._child_id = "05"

    # Act - Explicit domain method
    circuit.set_zone(mock_zone)

    # Assert
    assert circuit.zone_index == "05"

    # Act - _update_schema compatibility hook
    mock_zone_2 = MagicMock()
    mock_zone_2._child_id = "07"
    circuit._update_schema(zone=mock_zone_2, unhandled_prop="ignored")

    # Assert
    assert circuit.zone_index == "07"


@pytest.mark.asyncio
async def test_ufh_circuit_to_dto() -> None:
    # Arrange
    ufc = _make_mock_ufc("02:000921")
    circuit = ufc.get_circuit("01")
    ufc.ufh_state = UfhState(
        circuits={
            "01": UfhCircuitState(
                ufh_index="01",
                zone_index="02",
                heat_demand=0.90,
                cooling_demand=0.0,
                circuit_mode=ThermalMode.HEAT,
                setpoint=20.0,
                min_temp=10.0,
                max_temp=25.0,
                flags=1,
            )
        }
    )

    # Act
    dto = circuit.to_dto()

    # Assert
    assert isinstance(dto, UfhCircuitDTO)
    assert dto.ufh_index == "01"
    assert dto.circuit_index == "01"
    assert dto.zone_index == "02"
    assert dto.heat_demand == 0.90
    assert dto.cooling_demand == 0.0
    assert dto.circuit_mode == ThermalMode.HEAT
    assert dto.setpoint == 20.0
    assert dto.min_temp == 10.0
    assert dto.max_temp == 25.0
    assert dto.flags == 1


def test_ufh_circuit_dto_immutability() -> None:
    # Arrange
    dto = UfhCircuitDTO(
        ufh_index="00",
        zone_index="01",
        heat_demand=0.5,
    )

    # Act & Assert
    assert dto.ufh_index == "00"
    assert dto.circuit_index == "00"
    assert dto.zone_index == "01"
    assert dto.heat_demand == 0.5

    with pytest.raises(AttributeError):
        # Mutating frozen dataclass raises AttributeError
        dto.heat_demand = 0.8  # type: ignore[misc]
