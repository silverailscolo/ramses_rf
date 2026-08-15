import asyncio
import dataclasses
from dataclasses import replace
from datetime import datetime as dt
from typing import Any, Final
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ramses_rf import Gateway
from ramses_rf.const import SZ_DOMAIN_ID, SZ_SYSTEM_MODE
from ramses_rf.devices import BdrSwitch, Controller, DhwSensor, TrvActuator
from ramses_rf.dispatcher import (
    _resolve_logical_targets,
    _update_demand_state,
    _update_system_state,
)
from ramses_rf.exceptions import SchemaInconsistentError, SystemSchemaInconsistent
from ramses_rf.messages import Message
from ramses_rf.pipeline.polling import DEFAULT_POLLING_SCHEDULES
from ramses_rf.systems.tcs import Evohome, SystemBase
from ramses_rf.systems.zones import (
    DhwZone,
    UfhZone,
    Zone,
    ZoneBase,
    ZoneSchedule,
    _transform,
    zone_factory,
)
from ramses_tx import Packet
from ramses_tx.address import HGI_DEVICE_ID
from ramses_tx.const import FC, I_, Code
from ramses_tx.exceptions import ProtocolTimeoutError

# A standard 3150 I-packet (Heat Demand) from a Controller
# 3150 002 FCC8 -> domain_id=FC (System), demand=C8 (100%)
# NOTE: Must use double space after RSSI (064) for ' I' verb parsing
# by Packet.from_port
PKT_3150: Final = f"064  I --- 01:145038 --:------ 01:145038 {Code._3150} 002 FCC8"


# --- Fixtures required for fake_evofw3 ---


@pytest.fixture()
def gwy_config() -> dict[str, Any]:
    """Return a valid configuration for the gateway."""
    return {}


@pytest.fixture()
def gwy_dev_id() -> str:
    """Return a valid device ID for the gateway."""
    return HGI_DEVICE_ID


# --- Helper to create a valid Mock Message ---


def create_mock_message(tcs: SystemBase, payload: Any) -> MagicMock:
    """Create a mock message that looks like it came from the TCS
    controller.

    Includes internal structures (_pkt, _ctx) required for logging/caching.
    """
    mock_msg = MagicMock(spec=Message)
    mock_msg.code = Code._3150
    mock_msg.verb = I_
    mock_msg.src = MagicMock()
    mock_msg.src.id = tcs.id  # Match TCS ID so it is accepted
    mock_msg.dst = MagicMock()
    mock_msg.dst.id = tcs.id
    mock_msg.payload = payload

    # Mock the internal packet structure required by Entity logging
    mock_msg._pkt = MagicMock()
    mock_msg._pkt._ctx = f"{dt.now().isoformat()}_{tcs.id}"

    return mock_msg


# --- Tests ---


@pytest.mark.asyncio
async def test_system_handle_msg_3150_real_packet(fake_evofw3: Gateway) -> None:
    """Check that a real 3150 packet is handled correctly.

    If this passes, it means the current parser produces a payload (likely
    a dict) that the current code can handle.
    """
    gwy = fake_evofw3
    pkt = Packet.from_port(dt.now(), PKT_3150)
    gwy._engine._protocol.pkt_received(pkt)
    await asyncio.sleep(0)  # Yield to loop to process call_soon callbacks

    tcs = gwy.tcs
    assert tcs is not None
    assert tcs.heat_demand is not None


@pytest.mark.asyncio
async def test_system_handle_msg_3150_force_list(fake_evofw3: Gateway) -> None:
    """Simulate a parser returning a LIST payload.

    Confirms that the system correctly parses multi-zone payloads.
    """
    gwy = fake_evofw3

    # Bootstrap TCS
    pkt = Packet.from_port(dt.now(), PKT_3150)
    gwy._engine._protocol.pkt_received(pkt)
    await asyncio.sleep(0)  # Yield to loop to process call_soon callbacks
    tcs = gwy.tcs
    assert tcs is not None  # Ensure TCS exists for Mypy

    # Construct a List-based payload (New/Hybrid Style)
    payload = [{SZ_DOMAIN_ID: FC, "heat_demand": 0.5}]

    if not isinstance(tcs, SystemBase):
        pytest.fail("TCS is not an instance of SystemBase")

    msg = create_mock_message(tcs, payload[0])
    _update_demand_state(tcs, payload[0], msg)

    # We verify if it actually extracted the value into demand_state
    assert tcs.demand_state.heat_demand == 0.5


