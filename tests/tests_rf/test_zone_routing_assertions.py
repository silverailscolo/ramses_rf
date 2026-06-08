"""Test suite isolating the OSI decoupling legacy routing fault."""

import logging
from typing import cast
from unittest.mock import MagicMock

import pytest

from ramses_rf.const import Code
from ramses_rf.systems.tcs import MultiZone
from ramses_rf.systems.zones import Zone

_LOGGER = logging.getLogger(__name__)


class MockTrvActuator:
    """A minimal mock of the legacy device bubbling behaviour."""

    def __init__(self, device_id: str, parent_zone: Zone) -> None:
        """Initialise the mock TRV bound to a specific topological parent."""
        self.id = device_id
        self.type = "04"
        self._parent = parent_zone

    def _handle_msg(self, msg: MagicMock) -> None:
        """Legacy topological bubbling to the parent zone."""
        _LOGGER.debug(
            "MockTrvActuator(%s): Bubbling msg up to parent Zone(%s)",
            self.id,
            self._parent.idx,
        )
        self._parent._handle_msg(msg)


class MockTcs:
    """A minimal mock of the new explicit L7 routing behaviour."""

    def __init__(self) -> None:
        """Initialise the mock TCS."""
        self.zone_by_idx: dict[str, Zone] = {}
        self.id = "01:145038"
        self.ctl = MagicMock()
        self.ctl.id = "01:145038"
        self._gwy = MagicMock()
        self._gwy.config.enable_eavesdrop = False
        self._max_zones = 12

    def _handle_msg(self, msg: MagicMock) -> None:
        """New explicit downward routing based on L7 payload."""
        _LOGGER.debug("MockTcs: Routing downward using L7 payload.")
        if isinstance(msg.payload, dict):
            if zone_idx := msg.payload.get("zone_idx"):
                if zone := self.zone_by_idx.get(zone_idx):
                    zone._handle_msg(msg)


def test_stranglers_knot_routing_fault(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test the collision when legacy bubbling relies on a mismatched schema."""
    caplog.set_level(logging.DEBUG)

    # Arrange: Set up the topology with a TRV bound to the WRONG zone.
    tcs_mock = MockTcs()
    # Cast the mock to satisfy Mypy's strict _MultiZoneT bound variable requirement
    tcs = cast(MultiZone, tcs_mock)

    zone_02 = Zone(tcs, "02")
    zone_02._SLUG = "RAD"
    tcs_mock.zone_by_idx["02"] = zone_02

    zone_0a = Zone(tcs, "0A")
    zone_0a._SLUG = "RAD"
    tcs_mock.zone_by_idx["0A"] = zone_0a

    # TRV incorrectly bound to Zone 0A
    trv_0a = MockTrvActuator("04:056053", zone_0a)

    msg = MagicMock()
    msg.src = trv_0a
    msg.dst = tcs_mock.ctl
    msg.code = Code._3150
    msg.payload = {"zone_idx": "02", "heat_demand": 0.44}
    msg._has_array = False

    # Act & Assert: Trigger the legacy upward bubbling
    _LOGGER.debug("--- START: Legacy Bubbling Path (Mismatched Schema) ---")

    with pytest.raises(AssertionError) as exc_info:
        trv_0a._handle_msg(msg)

    # Assert: Verify the exact crash from zones.py:702 is triggered
    assert "msg inappropriately routed to" in str(exc_info.value)
    assert "0A" in str(exc_info.value)

    _LOGGER.debug("--- END: Assertion Triggered Successfully ---")


def test_legacy_bubbling_with_correct_schema(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that legacy bubbling succeeds if the topological schema is correct."""
    caplog.set_level(logging.DEBUG)

    # Arrange: Set up the topology with a TRV bound to the CORRECT zone.
    tcs_mock = MockTcs()
    # Cast the mock to satisfy Mypy's strict _MultiZoneT bound variable requirement
    tcs = cast(MultiZone, tcs_mock)

    zone_02 = Zone(tcs, "02")
    zone_02._SLUG = "RAD"
    tcs_mock.zone_by_idx["02"] = zone_02

    # TRV correctly bound to Zone 02
    trv_02 = MockTrvActuator("04:056053", zone_02)

    msg = MagicMock()
    msg.src = trv_02
    msg.dst = tcs_mock.ctl
    msg.code = Code._3150
    msg.payload = {"zone_idx": "02", "heat_demand": 0.44}
    msg._has_array = False

    # Act & Assert: Trigger the legacy upward bubbling
    _LOGGER.debug("--- START: Legacy Bubbling Path (Correct Schema) ---")

    try:
        trv_02._handle_msg(msg)
    except AssertionError as err:
        pytest.fail(f"AssertionError raised unexpectedly: {err}")

    # Assert: The zone successfully processes the message without crashing
    assert zone_02.demand_state is not None  # Ensure the object is healthy

    _LOGGER.debug("--- END: Legacy Bubbling Succeeded ---")
