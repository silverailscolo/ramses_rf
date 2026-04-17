"""Test the ramses_rf.device.heat module."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from ramses_rf.const import SZ_PRESSURE
from ramses_rf.device.heat import (
    BdrSwitch,
    Controller,
    DhwSensor,
    OtbGateway,
    OutSensor,
    Thermostat,
    TrvActuator,
)
from ramses_rf.exceptions import DeviceNotFaked
from ramses_tx import Code, Message, Priority
from ramses_tx.address import Address
from ramses_tx.const import I_, RP, SZ_TEMPERATURE, MsgId
from ramses_tx.opentherm import SZ_MSG_ID, SZ_MSG_NAME, SZ_MSG_TYPE, SZ_VALUE, OtMsgType


@pytest.fixture
def mock_gwy() -> MagicMock:
    """Return a mock Gateway for device testing."""
    gwy = MagicMock()
    # Mock the persistent SQLite message database
    gwy.message_store = AsyncMock()
    gwy.async_send_cmd = AsyncMock()
    gwy.config = MagicMock()
    gwy.config.disable_discovery = True
    gwy.config.use_native_ot = "prefer"
    return gwy


@pytest.fixture
def mock_addr() -> MagicMock:
    """Return a mock Address for device instantiation."""
    addr = MagicMock(spec=Address)
    addr.id = "13:111111"
    addr.type = "13"
    return addr


def _create_ot_msg(
    msg_id: int,
    msg_type: OtMsgType,
    value: Any,
    name: str,
    verb: str = RP,
) -> MagicMock:
    """Helper to create a mocked 3220 OpenTherm Message."""
    msg = MagicMock(spec=Message)
    msg.verb = verb
    msg.code = Code._3220
    msg.payload = {
        SZ_MSG_ID: msg_id,
        SZ_MSG_TYPE: msg_type,
        SZ_VALUE: value,
        SZ_MSG_NAME: name,
    }
    msg._pkt = MagicMock()
    # Topology validation checks the source and destination
    msg.src = MagicMock()
    msg.dst = MagicMock()
    return msg


@pytest.mark.asyncio
async def test_bdr_switch_relay_demand_standard(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Test BdrSwitch resolves relay demand from standard 0008 packet."""
    device = BdrSwitch(mock_gwy, mock_addr)
    device.entity_state = MagicMock()

    # Simulate 0008 packet returning a valid demand
    async def mock_get_value(code: Code | tuple, key: str) -> float | None:
        if code == Code._0008 and key == "relay_demand":
            return 0.45
        return None

    device.entity_state.get_value = AsyncMock(side_effect=mock_get_value)

    demand = await device.relay_demand()
    assert demand == 0.45