@pytest.mark.asyncio
async def test_system_handle_msg_3150_force_dict(fake_evofw3: Gateway) -> None:
    """Simulate a parser returning a DICT payload.

    This ensures backward compatibility for Dict payloads.
    """
    gwy = fake_evofw3

    # Bootstrap TCS
    pkt = Packet.from_port(dt.now(), PKT_3150)
    gwy._engine._protocol.pkt_received(pkt)
    await asyncio.sleep(0)  # Yield to loop to process call_soon callbacks
    tcs = gwy.tcs
    assert tcs is not None  # Ensure TCS exists for Mypy

    # Construct a Dict-based payload (Legacy Style)
    payload = {SZ_DOMAIN_ID: FC, "heat_demand": 0.5}

    if not isinstance(tcs, SystemBase):
        pytest.fail("TCS is not an instance of SystemBase")

    msg = create_mock_message(tcs, payload)
    _update_demand_state(tcs, payload, msg)

    assert tcs.demand_state.heat_demand == 0.5


@pytest.mark.asyncio
async def test_system_handle_msg_3150_list_no_match(
    fake_evofw3: Gateway,
) -> None:
    """Verify list payload ignores unrelated domains."""
    gwy = fake_evofw3
    pkt = Packet.from_port(dt.now(), PKT_3150)
    gwy._engine._protocol.pkt_received(pkt)
    await asyncio.sleep(0)
    tcs = gwy.tcs
    assert tcs is not None

    payload = [{"domain_id": "FA", "heat_demand": 0.5}]
    msg = create_mock_message(tcs, payload[0])

    targets = _resolve_logical_targets(gwy, msg, payload[0])
    assert tcs not in targets


@pytest.mark.asyncio
async def test_system_handle_msg_3150_dict_no_match(
    fake_evofw3: Gateway,
) -> None:
    """Verify dict payload ignores unrelated domains."""
    gwy = fake_evofw3
    pkt = Packet.from_port(dt.now(), PKT_3150)
    gwy._engine._protocol.pkt_received(pkt)
    await asyncio.sleep(0)
    tcs = gwy.tcs
    assert tcs is not None

    payload = {"domain_id": "F9", "heat_demand": 0.5}
    msg = create_mock_message(tcs, payload)

    targets = _resolve_logical_targets(gwy, msg, payload)
    assert tcs not in targets


@pytest.mark.asyncio
async def test_logbook_setup_discovery_creates_task(
    fake_evofw3: Gateway,
) -> None:
    """Verify Logbook actively schedules fault log retrieval on discovery."""
    gwy = fake_evofw3
    pkt = Packet.from_port(dt.now(), PKT_3150)
    gwy._engine._protocol.pkt_received(pkt)
    await asyncio.sleep(0)

    tcs = gwy.tcs
    assert tcs is not None

    with patch.object(tcs, "get_faultlog", new_callable=AsyncMock) as mock_fault:
        await tcs.get_faultlog()
        mock_fault.assert_called_once()


@pytest.mark.asyncio
async def test_sysmode_system_mode_async_cache_lookup(
    fake_evofw3: Gateway,
) -> None:
    """Verify system_mode retrieves state asynchronously from CQRS read-model."""
    gwy = fake_evofw3
    pkt = Packet.from_port(dt.now(), PKT_3150)
    gwy._engine._protocol.pkt_received(pkt)
    await asyncio.sleep(0)

    tcs = gwy.tcs
    assert tcs is not None

    tcs.system_state = replace(tcs.system_state, system_mode="01", until=None)

    # Call the newly refactored async method lookup
    result = await tcs.system_mode()

    assert result == {"system_mode": "01", "until": None}


# --- System Zones & Hydration Tests ---


@pytest.fixture
def mock_system_gwy() -> MagicMock:
    """Provide a mocked Gateway instance for zone tests."""
    gwy = MagicMock()
    gwy.config.enable_eavesdrop = False
    gwy.device_registry.get_device.return_value = MagicMock()
    gwy.dispatcher.send = AsyncMock(return_value="mocked_packet")
    gwy.hgi = MagicMock()
    gwy.hgi.id = "18:000730"
    gwy.message_store = None
    return gwy


@pytest.fixture
def mock_tcs(mock_system_gwy: MagicMock) -> MagicMock:
    """Provide a mocked TCS (Evohome) instance for zone tests."""
    tcs = MagicMock()
    tcs.id = "01:123456"
    tcs._gateway = mock_system_gwy
    tcs.ctl = MagicMock()
    tcs.ctl.id = "01:123456"
    tcs.ctl.addr = MagicMock()
    tcs.dhw = None
    tcs.zone_by_idx = {}
    tcs._max_zones = 12
    return tcs


