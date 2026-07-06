"""TDD Test for Issue #649: Polling task never sending."""

from unittest.mock import MagicMock, patch

import pytest

from ramses_rf.address import Address
from ramses_rf.devices.dev_registry import DeviceRegistry
from ramses_rf.devices.hvac_ventilators import FilterChange
from ramses_rf.discovery import DiscoveryService
from ramses_rf.models import DeviceTraits


@pytest.mark.asyncio
async def test_issue_649_discovery_cmds_populated() -> None:
    # Arrange
    mock_gwy = MagicMock()
    mock_gwy.config = MagicMock()
    mock_gwy.config.disable_discovery = False
    mock_gwy.config.known_list = {}  # <-- FIX: Use a real dict, not a MagicMock
    mock_gwy.config.hgi_id = "18:000000"

    def mock_factory(
        addr: Address, msg: MagicMock, traits: DeviceTraits
    ) -> FilterChange:
        dev = FilterChange(mock_gwy, addr, traits=traits)
        dev.discovery = DiscoveryService(dev, mock_gwy)
        return dev

    # Suppress the auto-starting poller (which would crash on the mock
    # gateway and leave lingering tasks).
    with patch.object(DiscoveryService, "start_poller", lambda self: None):
        registry = DeviceRegistry(
            device_filter=MagicMock(),
            config=mock_gwy.config,
            device_factory_cb=mock_factory,
        )

        # Act
        dev = registry.get_device("32:111111")

        # Assert
        assert hasattr(dev, "discovery"), "Device missing discovery service"
        assert dev.discovery.cmds, "Issue #649: Discovery cmds dictionary is empty"

        scheduled_codes = [task["command"].code for task in dev.discovery.cmds.values()]
        assert "10D0" in scheduled_codes, "10D0 filter poll not scheduled"
