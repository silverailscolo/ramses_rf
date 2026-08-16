"""Focused HCC100 cooling packet and UFC relay tests."""

from datetime import datetime as dt
from typing import Any
from unittest.mock import MagicMock

import pytest

from ramses_rf.const import (
    SZ_COOLING_DEMAND,
    SZ_PUMP_RELAY_STATE,
    SZ_ZONE_INDEX,
)
from ramses_rf.devices.heat_controllers import Controller, UfhController
from ramses_rf.enums import PumpRelayState, ThermalMode
from ramses_rf.models.state_climate import ActuatorState, SystemState
from ramses_rf.parsers.decoder import decode_packet
from ramses_rf.payloads.heating import (
    ActuatorStatePayload,
    HeatDemandPayload,
    TemperaturePayload,
)
from ramses_rf.payloads.hvac import (
    CoolingState2BPayload,
    CoolingState3BPayload,
    CoolingStatePayload,
)
from ramses_rf.protocol.ramses import CODES_WITH_ARRAYS
from ramses_rf.systems.tcs import System
from ramses_tx.address import Address
from ramses_tx.const import Code, Verb
from ramses_tx.dtos import PacketDTO


def _decode(
    code: Code | str, payload: str, source_type: str = "02"
) -> dict[str, Any]:
    """Helper to construct a PacketDTO and run decode_packet."""
    # Arrange
    dto = PacketDTO(
        timestamp=dt.now(),
        rssi="-64",
        verb=str(Verb.I_),
        seq="---",
        addr1=f"{source_type}:000001",
        addr2="--:------",
        addr3=f"{source_type}:000001",
        code=code if isinstance(code, str) else code.value,
        length=f"{len(payload) // 2:03d}",
        payload=payload,
    )

    # Act
    result = decode_packet(dto)

    # Assert
    assert isinstance(result, dict)
    return result


@pytest.mark.parametrize(
    ("payload", "expected"),
    (
        ("1EC800", True),
        ("200000", False),
        ("23C800", True),
        ("880000", False),
        ("FDC800", True),
        ("00C800", True),
        ("010000", False),
        ("01C800", True),
    ),
)
def test_2d49_hcc100_cooling_demand_decoding(
    payload: str, expected: bool
) -> None:
    # Arrange
    code = Code._2D49

    # Act
    result = _decode(code, payload, "01")

    # Assert
    assert result[SZ_ZONE_INDEX] == payload[:2]
    assert result[SZ_COOLING_DEMAND] is expected


def test_2d49_unknown_demand_byte_handling() -> None:
    # Arrange
    code = Code._2D49
    payload = "1E6400"

    # Act
    result = _decode(code, payload, "01")

    # Assert
    assert result[SZ_ZONE_INDEX] == "1E"
    assert result[SZ_COOLING_DEMAND] is False


@pytest.mark.parametrize(
    ("raw_bytes", "expected_zone", "expected_state", "expected_reserved"),
    (
        (b"\x1e\xc8\x00", 0x1E, True, 0x00),
        (b"\x20\x00\x00", 0x20, False, 0x00),
        (b"\x23\xc8\x00", 0x23, True, 0x00),
        (b"\x88\x00\x00", 0x88, False, 0x00),
        (b"\xfd\xc8\x00", 0xFD, True, 0x00),
        (b"\x00\xc8\x00", 0x00, True, 0x00),
        (b"\x01\x00\x00", 0x01, False, 0x00),
    ),
)
def test_2d49_3b_payload_dataclass_from_bytes_and_roundtrip(
    raw_bytes: bytes,
    expected_zone: int,
    expected_state: bool,
    expected_reserved: int,
) -> None:
    # Arrange & Act
    payload = CoolingStatePayload.from_bytes(raw_bytes)

    # Assert
    assert isinstance(payload, CoolingState3BPayload)
    assert payload.domain_or_zone_index == expected_zone
    assert payload.state is expected_state
    assert payload.reserved == expected_reserved
    assert payload.to_bytes() == raw_bytes
    assert payload.to_dict() == {
        SZ_ZONE_INDEX: f"{expected_zone:02X}",
        SZ_COOLING_DEMAND: expected_state,
    }


@pytest.mark.parametrize(
    ("raw_bytes", "expected_zone", "expected_state"),
    (
        (b"\x00\xc8", 0x00, True),
        (b"\x01\x00", 0x01, False),
        (b"\x1e\xc8", 0x1E, True),
    ),
)
def test_2d49_2b_payload_dataclass_from_bytes_and_roundtrip(
    raw_bytes: bytes,
    expected_zone: int,
    expected_state: bool,
) -> None:
    # Arrange & Act
    payload = CoolingStatePayload.from_bytes(raw_bytes)

    # Assert
    assert isinstance(payload, CoolingState2BPayload)
    assert payload.domain_or_zone_index == expected_zone
    assert payload.state is expected_state
    assert payload.to_bytes() == raw_bytes
    assert payload.to_dict() == {
        SZ_ZONE_INDEX: f"{expected_zone:02X}",
        SZ_COOLING_DEMAND: expected_state,
    }


@pytest.mark.parametrize(
    "invalid_length_bytes",
    (
        b"",
        b"\x1e",
        b"\x1e\xc8\x00\x00",
        b"\x1e\xc8\x00\x00\x00",
    ),
)
def test_2d49_invalid_length_rejection(invalid_length_bytes: bytes) -> None:
    # Arrange & Act & Assert
    with pytest.raises(ValueError, match="Invalid payload length for 2D49"):
        CoolingStatePayload.from_bytes(invalid_length_bytes)


