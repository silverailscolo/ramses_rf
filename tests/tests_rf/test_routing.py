#!/usr/bin/env python3
"""Tests for L7 domain and message routing components."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest

from ramses_rf import dispatcher
from ramses_rf.const import DevType
from ramses_rf.devices import HvacVentilator
from ramses_rf.dispatcher import process_msg
from ramses_rf.gateway import Gateway
from ramses_rf.pipeline.ingestion import StateProjector
from ramses_rf.routing import EventTopic, RoutingContext, StateHeader
from ramses_rf.state import MessageStore
from ramses_rf.systems.zones import Zone
from ramses_tx import Address
from ramses_tx.const import I_, Code
from ramses_tx.typing import DeviceIdT

TEST_DEVICE_ID = "32:153289"
TEST_PARAM_ID = "3F"
TEST_PARAM_VALUE = 50


def test_routing_context_string_formatting() -> None:
    """Test that RoutingContext handles legacy string casting safely."""
    assert RoutingContext(True).as_string == "True"
    assert RoutingContext(False).as_string == "False"
    assert RoutingContext("00").as_string == "00"
    assert RoutingContext("FA").as_string == "FA"
    assert RoutingContext(None).as_string == "None"


def test_state_header_legacy_formatting() -> None:
    """Test that StateHeader perfectly replicates the legacy _hdr format."""
    hdr = StateHeader.create(
        code="3220",
        verb="RP",
        source_id="01:123456",
        context_val="00",
    )
    assert hdr.legacy_hdr == "3220|RP|01:123456|00"

    base_hdr = StateHeader.create(
        code="10A0",
        verb=" I",
        source_id="04:654321",
        context_val=True,
    )
    assert base_hdr.legacy_hdr == "10A0| I|04:654321|True"


def test_state_header_hashing() -> None:
    """Test that StateHeader can be used as an O(1) dictionary key."""
    hdr1 = StateHeader.create("000C", "RP", "01:111111", "01")
    hdr2 = StateHeader.create("000C", "RP", "01:111111", "01")
    hdr3 = StateHeader.create("000C", "RP", "01:111111", "02")

    cache = {hdr1: "payload_data"}

    assert hdr2 in cache
    assert hdr3 not in cache


def test_state_header_topic_generation() -> None:
    """Test the Master Plan topic generation logic."""
    state_hdr = StateHeader.create("30C9", " I", "01:123456", "00")
    assert state_hdr.topic is EventTopic.INFORMATION

    disc_hdr = StateHeader.create("1FC9", " I", "01:123456", "00")
    assert disc_hdr.topic is EventTopic.TOPOLOGY_DISCOVERY

    req_hdr = StateHeader.create("3220", "RQ", "01:123456", "00")
    assert req_hdr.topic is EventTopic.REQUEST

    write_hdr = StateHeader.create("2309", " W", "01:123456", "00")
    assert write_hdr.topic is EventTopic.WRITE


# --- 2411 FAN Routing Tests (Fixes ramses_cc #851) ---


@pytest.fixture
def mock_gateway() -> Generator[MagicMock, None, None]:
    """Create a mock Gateway with a real device_registry mapping."""
    gateway = MagicMock(spec=Gateway)
    gateway.config = MagicMock()
    gateway.config.disable_discovery = False
    gateway.config.enable_eavesdrop = False
    gateway._loop = MagicMock()
    gateway._loop.call_soon = MagicMock()
    gateway._loop.call_later = MagicMock()
    gateway._loop.time = MagicMock(return_value=0.0)
    gateway._include = {}
    gateway.message_store = MessageStore(maintain=False)

    registry = MagicMock()
    registry.device_by_id = {}
    gateway.device_registry = registry

    yield gateway


def _make_fan(gateway: MagicMock) -> HvacVentilator:
    """Create a real HvacVentilator registered in the mock registry."""
    fan = HvacVentilator(gateway, Address(DeviceIdT(TEST_DEVICE_ID)))
    gateway.device_registry.device_by_id[TEST_DEVICE_ID] = fan
    return fan


def _make_2411_msg(verb: str = " I") -> MagicMock:
    """Create a mock 2411 message whose src/dst resolve to the FAN."""
    msg = MagicMock()
    msg.code = Code._2411
    msg.verb = verb
    msg.src = MagicMock()
    msg.src.id = TEST_DEVICE_ID
    msg.dst = MagicMock()
    msg.dst.id = TEST_DEVICE_ID
    msg.payload = {"parameter": TEST_PARAM_ID, "value": TEST_PARAM_VALUE}
    return msg


class TestDispatcher2411Routing:
    """Verify dispatcher._cqrs_ingestion_engine routes 2411 to the FAN."""

    @pytest.mark.asyncio
    async def test_2411_updates_fan_state_and_invokes_callback(
        self, mock_gateway: MagicMock
    ) -> None:
        """A 2411 `` I`` packet must set supports_2411 and fire the callback."""
        fan = _make_fan(mock_gateway)

        callback = MagicMock()
        fan.set_initialized_callback(callback)

        msg = _make_2411_msg(verb=" I")
        await dispatcher._cqrs_ingestion_engine(mock_gateway, msg)

        assert fan._supports_2411, "supports_2411 was not flipped"
        assert TEST_PARAM_ID in fan._params_2411
        assert fan._params_2411[TEST_PARAM_ID] == TEST_PARAM_VALUE
        callback.assert_called_once()
        assert fan._initialized_callback is None

        if fan._gateway.message_store:
            fan._gateway.message_store.stop()

    @pytest.mark.asyncio
    async def test_2411_rp_also_routed(self, mock_gateway: MagicMock) -> None:
        """A 2411 ``RP`` reply must also be routed."""
        fan = _make_fan(mock_gateway)
        msg = _make_2411_msg(verb="RP")
        await dispatcher._cqrs_ingestion_engine(mock_gateway, msg)

        assert fan._supports_2411

        if fan._gateway.message_store:
            fan._gateway.message_store.stop()

    @pytest.mark.asyncio
    async def test_2411_rq_not_routed(self, mock_gateway: MagicMock) -> None:
        """A 2411 ``RQ`` request carries no telemetry and must be skipped."""
        fan = _make_fan(mock_gateway)
        msg = _make_2411_msg(verb="RQ")
        await dispatcher._cqrs_ingestion_engine(mock_gateway, msg)

        assert not fan._supports_2411, "RQ must not flip supports_2411"
        assert fan._params_2411 == {}

        if fan._gateway.message_store:
            fan._gateway.message_store.stop()

    @pytest.mark.asyncio
    async def test_non_fan_target_not_affected(self, mock_gateway: MagicMock) -> None:
        """A non-FAN device in registry must not be touched by 2411 routing."""
        fan = _make_fan(mock_gateway)
        other = MagicMock()
        other._SLUG = DevType.CTL
        other.id = "01:000001"
        mock_gateway.device_registry.device_by_id["01:000001"] = other

        msg = _make_2411_msg(verb=" I")
        await dispatcher._cqrs_ingestion_engine(mock_gateway, msg)

        assert fan._supports_2411
        other._handle_2411_message.assert_not_called()

        if fan._gateway.message_store:
            fan._gateway.message_store.stop()


class TestStateProjector2411Routing:
    """Verify StateProjector._route_2411_to_fan mirrors the dispatcher path."""

    def test_state_projector_routes_2411(self, mock_gateway: MagicMock) -> None:
        """The ingestion StateProjector must also route 2411 to the FAN."""
        fan = _make_fan(mock_gateway)
        callback = MagicMock()
        fan.set_initialized_callback(callback)

        projector = StateProjector(mock_gateway, MagicMock())
        msg = _make_2411_msg(verb=" I")
        projector._route_2411_to_fan(msg)

        assert fan._supports_2411
        assert fan._params_2411.get(TEST_PARAM_ID) == TEST_PARAM_VALUE
        callback.assert_called_once()

        if fan._gateway.message_store:
            fan._gateway.message_store.stop()

    def test_state_projector_process_message_state_routes_2411(
        self, mock_gateway: MagicMock
    ) -> None:
        """process_message_state must trigger 2411 routing for a 2411 msg."""
        fan = _make_fan(mock_gateway)
        projector = StateProjector(mock_gateway, MagicMock())

        msg = _make_2411_msg(verb=" I")
        projector.process_message_state(msg)

        assert fan._supports_2411

        if fan._gateway.message_store:
            fan._gateway.message_store.stop()


@pytest.mark.asyncio
async def test_l7_routing_avoids_stranglers_knot() -> None:
    """Test that a mismatched topological binding does not crash routing."""
    gwy_mock = MagicMock()
    gwy_mock.config.enable_eavesdrop = False
    gwy_mock.config.reduce_processing = 0
    gwy_mock.async_send_cmd = AsyncMock()

    tcs = MagicMock()
    tcs.id = "01:145038"
    tcs._gateway = gwy_mock
    tcs.ctl = MagicMock()
    tcs.ctl.id = "01:145038"
    tcs.zone_by_idx = {}
    tcs._max_zones = 12

    zone_02 = Zone(tcs, "02")
    zone_02._SLUG = "RAD"
    tcs.zone_by_idx["02"] = zone_02

    zone_0a = Zone(tcs, "0A")
    zone_0a._SLUG = "RAD"
    tcs.zone_by_idx["0A"] = zone_0a

    msg = MagicMock()
    msg.code = Code._3150
    msg.verb = I_
    msg.payload = {"zone_idx": "02", "heat_demand": 0.44}
    msg._has_array = False
    msg.src = MagicMock()
    msg.src.id = "04:056053"
    msg.dst = MagicMock()
    msg.dst.id = "01:145038"

    mock_dev = MagicMock()
    mock_dev._SLUG = "TRV"
    mock_dev.tcs = tcs
    gwy_mock.device_by_id = {"04:056053": mock_dev}
    gwy_mock.system_by_id = {"01:145038": tcs}
    gwy_mock.device_registry = MagicMock()
    gwy_mock.device_registry.device_by_id = {"04:056053": mock_dev}

    await process_msg(gwy_mock, msg)

    demand = await zone_02.heat_demand()
    assert demand == 0.44
