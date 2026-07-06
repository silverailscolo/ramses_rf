"""Tests for the CQRS-compliant system_mode getter.

The getter is a pure read — it returns the cached Hot State RAM value
without dispatching any commands.  Hydration is handled by the discovery
queue configured in ``_setup_discovery_cmds``.
"""

from __future__ import annotations

import dataclasses
from unittest.mock import AsyncMock, MagicMock

import pytest

from ramses_rf.const import SZ_SYSTEM_MODE
from ramses_rf.devices import Controller
from ramses_rf.systems.tcs import Evohome


@pytest.mark.asyncio
async def test_system_mode_returns_none_when_cqrs_empty() -> None:
    """Test that system_mode returns None when CQRS state is empty.

    The getter must NOT dispatch any commands — hydration is the
    responsibility of the discovery queue, not the getter.

    Arrange: An Evohome controller with an empty hot CQRS state.
    Act: Retrieve the system mode via the async getter.
    Assert: Returns None and no network RQ is dispatched.
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
    result = await tcs.system_mode()

    # Assert
    assert result is None
    # No command should be dispatched by a getter (CQRS: reads have no side-effects)
    mock_gwy.async_send_cmd.assert_not_called()


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
