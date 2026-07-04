"""Tests for the CQRS-compliant self-hydrating system_mode getter."""

from __future__ import annotations

import dataclasses
from unittest.mock import AsyncMock, MagicMock

import pytest

from ramses_rf.const import SZ_SYSTEM_MODE
from ramses_rf.devices import Controller
from ramses_rf.systems.tcs import Evohome
from ramses_tx.command import Command


@pytest.mark.asyncio
async def test_system_mode_triggers_network_rq_when_cqrs_empty() -> None:
    """Test that system_mode triggers a physical network RQ if CQRS state is empty.

    Arrange: An Evohome controller with an empty hot CQRS state.
    Act: Retrieve the system mode via the async getter.
    Assert: An explicit network RQ (2E04) is dispatched.
    """

    # Arrange
    mock_gwy = MagicMock()
    mock_gwy.config.enable_eavesdrop = False
    mock_gwy.device_registry.system_by_id = {}
    mock_gwy.async_send_cmd = AsyncMock()

    # Pass spec=Controller to satisfy the strict isinstance() guard in tcs.py
    mock_ctl = MagicMock(spec=Controller)
    mock_ctl.id = "01:123456"
    mock_ctl._gwy = mock_gwy

    tcs = Evohome(mock_ctl)

    # Simulate an empty CQRS state (typical boot scenario before telemetry arrives)
    tcs.system_state = dataclasses.replace(
        tcs.system_state, system_mode=None, until=None
    )

    # Act
    await tcs.system_mode()

    # Assert
    # Verify that an active network request was dispatched to hydrate the state
    mock_gwy.async_send_cmd.assert_called_once()

    # Extract the command passed to async_send_cmd
    cmd: Command = mock_gwy.async_send_cmd.call_args[0][0]

    assert cmd.verb == "RQ"
    assert cmd.code == "2E04"
    assert cmd.dst.id == mock_ctl.id


@pytest.mark.asyncio
async def test_system_mode_uses_hot_cqrs_state_when_available() -> None:
    """Test that system_mode prefers the hot CQRS state without network I/O.

    Arrange: An Evohome controller with a populated hot CQRS state.
    Act: Retrieve the system mode via the async getter.
    Assert: Returns the state instantly without dispatching an RQ.
    """

    # Arrange
    mock_gwy = MagicMock()
    mock_gwy.config.enable_eavesdrop = False
    mock_gwy.device_registry.system_by_id = {}
    mock_gwy.async_send_cmd = AsyncMock()

    # Pass spec=Controller to satisfy the strict isinstance() guard in tcs.py
    mock_ctl = MagicMock(spec=Controller)
    mock_ctl.id = "01:123456"
    mock_ctl._gwy = mock_gwy

    tcs = Evohome(mock_ctl)

    # Populate the hot CQRS state (simulating normal operation post-boot)
    tcs.system_state = dataclasses.replace(
        tcs.system_state,
        system_mode="02",  # AUTO
        until="2024-01-01T12:00:00",
    )

    # Act
    result = await tcs.system_mode()

    # Assert
    assert result is not None
    assert result[SZ_SYSTEM_MODE] == "02"
    assert result["until"] == "2024-01-01T12:00:00"

    # Verify we did NOT hit the network
    mock_gwy.async_send_cmd.assert_not_called()
