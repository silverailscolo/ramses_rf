#!/usr/bin/env python3
"""RAMSES RF - Unit and parity tests for Outbound Command Dispatching."""

from __future__ import annotations

import asyncio
from datetime import datetime as dt
from unittest.mock import AsyncMock, MagicMock

import pytest

from ramses_rf.address import Address
from ramses_rf.commands.dispatcher import CommandDispatcher
from ramses_rf.const import SYS_MODE_MAP, ZON_MODE_MAP
from ramses_rf.devices import Controller, HvacVentilator
from ramses_rf.gateway import Gateway
from ramses_rf.messages import Message
from ramses_rf.systems import DhwZone, Evohome, Zone
from ramses_tx import Code, Packet
from ramses_tx.dtos import CommandDTO


@pytest.fixture
async def mock_gateway() -> MagicMock:
    """Create a mock Gateway instance with dispatcher wiring."""
    gateway = MagicMock(spec=Gateway)
    gateway.__class__ = Gateway  # type: ignore[assignment]
    gateway._loop = asyncio.get_running_loop()
    gateway._async_send_dto = AsyncMock()
    gateway.conversation_manager = None
    gateway.add_task = MagicMock()
    gateway.hgi = None
    gateway.device_registry = MagicMock()
    gateway.device_registry.system_by_id = {}

    # Wire a real CommandDispatcher backed by the mock gateway
    dispatcher = CommandDispatcher(gateway)
    gateway.dispatcher = dispatcher

    return gateway


@pytest.mark.asyncio
async def test_zone_set_temperature_dispatches_intent(
    mock_gateway: MagicMock,
) -> None:
    """Verify Zone.set_setpoint dispatches Action.SET_TEMPERATURE via CommandDispatcher."""
    # Arrange
    tcs = MagicMock(spec=Evohome)
    tcs._gateway = mock_gateway
    tcs.ctl = MagicMock()
    tcs.ctl.id = "01:078710"
    tcs.id = "01:078710"
    tcs._max_zones = 12
    tcs.zone_by_index = {}
    tcs.zone_by_idx = {}
    tcs.zones = []
    tcs.childs = []

    zone = Zone(tcs, "00")
    packet = Packet.from_port(
        dt.now(),
        "000  I --- 18:000730 01:078710 --:------ 2349 007 00083401078710",
    )
    mock_gateway._async_send_dto.return_value = packet

    # Act
    result = await zone.set_setpoint(21.0)

    # Assert
    assert isinstance(result, Message)
    assert mock_gateway._async_send_dto.await_count == 1
    call_dto: CommandDTO = mock_gateway._async_send_dto.call_args[0][0]
    assert call_dto.code == Code._2309
    assert call_dto.addr3 == "01:078710"


@pytest.mark.asyncio
async def test_zone_set_mode_dispatches_intent(
    mock_gateway: MagicMock,
) -> None:
    """Verify Zone.set_mode dispatches Action.SET_MODE via CommandDispatcher."""
    # Arrange
    tcs = MagicMock(spec=Evohome)
    tcs._gateway = mock_gateway
    tcs.ctl = MagicMock()
    tcs.ctl.id = "01:078710"
    tcs.id = "01:078710"
    tcs._max_zones = 12
    tcs.zone_by_index = {}
    tcs.zone_by_idx = {}
    tcs.zones = []
    tcs.childs = []

    zone = Zone(tcs, "01")
    packet = Packet.from_port(
        dt.now(),
        "000  I --- 18:000730 01:078710 --:------ 2349 007 0107D000FFFFFF",
    )
    mock_gateway._async_send_dto.return_value = packet

    # Act
    result = await zone.set_mode(mode=ZON_MODE_MAP.PERMANENT, setpoint=20.0)

    # Assert
    assert isinstance(result, Message)
    assert mock_gateway._async_send_dto.await_count == 1
    call_dto: CommandDTO = mock_gateway._async_send_dto.call_args[0][0]
    assert call_dto.code == Code._2349


