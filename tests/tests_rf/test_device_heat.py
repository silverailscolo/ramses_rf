"""Test the ramses_rf.device.heat module."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from ramses_rf.device.heat import (
    BdrSwitch,
    DhwSensor,
    OtbGateway,
    OutSensor,
    Thermostat,
    TrvActuator,
)
from ramses_rf.exceptions import DeviceNotFaked
from ramses_tx import Code, Priority
from ramses_tx.address import Address
from ramses_tx.const import SZ_TEMPERATURE


@pytest.fixture
def mock_gwy() -> MagicMock:
    """Return a mock Gateway for device testing."""
    gwy = MagicMock()
    # Mock the persistent SQLite message database
    gwy.msg_db = AsyncMock()
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


@pytest.mark.asyncio
async def test_bdr_switch_relay_demand_standard(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Test BdrSwitch resolves relay demand from standard 0008 packet."""
    device = BdrSwitch(mock_gwy, mock_addr)
    device.state_store = MagicMock()

    # Simulate 0008 packet returning a valid demand
    async def mock_msg_value(code: Code | tuple, key: str) -> float | None:
        if code == Code._0008 and key == "relay_demand":
            return 0.45
        return None

    device.state_store._msg_value = AsyncMock(side_effect=mock_msg_value)

    demand = await device.relay_demand()
    assert demand == 0.45


@pytest.mark.asyncio
async def test_bdr_switch_relay_demand_fallback(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Test BdrSwitch falls back to 3EF0/3EF1 modulation for demand."""
    device = BdrSwitch(mock_gwy, mock_addr)
    device.state_store = MagicMock()

    # Simulate 0008 missing, but 3EF0/3EF1 available
    async def mock_msg_value(code: Code | tuple, key: str) -> float | None:
        if code == Code._0008:
            return None
        if code == (Code._3EF0, Code._3EF1) and key == "modulation_level":
            return 0.85
        return None

    device.state_store._msg_value = AsyncMock(side_effect=mock_msg_value)

    demand = await device.relay_demand()
    assert demand == 0.85


@pytest.mark.asyncio
async def test_temperature_msg_db_fallback(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Test Thermostat explicitly falls back to the persistent msg_db."""
    device = Thermostat(mock_gwy, mock_addr)
    device.state_store = MagicMock()
    device.state_store._msg_value = AsyncMock(return_value=None)

    # Mock the database returning a cached 30C9 packet
    mock_msg = MagicMock()
    mock_msg.payload = {SZ_TEMPERATURE: 21.5}
    mock_gwy.msg_db.get.return_value = [mock_msg]

    temp = await device.temperature()

    assert temp == 21.5
    mock_gwy.msg_db.get.assert_called_once_with(code=Code._30C9, src=device.id)


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
async def test_dhw_temperature_msg_db_fallback(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Test DhwSensor falls back to the persistent msg_db."""
    device = DhwSensor(mock_gwy, mock_addr)
    device.state_store = MagicMock()
    device.state_store._msg_value = AsyncMock(return_value=None)

    # Mock the database returning a cached 1260 packet
    mock_msg = MagicMock()
    mock_msg.payload = {SZ_TEMPERATURE: 55.0}
    mock_gwy.msg_db.get.return_value = [mock_msg]

    temp = await device.temperature()

    assert temp == 55.0
    mock_gwy.msg_db.get.assert_called_once_with(code=Code._1260, src=device.id)


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
async def test_weather_temperature_msg_db_fallback(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Test OutSensor falls back to the persistent msg_db."""
    device = OutSensor(mock_gwy, mock_addr)
    device.state_store = MagicMock()
    device.state_store._msg_value = AsyncMock(return_value=None)

    # Mock the database returning a cached 0002 packet
    mock_msg = MagicMock()
    mock_msg.payload = {SZ_TEMPERATURE: 12.5}
    mock_gwy.msg_db.get.return_value = [mock_msg]

    temp = await device.temperature()

    assert temp == 12.5
    mock_gwy.msg_db.get.assert_called_once_with(code=Code._0002, src=device.id)


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
    device.state_store = MagicMock()

    # 1. State store returns None, Setpoint is False -> Demand is 0
    device.state_store._msg_value = AsyncMock(return_value=None)

    with patch.object(device, "setpoint", AsyncMock(return_value=False)):
        assert await device.heat_demand() == 0

    # 2. State store returns valid demand
    async def mock_msg_value(code: Code | tuple, **kwargs: Any) -> float:
        return 0.35

    device.state_store._msg_value = AsyncMock(side_effect=mock_msg_value)
    assert await device.heat_demand() == 0.35


@pytest.mark.asyncio
async def test_otb_gateway_modulation_prefer(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Test OtbGateway modulation 'prefer' hack prioritizes RAMSES."""
    device = OtbGateway(mock_gwy, mock_addr)
    mock_gwy.config.use_native_ot = "prefer"
    device.state_store = MagicMock()

    # Because of a HACK in rel_modulation_level, "prefer" bypasses OT
    # and forces RAMSES state_store retrieval.
    device.state_store._msg_value = AsyncMock(return_value=0.45)

    with patch.object(device, "_ot_msg_value", return_value=0.60) as mock_ot:
        level = await device.rel_modulation_level()

        assert level == 0.45
        mock_ot.assert_not_called()
        device.state_store._msg_value.assert_awaited_once()


@pytest.mark.asyncio
async def test_otb_gateway_pressure_prefer(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Test standard prefer logic prioritizes OT (e.g., water pressure)."""
    device = OtbGateway(mock_gwy, mock_addr)
    mock_gwy.config.use_native_ot = "prefer"
    device.state_store = MagicMock()
    device.state_store._msg_value = AsyncMock()

    with patch.object(device, "_ot_msg_value", return_value=1.5) as mock_ot:
        pressure = await device.ch_water_pressure()

        assert pressure == 1.5
        mock_ot.assert_called_once()
        device.state_store._msg_value.assert_not_called()


@pytest.mark.asyncio
async def test_otb_gateway_modulation_avoid(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Test OtbGateway prioritizes RAMSES when native_ot is avoid."""
    device = OtbGateway(mock_gwy, mock_addr)
    mock_gwy.config.use_native_ot = "avoid"
    device.state_store = MagicMock()

    # Provide both values, ensure RAMSES wins
    device.state_store._msg_value = AsyncMock(return_value=0.40)

    with patch.object(device, "_ot_msg_value", return_value=0.60):
        level = await device.rel_modulation_level()

        assert level == 0.40
        device.state_store._msg_value.assert_awaited_once()


@pytest.mark.asyncio
async def test_otb_gateway_modulation_avoid_fallback(
    mock_gwy: MagicMock, mock_addr: MagicMock
) -> None:
    """Test OtbGateway falls back to OT when native_ot is avoid but empty."""
    device = OtbGateway(mock_gwy, mock_addr)
    mock_gwy.config.use_native_ot = "avoid"
    device.state_store = MagicMock()

    # RAMSES returns None, OT returns value -> OT wins as fallback
    device.state_store._msg_value = AsyncMock(return_value=None)

    with patch.object(device, "_ot_msg_value", return_value=0.75) as mock_ot:
        level = await device.rel_modulation_level()

        assert level == 0.75
        device.state_store._msg_value.assert_awaited_once()
        mock_ot.assert_called_once()