@pytest.mark.asyncio
async def test_bdr_switch_relay_demand_fallback(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Test BdrSwitch falls back to 3EF0/3EF1 modulation for demand."""
    device = BdrSwitch(mock_gwy, mock_addr)
    device.entity_state = MagicMock()

    # Simulate 0008 missing, but 3EF0/3EF1 available
    async def mock_get_value(code: Code | tuple, key: str) -> float | None:
        if code == Code._0008:
            return None
        if code == (Code._3EF0, Code._3EF1) and key == "modulation_level":
            return 0.85
        return None

    device.entity_state.get_value = AsyncMock(side_effect=mock_get_value)

    demand = await device.relay_demand()
    assert demand == 0.85


@pytest.mark.asyncio
async def test_temperature_message_store_fallback(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Test Thermostat explicitly falls back to the message_store."""
    device = Thermostat(mock_gwy, mock_addr)
    device.entity_state = MagicMock()
    device.entity_state.get_value = AsyncMock(return_value=None)

    # Mock the database returning a cached 30C9 packet
    mock_msg = MagicMock()
    mock_msg.payload = {SZ_TEMPERATURE: 21.5}
    mock_gwy.message_store.get.return_value = [mock_msg]

    temp = await device.temperature()

    assert temp == 21.5
    mock_gwy.message_store.get.assert_called_once_with(code=Code._30C9, src=device.id)


@pytest.mark.asyncio
async def test_temperature_set_faked(mock_gwy: MagicMock, mock_addr: MagicMock) -> None:
    """Test Thermostat faking successfully delegates to Gateway."""
    device = Thermostat(mock_gwy, mock_addr)

    # 1. Test failure when not faked
    with (
        patch.object(
            Thermostat, "is_faked", new_callable=PropertyMock, return_value=False
        ),
        pytest.raises(DeviceNotFaked),
    ):
        await device.set_temperature(22.0)

    # 2. Test success when faked
    with (
        patch.object(
            Thermostat, "is_faked", new_callable=PropertyMock, return_value=True
        ),
        patch("ramses_rf.device.heat.Command.put_sensor_temp") as mock_cmd_gen,
    ):
        mock_cmd = MagicMock()
        mock_cmd_gen.return_value = mock_cmd

        await device.set_temperature(22.0)

        mock_cmd_gen.assert_called_once_with(device.id, 22.0)
        mock_gwy.async_send_cmd.assert_awaited_once_with(
            mock_cmd, num_repeats=2, priority=Priority.HIGH
        )


@pytest.mark.asyncio
async def test_dhw_temperature_message_store_fallback(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Test DhwSensor falls back to the persistent message_store."""
    device = DhwSensor(mock_gwy, mock_addr)
    device.entity_state = MagicMock()
    device.entity_state.get_value = AsyncMock(return_value=None)

    # Mock the database returning a cached 1260 packet
    mock_msg = MagicMock()
    mock_msg.payload = {SZ_TEMPERATURE: 55.0}
    mock_gwy.message_store.get.return_value = [mock_msg]

    temp = await device.temperature()

    assert temp == 55.0
    mock_gwy.message_store.get.assert_called_once_with(code=Code._1260, src=device.id)


@pytest.mark.asyncio
async def test_dhw_temperature_set_faked(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Test DhwSensor faking triggers put_dhw_temp."""
    device = DhwSensor(mock_gwy, mock_addr)

    with (
        patch.object(
            DhwSensor, "is_faked", new_callable=PropertyMock, return_value=True
        ),
        patch("ramses_rf.device.heat.Command.put_dhw_temp") as mock_cmd_gen,
    ):
        mock_cmd = MagicMock()
        mock_cmd_gen.return_value = mock_cmd

        await device.set_temperature(45.0)

        mock_cmd_gen.assert_called_once_with(device.id, 45.0)
        mock_gwy.async_send_cmd.assert_awaited_once()


@pytest.mark.asyncio
async def test_weather_temperature_message_store_fallback(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Test OutSensor falls back to the persistent message_store."""
    device = OutSensor(mock_gwy, mock_addr)
    device.entity_state = MagicMock()
    device.entity_state.get_value = AsyncMock(return_value=None)

    # Mock the database returning a cached 0002 packet
    mock_msg = MagicMock()
    mock_msg.payload = {SZ_TEMPERATURE: 12.5}
    mock_gwy.message_store.get.return_value = [mock_msg]

    temp = await device.temperature()

    assert temp == 12.5
    mock_gwy.message_store.get.assert_called_once_with(code=Code._0002, src=device.id)


@pytest.mark.asyncio
async def test_weather_temperature_set_faked(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Test OutSensor faking triggers put_outdoor_temp."""
    device = OutSensor(mock_gwy, mock_addr)

    with (
        patch.object(
            OutSensor, "is_faked", new_callable=PropertyMock, return_value=True
        ),
        patch("ramses_rf.device.heat.Command.put_outdoor_temp") as mock_cmd_gen,
    ):
        mock_cmd = MagicMock()
        mock_cmd_gen.return_value = mock_cmd

        await device.set_temperature(8.0)

        mock_cmd_gen.assert_called_once_with(device.id, 8.0)
        mock_gwy.async_send_cmd.assert_awaited_once()


@pytest.mark.asyncio
async def test_trv_actuator_heat_demand(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Test TrvActuator heat demand 0% fallback when setpoint is False."""
    device = TrvActuator(mock_gwy, mock_addr)
    device.entity_state = MagicMock()

    # 1. State store returns None, Setpoint is False -> Demand is 0
    device.entity_state.get_value = AsyncMock(return_value=None)

    with patch.object(device, "setpoint", AsyncMock(return_value=False)):
        assert await device.heat_demand() == 0

    # 2. State store returns valid demand
    async def mock_get_value(code: Code | tuple, **kwargs: Any) -> float:
        return 0.35

    device.entity_state.get_value = AsyncMock(side_effect=mock_get_value)
    assert await device.heat_demand() == 0.35


@pytest.mark.asyncio
async def test_otb_gateway_modulation_quarantine_fallback(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Test OtbGateway modulation falls back to RAMSES due to quarantine."""
    device = OtbGateway(mock_gwy, mock_addr)
    mock_gwy.config.use_native_ot = "prefer"
    device.entity_state = MagicMock()

    # Simulate RAMSES returning 0.45
    device.entity_state.get_value = AsyncMock(return_value=0.45)

    # Inject a fake OpenTherm message. Because MsgId._11 is in the
    # quarantine list, _ot_msg_value will ignore this and return None,
    # forcing the fallback to RAMSES.
    mock_msg = MagicMock()
    mock_msg.payload = {"value": 0.60}  # SZ_VALUE
    mock_msg._expired = False
    device._msgs_ot[MsgId._11] = mock_msg

    level = await device.rel_modulation_level()

    assert level == 0.45
    device.entity_state.get_value.assert_awaited_once()


@pytest.mark.asyncio
async def test_otb_gateway_pressure_prefer(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Test standard prefer logic prioritizes OT (e.g., water pressure)."""
    device = OtbGateway(mock_gwy, mock_addr)
    mock_gwy.config.use_native_ot = "prefer"
    device.entity_state = MagicMock()
    device.entity_state.get_value = AsyncMock()

    with patch.object(device, "_ot_msg_value", return_value=1.5) as mock_ot:
        pressure = await device.ch_water_pressure()

        assert pressure == 1.5
        mock_ot.assert_called_once()
        device.entity_state.get_value.assert_not_called()


@pytest.mark.asyncio
async def test_otb_gateway_modulation_avoid(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Test OtbGateway prioritizes RAMSES when native_ot is avoid."""
    device = OtbGateway(mock_gwy, mock_addr)
    mock_gwy.config.use_native_ot = "avoid"
    device.entity_state = MagicMock()

    # Provide both values, ensure RAMSES wins
    device.entity_state.get_value = AsyncMock(return_value=0.40)

    with patch.object(device, "_ot_msg_value", return_value=0.60):
        level = await device.rel_modulation_level()

        assert level == 0.40
        device.entity_state.get_value.assert_awaited_once()


@pytest.mark.asyncio
async def test_otb_gateway_modulation_avoid_fallback(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Test OtbGateway falls back to OT when native_ot is avoid but empty."""
    device = OtbGateway(mock_gwy, mock_addr)
    mock_gwy.config.use_native_ot = "avoid"
    device.entity_state = MagicMock()

    # RAMSES returns None, OT returns value -> OT wins as fallback
    device.entity_state.get_value = AsyncMock(return_value=None)

    with patch.object(device, "_ot_msg_value", return_value=0.75) as mock_ot:
        level = await device.rel_modulation_level()

        assert level == 0.75
        device.entity_state.get_value.assert_awaited_once()
        mock_ot.assert_called_once()


@pytest.mark.asyncio
async def test_otb_gateway_water_pressure_packet_flow(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Verify end-to-end packet processing for CH Water Pressure (0x12)."""
    device = OtbGateway(mock_gwy, mock_addr)
    # Force 'avoid' to test the RAMSES failure -> OT fallback path
    mock_gwy.config.use_native_ot = "avoid"
    device.entity_state = MagicMock()
    device.entity_state.get_value = AsyncMock(return_value=None)

    # 1. Simulate an arriving 3220 OpenTherm RP packet for Water Pressure
    msg = _create_ot_msg(0x12, OtMsgType.READ_ACK, 1.5, "ch_water_pressure")
    device._handle_msg(msg)

    # 2. Assert the fixed fallback logic retrieves the value from the OT cache
    pressure = await device.ch_water_pressure()

    assert pressure == 1.5
    # Confirm it attempted to fetch RAMSES Code._1300 first, failed, and fell back
    device.entity_state.get_value.assert_awaited_once_with(Code._1300, key=SZ_PRESSURE)


@pytest.mark.asyncio
async def test_otb_gateway_boiler_temp_packet_flow(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Verify end-to-end processing for Boiler Output Temp (Data-ID 0x19)."""
    device = OtbGateway(mock_gwy, mock_addr)
    # Force 'avoid' to test the RAMSES failure -> OT fallback path
    mock_gwy.config.use_native_ot = "avoid"
    device.entity_state = MagicMock()
    device.entity_state.get_value = AsyncMock(return_value=None)

    # 1. Simulate an arriving 3220 OpenTherm I_ packet for Boiler Temp
    msg = _create_ot_msg(0x19, OtMsgType.DATA_INVALID, None, "boiler_temp")
    device._handle_msg(msg)

    # 2. Inject valid packet
    msg_valid = _create_ot_msg(0x19, OtMsgType.READ_ACK, 45.5, "boiler_temp", I_)
    device._handle_msg(msg_valid)

    temp = await device.boiler_output_temp()

    assert temp == 45.5
    device.entity_state.get_value.assert_awaited_once_with(
        Code._3200, key=SZ_TEMPERATURE
    )


@pytest.mark.asyncio
async def test_otb_gateway_status_flags_packet_flow(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Verify correct bitmask extraction for Status Flags (Data-ID 0x00)."""
    device = OtbGateway(mock_gwy, mock_addr)
    device.entity_state = MagicMock()
    device.entity_state.get_value = AsyncMock(return_value=None)

    # Setup 16-bit status flag array (0-indexed)
    # Fault Present = index 8, Flame Active = index 11 (8 + 3)
    flags = [0] * 16
    flags[8] = 1
    flags[11] = 1

    msg = _create_ot_msg(0x00, OtMsgType.READ_ACK, flags, "status")
    device._handle_msg(msg)

    fault = await device.fault_present()
    flame = await device.flame_active()
    cooling = await device.cooling_active()  # index 12 (8 + 4), should be False

    assert fault is True
    assert flame is True
    assert cooling is False


@pytest.mark.asyncio
async def test_otb_gateway_ignores_unknown_data_id(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Ensure invalid/unknown OpenTherm packets are safely dropped."""
    device = OtbGateway(mock_gwy, mock_addr)
    device.entity_state = MagicMock()
    device.entity_state.get_value = AsyncMock(return_value=None)

    # Simulate Data-ID 0x73 (OEM code) returning an Unknown Data ID error
    msg = _create_ot_msg(0x73, OtMsgType.UNKNOWN_DATAID, None, "oem_code")
    device._handle_msg(msg)

    # The payload is dropped, so the sensor should safely evaluate to None
    oem_code = await device.oem_code()
    assert oem_code is None


@pytest.mark.asyncio
async def test_controller_discovers_system_mode(mock_gwy: MagicMock) -> None:
    """Test that the Controller actively polls for system_mode (2E04) on startup."""
    # 1. Override the fixture to ENABLE discovery for this specific test
    mock_gwy.config.disable_discovery = False

    # 2. Create a mock address for an Evohome Controller (type '01')
    mock_addr = MagicMock(spec=Address)
    mock_addr.id = "01:111111"
    mock_addr.type = "01"

    # 3. Instantiate the Controller
    device = Controller(mock_gwy, mock_addr)

    # 4. Explicitly trigger the discovery setup phase (normally done by the Gateway)
    device._setup_discovery_cmds()

    # 5. Extract all queued discovery commands scheduled by the device
    # device.discovery.cmds is a dictionary keyed by the packet header
    queued_cmds = [task["command"].code for task in device.discovery.cmds.values()]

    # 6. Assert that the 2E04 (System Mode) packet was queued for polling
    assert Code._2E04 in queued_cmds, (
        "Diagnosis Failed: Controller did not queue a 2E04 (System Mode) "
        "packet during discovery initialization."
    )
