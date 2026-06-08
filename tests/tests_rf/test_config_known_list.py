"""Tests for the known_list data pipeline and configuration boundary.

These tests verify that the nested L7 trait dictionaries provided by
clients (like ramses_cc) are successfully retained at the Application
layer, while only flat lists of MAC addresses are passed down to the
L3 Transport layer (ramses_tx).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import pytest

from ramses_rf.config import GatewayConfig
from ramses_rf.gateway import Gateway
from ramses_rf.typing import DeviceIdT


@pytest.mark.asyncio
async def test_known_list_data_pipeline_boundary() -> None:
    """Verify the known_list pipeline strips L7 traits before L3."""

    # ARRANGE
    # Simulate the raw nested dictionary passed in from ramses_cc
    raw_known_list: dict[str, dict[str, Any]] = {
        "18:123456": {"class": "HGI", "alias": "MyGateway"},
        "01:111111": {"class": "CTL"},
        "04:222222": {"faked": True, "alias": "FakedSensor"},
    }

    # ACT
    # Instantiate the L7 configuration and the Gateway facade
    config = GatewayConfig(
        known_list=raw_known_list,
    )

    # We use a dummy port and pass the loop to prevent thread leaks
    loop = asyncio.get_running_loop()
    gateway = Gateway(port_name="/dev/null", config=config, loop=loop)

    # ASSERT - Layer 7 Application Domain
    # The L7 config must retain the rich nested dictionaries
    assert isinstance(gateway.config.known_list, dict)
    assert gateway.config.known_list["18:123456"]["alias"] == "MyGateway"

    # The L7 config must successfully deduce the HGI ID from the traits
    assert gateway.config.hgi_id == "18:123456"

    # ASSERT - The L7 to L3 Translation Boundary
    # mac_filter_list must strip all traits and yield strings
    assert isinstance(gateway.config.mac_filter_list, list)
    assert len(gateway.config.mac_filter_list) == 3
    assert "01:111111" in gateway.config.mac_filter_list

    # ASSERT - Layer 3 Transport Domain
    # The L3 EngineConfig must receive ONLY the flat list of strings
    engine_config = gateway._gwy_config.engine

    assert isinstance(engine_config.known_list, list)
    assert "04:222222" in engine_config.known_list

    # Ensure no dictionaries leaked into the L3 transport array
    for mac in engine_config.known_list:
        assert isinstance(mac, str)

    # ASSERT - Device Registry Validation
    # The decoupled registry must natively provide the structured traits
    registry_known_list = await gateway.device_registry.known_list()
    assert isinstance(registry_known_list, dict)

    # Strictly index using the Domain Type
    dev_id = DeviceIdT("04:222222")
    assert registry_known_list[dev_id]["faked"] is True

    # CLEANUP
    # Prevent async loop warnings during test teardown
    with contextlib.suppress(asyncio.CancelledError):
        await gateway.stop()


@pytest.mark.asyncio
async def test_implicit_hgi_discovery_fallback() -> None:
    """Verify GatewayConfig can deduce an HGI without explicit traits."""

    # ARRANGE
    # A known_list where the HGI has no explicit {"class": "HGI"} trait
    raw_known_list: dict[str, dict[str, Any]] = {
        "18:006402": {},
        "01:145038": {"class": "CTL"},
    }

    # ACT
    config = GatewayConfig(
        known_list=raw_known_list,
    )

    # ASSERT
    # The config should fallback to detecting the '18:' MAC prefix
    assert config.hgi_id == "18:006402"
