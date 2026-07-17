"""Test suite validating explicit L7 payload routing in the new architecture."""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from ramses_rf.const import Code
from ramses_rf.systems.zones import Zone

_LOGGER = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_l7_routing_avoids_stranglers_knot() -> None:
    """Test that a mismatched topological binding does not crash routing.

    In the legacy architecture, an orphan TRV bound to the wrong zone would bubble
    a 3150 packet up to the wrong zone parent, causing an AssertionError crash.
    In the new CQRS architecture, state updates are pulled from the MessageStore
    by querying the L7 `zone_idx` explicitly, avoiding topological bubbling.
    """
    # Arrange: Set up a mocked TCS with two zones
    gwy_mock = MagicMock()
    gwy_mock.config.enable_eavesdrop = False
    gwy_mock.config.reduce_processing = 0
    gwy_mock.async_send_cmd = AsyncMock()

    tcs = MagicMock()
    tcs.id = "01:145038"
    tcs._gwy = gwy_mock
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

    # Create a 3150 message intended for Zone 02, but coming from a TRV
    # that is (hypothetically) improperly bound in the real world to Zone 0A.
    from ramses_rf.const import I_

    msg = MagicMock()
    msg.code = Code._3150
    msg.verb = I_
    msg.payload = {"zone_idx": "02", "heat_demand": 0.44}
    msg._has_array = False
    msg.src = MagicMock()
    msg.src.id = "04:056053"
    msg.dst = MagicMock()
    msg.dst.id = "01:145038"

    # Mock the device registry to return a TRV
    mock_dev = MagicMock()
    mock_dev._SLUG = "TRV"
    mock_dev.tcs = tcs
    gwy_mock.device_by_id = {"04:056053": mock_dev}
    gwy_mock.system_by_id = {"01:145038": tcs}
    gwy_mock.device_registry = MagicMock()
    gwy_mock.device_registry.device_by_id = {"04:056053": mock_dev}

    # Act: Process the message through the dispatcher pipeline
    from ramses_rf.dispatcher import process_msg

    await process_msg(gwy_mock, msg)

    # Assert: Zone 02 successfully processes the payload and returns the correct demand
    demand = await zone_02.heat_demand()
    assert demand == 0.44
