#!/usr/bin/env python3
"""Test the boot-time discovery polling for dormant DHW entities."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from ramses_rf.const import Code
from ramses_rf.devices import Controller
from ramses_rf.systems.tcs import StoredHw


@pytest.fixture
def mock_gwy() -> MagicMock:
    """Provide a mocked Gateway instance."""
    gwy = MagicMock()
    gwy.config.disable_discovery = False
    gwy.async_send_cmd = AsyncMock(return_value=None)
    gwy.device_registry.system_by_id = {}
    return gwy


@pytest.fixture
def mock_ctl(mock_gwy: MagicMock) -> MagicMock:
    """Provide a mocked Controller instance."""
    ctl = MagicMock(spec=Controller)
    ctl.id = "01:123456"
    ctl._gwy = mock_gwy
    return ctl


def test_stored_hw_discovery_adds_dhw_state_requests(
    mock_ctl: MagicMock,
) -> None:
    """Ensure DHW state codes are explicitly polled during system boot."""

    # Arrange
    tcs = StoredHw(mock_ctl)

    # Act
    tcs._setup_discovery_cmds()

    # Assert
    cmds: list[Any] = [task["command"] for task in tcs.discovery.cmds.values()]
    scheduled_codes: list[Code] = [cmd.code for cmd in cmds]

    assert Code._10A0 in scheduled_codes, "DHW Params (10A0) not polled"
    assert Code._1260 in scheduled_codes, "DHW Temp (1260) not polled"
    assert Code._1F41 in scheduled_codes, "DHW Mode (1F41) not polled"