@pytest.mark.asyncio
async def test_hvac_ventilator_set_fan_mode_dispatches_intent(
    mock_gateway: MagicMock,
) -> None:
    """Verify HvacVentilator.set_fan_mode dispatches Action.SET_FAN_MODE."""
    # Arrange
    vent = HvacVentilator(mock_gateway, Address("32:208628"))
    vent.get_bound_rem = MagicMock(return_value="32:208628")  # type: ignore[method-assign]
    packet = Packet.from_port(
        dt.now(),
        "000  I --- 18:000730 32:208628 --:------ 22F1 003 00020A",
    )
    mock_gateway._async_send_dto.return_value = packet

    # Act
    result = await vent.set_fan_mode("auto")

    # Assert
    assert isinstance(result, Message)
    assert mock_gateway._async_send_dto.await_count == 1
    call_dto: CommandDTO = mock_gateway._async_send_dto.call_args[0][0]
    assert call_dto.code == Code._22F1
    assert call_dto.addr1 == "32:208628"


@pytest.mark.asyncio
async def test_hvac_ventilator_probe_2411_dispatches_intent(
    mock_gateway: MagicMock,
) -> None:
    """Verify HvacVentilator.async_probe_2411_support dispatches Action.GET_FAN_PARAM."""
    # Arrange
    vent = HvacVentilator(mock_gateway, Address("32:208628"))
    packet = Packet.from_port(
        dt.now(),
        "000 RP --- 32:208628 18:000730 --:------ 2411 003 000001",
    )
    mock_gateway._async_send_dto.return_value = packet

    # Act
    success = await vent.async_probe_2411_support()

    # Assert
    assert success is True
    assert mock_gateway._async_send_dto.await_count == 1
    call_dto: CommandDTO = mock_gateway._async_send_dto.call_args[0][0]
    assert call_dto.code == Code._2411
    assert call_dto.addr2 == "32:208628"


@pytest.mark.asyncio
async def test_dhw_zone_set_mode_dispatches_intent(
    mock_gateway: MagicMock,
) -> None:
    """Verify DhwZone.set_mode dispatches Action.SET_DHW_MODE."""
    # Arrange
    tcs = MagicMock(spec=Evohome)
    tcs._gateway = mock_gateway
    tcs.ctl = MagicMock()
    tcs.ctl.id = "01:078710"
    tcs.id = "01:078710"
    tcs.dhw = None
    tcs.childs = []

    dhw = DhwZone(tcs)
    packet = Packet.from_port(
        dt.now(),
        "000  I --- 18:000730 01:078710 --:------ 1F41 006 000100FFFFFF",
    )
    mock_gateway._async_send_dto.return_value = packet

    # Act
    result = await dhw.set_mode(mode=ZON_MODE_MAP.PERMANENT, active=True)

    # Assert
    assert isinstance(result, Message)
    assert mock_gateway._async_send_dto.await_count == 1
    call_dto: CommandDTO = mock_gateway._async_send_dto.call_args[0][0]
    assert call_dto.code == Code._1F41


@pytest.mark.asyncio
async def test_tcs_set_mode_dispatches_intent(
    mock_gateway: MagicMock,
) -> None:
    """Verify Evohome.set_mode dispatches Action.SET_SYSTEM_MODE."""
    # Arrange
    ctl = Controller(mock_gateway, Address("01:078710"))
    tcs = Evohome(ctl)
    packet = Packet.from_port(
        dt.now(),
        "000  I --- 18:000730 01:078710 --:------ 2E04 005 0000000000",
    )
    mock_gateway._async_send_dto.return_value = packet

    # Act
    result = await tcs.set_mode(system_mode=SYS_MODE_MAP.AUTO)

    # Assert
    assert isinstance(result, Message)
    assert mock_gateway._async_send_dto.await_count == 1
    call_dto: CommandDTO = mock_gateway._async_send_dto.call_args[0][0]
    assert call_dto.code == Code._2E04