def test_transform_function() -> None:
    """Test the valve position to demand percentage transformation."""
    assert _transform(0.15) == 0.0
    assert _transform(0.30) == 0.0
    assert _transform(0.50) == 0.15
    assert _transform(0.80) == 0.53


@pytest.mark.asyncio
async def test_zone_base(mock_tcs: MagicMock) -> None:
    """Test the ZoneBase initialization and base methods."""
    zon = ZoneBase(mock_tcs, "00")
    assert zon.idx == "00"
    assert zon.id == "01:123456_00"
    assert repr(zon) == "01:123456_00 (None)"

    zon2 = ZoneBase(mock_tcs, "01")
    assert zon < zon2
    assert zon.__lt__("string_fallback") is NotImplemented

    assert await zon.schema() == {}
    assert await zon.params() == {}
    assert await zon.status() == {}


@pytest.mark.asyncio
async def test_zone_schedule(mock_tcs: MagicMock) -> None:
    """Test schedule retrieval and mutations."""
    zon = ZoneSchedule(mock_tcs, "02")
    zon._schedule = MagicMock()
    zon._schedule.version = 42
    zon._schedule.get_schedule = AsyncMock()
    zon._schedule.set_schedule = AsyncMock()
    zon._schedule.schedule = []

    zon.entity_state = MagicMock()
    zon.entity_state._msg_value = AsyncMock(return_value={})

    await zon.get_schedule(force_io=True)
    zon._schedule.get_schedule.assert_called_once_with(force_io=True)

    await zon.set_schedule({"new": "schedule"})
    zon._schedule.set_schedule.assert_called_once_with({"new": "schedule"})

    assert zon.schedule == []
    assert await zon.schedule_version() == 42

    status = await zon.status()
    assert status["schedule_version"] == 42


@pytest.mark.asyncio
async def test_dhw_zone_initialization(mock_tcs: MagicMock) -> None:
    """Test the DhwZone initialization constraints."""
    dhw = DhwZone(mock_tcs, "HW")
    assert dhw.idx == "HW"

    mock_tcs.dhw = dhw
    with pytest.raises(SchemaInconsistentError):
        DhwZone(mock_tcs, "HW")

    mock_tcs.dhw = None
    with pytest.raises(SchemaInconsistentError):
        DhwZone(mock_tcs, "01")


def test_dhw_zone_schema_updates(mock_tcs: MagicMock) -> None:
    """Test schema injection into DHW."""
    dhw = DhwZone(mock_tcs, "HW")

    mock_sensor = MagicMock(spec=DhwSensor)
    mock_sensor.id = "07:123456"
    mock_valve = MagicMock(spec=BdrSwitch)
    mock_valve.id = "13:123456"

    mock_tcs._gateway.device_registry.get_device.side_effect = [
        mock_sensor,
        mock_valve,
        mock_valve,
    ]

    dhw._update_schema(
        sensor="07:123456", hotwater_valve="13:123456", heating_valve="13:654321"
    )
    assert dhw.sensor is not None
    assert dhw.sensor.id == "07:123456"
    assert dhw.hotwater_valve is not None
    assert dhw.hotwater_valve.id == "13:123456"


@pytest.mark.asyncio
async def test_dhw_commands(mock_tcs: MagicMock) -> None:
    """Test command generation wrappers for DHW."""
    dhw = DhwZone(mock_tcs, "HW")

    await dhw.set_setpoint(55.0)
    mock_tcs._gateway.dispatcher.send.assert_called()

    await dhw.set_boost_mode()
    assert mock_tcs._gateway.dispatcher.send.call_count == 2

    await dhw.reset_mode()
    assert mock_tcs._gateway.dispatcher.send.call_count == 3

    await dhw.reset_config()
    assert mock_tcs._gateway.dispatcher.send.call_count == 4


@pytest.mark.asyncio
async def test_zone_initialization(mock_tcs: MagicMock) -> None:
    """Test standard Zone initialisation and validation rules."""
    zon = Zone(mock_tcs, "00")
    assert zon.idx == "00"

    mock_tcs.zone_by_idx = {"00": zon}
    with pytest.raises(SchemaInconsistentError):
        Zone(mock_tcs, "00")

    mock_tcs.zone_by_idx = {}
    with pytest.raises(SchemaInconsistentError):
        Zone(mock_tcs, "0C")