def test_30c9_ufc_array_metadata_registration() -> None:
    # Arrange & Act
    ufc_types = CODES_WITH_ARRAYS[Code._30C9][1]

    # Assert
    assert isinstance(ufc_types, tuple)
    assert "02" in ufc_types
    assert "01" in ufc_types
    assert "12" in ufc_types
    assert "22" in ufc_types


@pytest.mark.parametrize(
    "index",
    (0, 1, 15, 16, 0x1E, 0x20, 0x23, 0x88, 0xFC, 0xFD, 255),
)
def test_full_byte_zone_indexes_temperature_and_demand(index: int) -> None:
    # Arrange
    temp_bytes = bytes((index, 0x08, 0x34))
    demand_bytes = bytes((index, 0xC8))

    # Act
    temperature = TemperaturePayload.from_bytes(temp_bytes)
    demand = HeatDemandPayload.from_bytes(demand_bytes)

    # Assert
    assert isinstance(temperature, TemperaturePayload)
    assert isinstance(demand, HeatDemandPayload)
    assert temperature.to_dict()[SZ_ZONE_INDEX] == f"{index:02X}"
    assert demand.domain_or_zone_index == index


@pytest.mark.parametrize(
    ("relay_byte", "expected_state"),
    (
        (0x10, "cooling"),
        (0x02, "heating"),
        (0x00, "off"),
        (0x12, "cooling"),
        (0x15, "cooling"),
    ),
)
def test_3ef0_ufc_pump_relay_examples(
    relay_byte: int, expected_state: str
) -> None:
    # Arrange
    code = Code._3EF0
    payload = f"000000{relay_byte:02X}0000000000"

    # Act
    result = _decode(code, payload, source_type="02")

    # Assert
    assert result[SZ_PUMP_RELAY_STATE] == expected_state


def test_3ef0_ufc_pump_relay_anomalous_flag_priority() -> None:
    # Arrange
    code = Code._3EF0
    payload = "000000120000000000"

    # Act
    result = _decode(code, payload, source_type="02")

    # Assert
    assert result[SZ_PUMP_RELAY_STATE] == "cooling"


@pytest.mark.parametrize(
    ("payload_length", "source_type"),
    (
        (3, "01"),
        (3, "02"),
        (3, "13"),
        (6, "01"),
        (6, "02"),
        (6, "13"),
        (9, "01"),
        (9, "10"),
        (9, "13"),
    ),
)
def test_3ef0_non_ufc_routing_guard(
    payload_length: int, source_type: str
) -> None:
    # Arrange
    code = Code._3EF0
    if payload_length == 9:
        raw_bytes = bytes((0, 100, 0, 0, 0, 0, 0, 20, 200))
    elif payload_length == 6:
        raw_bytes = bytes((0, 100, 0, 0, 0, 0))
    else:
        raw_bytes = bytes((0, 100, 0))
    payload = raw_bytes.hex().upper()

    # Act
    result = _decode(code, payload, source_type=source_type)

    # Assert
    assert SZ_PUMP_RELAY_STATE not in result


def test_3ef0_standard_opentherm_payload_is_preserved() -> None:
    # Arrange
    raw_payload = bytes.fromhex("0064FF1000FF0114C8")

    # Act
    payload = ActuatorStatePayload.from_bytes(raw_payload)
    result = payload.to_dict()

    # Assert
    assert result == {
        "modulation_level": 0.5,
        "ch_active": False,
        "dhw_active": False,
        "flame_on": False,
        "cool_active": True,
        "ch_enabled": True,
        "ch_setpoint": 20,
        "max_rel_modulation": 1.0,
    }


def test_30c9_ufc_multi_zone_array_decoding() -> None:
    # Arrange
    indexes = [0x01, 0x02, 0x1E, 0x20, 0x23]
    raw_bytes = b"".join(bytes((index, 0x08, 0x34)) for index in indexes)

    # Act
    temperatures = TemperaturePayload.from_bytes(raw_bytes)

    # Assert
    assert isinstance(temperatures, list)
    assert [item.to_dict()[SZ_ZONE_INDEX] for item in temperatures] == [
        f"{index:02X}" for index in indexes
    ]


@pytest.mark.asyncio
async def test_ufh_controller_pump_relay_state_read_model() -> None:
    # Arrange
    gateway = MagicMock()
    address = MagicMock()
    ufc = UfhController(gateway, address)
    ufc.act_state = ActuatorState(pump_relay_state=PumpRelayState.COOLING)

    # Act
    state = await ufc.pump_relay_state()

    # Assert
    assert state == PumpRelayState.COOLING
    assert str(state) == "cooling"
    assert isinstance(state, PumpRelayState)


@pytest.mark.asyncio
async def test_system_cooling_mode_and_thermal_mode_read_model() -> None:
    # Arrange
    gateway = MagicMock()
    gateway.device_registry.system_by_id = {}
    controller = Controller(gateway, Address("01:123456"))
    system = System(controller)
    system.system_state = SystemState(cooling_mode=True)

    # Act
    cooling_mode = await system.cooling_mode()
    thermal_mode = await system.thermal_mode()

    # Assert
    assert cooling_mode is True
    assert thermal_mode == ThermalMode.COOL


@pytest.mark.asyncio
async def test_system_thermal_mode_heating_fallback() -> None:
    # Arrange
    gateway = MagicMock()
    gateway.device_registry.system_by_id = {}
    controller = Controller(gateway, Address("01:123456"))
    system = System(controller)
    system.system_state = SystemState(cooling_mode=False)

    # Act
    cooling_mode = await system.cooling_mode()
    thermal_mode = await system.thermal_mode()

    # Assert
    assert cooling_mode is False
    assert thermal_mode == ThermalMode.HEAT