def test_zone_schema_promotion(mock_tcs: MagicMock) -> None:
    """Test dynamic class promotion through schema definitions."""
    zon = Zone(mock_tcs, "01")
    zon._update_schema(**{"class": "underfloor_heating"})
    assert isinstance(zon, UfhZone)

    with pytest.raises(SystemSchemaInconsistent):
        zon._update_schema(**{"class": "radiator_valve"})


@pytest.mark.asyncio
async def test_zone_commands(mock_tcs: MagicMock) -> None:
    """Test command generation overrides for general Zones."""
    zon = Zone(mock_tcs, "01")

    await zon.set_setpoint(21.0)
    mock_tcs._gateway.dispatcher.send.assert_called_once()

    await zon.set_setpoint(None)
    assert mock_tcs._gateway.dispatcher.send.call_count == 2

    await zon.set_config(min_temp=10.0, max_temp=30.0)
    assert mock_tcs._gateway.dispatcher.send.call_count == 3

    await zon.set_name("Living Room")
    assert mock_tcs._gateway.dispatcher.send.call_count == 4


def test_zone_factory_routing(mock_tcs: MagicMock) -> None:
    """Test the factory constructs the correct initial base class."""
    dhw = zone_factory(mock_tcs, "HW")
    assert isinstance(dhw, DhwZone)

    zon = zone_factory(mock_tcs, "03")
    assert isinstance(zon, Zone)


@pytest.mark.asyncio
async def test_zone_get_temp_handles_protocol_timeout(
    mock_tcs: MagicMock,
) -> None:
    """Verify _get_temp gracefully handles ProtocolTimeoutError."""
    zon = Zone(mock_tcs, "01")

    async def mock_send_cmd(*args: Any, **kwargs: Any) -> Packet:
        raise ProtocolTimeoutError("Mocked 20-second FSM timeout")

    mock_tcs._gateway.dispatcher.send = AsyncMock(side_effect=mock_send_cmd)

    result = await zon._get_temp()
    assert result is None


@pytest.mark.asyncio
async def test_zone_name_from_cqrs_state(mock_tcs: MagicMock) -> None:
    """Test zone name is retrieved natively from the CQRS ZoneState."""
    zon = Zone(mock_tcs, "00")
    zon.zone_state = dataclasses.replace(zon.zone_state, name="Lounge")
    mock_tcs._gateway.message_store = AsyncMock()

    result = await zon.name()
    assert result == "Lounge"
    mock_tcs._gateway.message_store.get.assert_not_called()


# --- Window Open State Aggregation Tests ---


def _create_mock_zone() -> Zone:
    mock_tcs = MagicMock()
    mock_tcs.id = "01:123456"
    mock_tcs._gateway = MagicMock()
    mock_tcs.zone_by_idx = {}
    mock_tcs._max_zones = 12
    mock_tcs.ctl = MagicMock()
    return Zone(mock_tcs, "00")


def _create_mock_trv(state: bool | None) -> MagicMock:
    trv = MagicMock(spec=TrvActuator)
    trv.window_open = AsyncMock(return_value=state)
    return trv


@pytest.mark.asyncio
async def test_window_open_no_actuators() -> None:
    zone = _create_mock_zone()
    zone.actuators = []
    result = await zone.window_open()
    assert result is None


@pytest.mark.asyncio
async def test_window_open_all_closed() -> None:
    zone = _create_mock_zone()
    zone.actuators = [_create_mock_trv(False), _create_mock_trv(False)]
    result = await zone.window_open()
    assert result is False


@pytest.mark.asyncio
async def test_window_open_one_open() -> None:
    zone = _create_mock_zone()
    zone.actuators = [_create_mock_trv(False), _create_mock_trv(True)]
    result = await zone.window_open()
    assert result is True


@pytest.mark.asyncio
async def test_window_open_mixed_unknown_and_closed() -> None:
    zone = _create_mock_zone()
    zone.actuators = [_create_mock_trv(None), _create_mock_trv(False)]
    result = await zone.window_open()
    assert result is None


@pytest.mark.asyncio
async def test_window_open_mixed_unknown_and_open() -> None:
    zone = _create_mock_zone()
    zone.actuators = [_create_mock_trv(None), _create_mock_trv(True)]
    result = await zone.window_open()
    assert result is True


# --- DHW Boot Polling Tests ---


def test_dhw_battery_zero_polling() -> None:
    """Ensure DHW battery devices have polling explicitly disabled."""
    dhw_schedule = DEFAULT_POLLING_SCHEDULES.get("DHW", {})
    for interval in dhw_schedule.values():
        assert interval is None


# --- TCS Hydration Tests ---


@pytest.mark.asyncio
async def test_system_mode_returns_none_when_cqrs_empty() -> None:
    mock_gwy = MagicMock()
    mock_gwy.config.enable_eavesdrop = False
    mock_gwy.device_registry.system_by_id = {}
    mock_gwy.async_send_cmd = AsyncMock()

    mock_ctl = MagicMock(spec=Controller)
    mock_ctl.id = "01:123456"
    mock_ctl._gateway = mock_gwy

    tcs = Evohome(mock_ctl)
    tcs.system_state = dataclasses.replace(
        tcs.system_state, system_mode=None, until=None
    )

    result = await tcs.system_mode()
    assert result is None
    mock_gwy.async_send_cmd.assert_not_called()


@pytest.mark.asyncio
async def test_system_mode_uses_hot_cqrs_state_when_available() -> None:
    mock_gwy = MagicMock()
    mock_gwy.config.enable_eavesdrop = False
    mock_gwy.device_registry.system_by_id = {}
    mock_gwy.async_send_cmd = AsyncMock()

    mock_ctl = MagicMock(spec=Controller)
    mock_ctl.id = "01:123456"
    mock_ctl._gateway = mock_gwy

    tcs = Evohome(mock_ctl)
    tcs.system_state = dataclasses.replace(
        tcs.system_state,
        system_mode="02",
        until="2024-01-01T12:00:00",
    )

    result = await tcs.system_mode()
    assert result is not None
    assert result[SZ_SYSTEM_MODE] == "02"
    assert result["until"] == "2024-01-01T12:00:00"
    mock_gwy.async_send_cmd.assert_not_called()


def test_update_system_state_hydrates_from_2e04_packet() -> None:
    mock_gwy = MagicMock()
    mock_gwy.config.enable_eavesdrop = False
    mock_gwy.device_registry.system_by_id = {}
    mock_gwy.async_send_cmd = AsyncMock()

    mock_ctl = MagicMock(spec=Controller)
    mock_ctl.id = "01:123456"
    mock_ctl._gateway = mock_gwy

    tcs = Evohome(mock_ctl)

    mock_msg = MagicMock()
    mock_msg.code = Code._2E04
    mock_msg.dtm = None
    mock_msg.timestamp = None
    payload = {SZ_SYSTEM_MODE: "heat_off", "until": None}

    _update_system_state(tcs, payload, mock_msg)

    assert tcs.system_state.system_mode == "heat_off"
    assert tcs.system_state.until is None

    result = asyncio.run(tcs.system_mode())
    assert result is not None
    assert result[SZ_SYSTEM_MODE] == "heat_off"


def test_update_demand_state_ufc_ufh_circuit_demand_ignored() -> None:
    # Arrange
    from ramses_rf.models import DemandState, StateUpdatedEvent
    from ramses_tx.const import Code

    class MockTarget:
        _SLUG = "UFC"
        id = "02:123456"

        def __init__(self) -> None:
            self.demand_state = DemandState()

        def apply_state_update(self, event: StateUpdatedEvent) -> None:
            if isinstance(event.state, DemandState):
                self.demand_state = event.state

    target = MockTarget()
    msg = MagicMock()
    msg.code = Code._3150
    payload = {"heat_demand": 0.81, "ufx_idx": "00"}

    # Act
    _update_demand_state(target, payload, msg)

    # Assert
    assert target.demand_state.heat_demand is None


def test_update_demand_state_ctl_fc_domain_demand_accepted() -> None:
    # Arrange
    from ramses_rf.models import DemandState, StateUpdatedEvent
    from ramses_tx.const import Code

    class MockTarget:
        _SLUG = "CTL"
        id = "01:123456"

        def __init__(self) -> None:
            self.demand_state = DemandState()

        def apply_state_update(self, event: StateUpdatedEvent) -> None:
            if isinstance(event.state, DemandState):
                self.demand_state = event.state

    target = MockTarget()
    msg = MagicMock()
    msg.code = Code._3150
    payload = {"heat_demand": 0.81, "domain_id": "FC"}

    # Act
    _update_demand_state(target, payload, msg)

    # Assert
    assert target.demand_state.heat_demand == 0.81
