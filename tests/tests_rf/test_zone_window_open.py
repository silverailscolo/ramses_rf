"""Tests for Zone-level window_open state aggregation."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ramses_rf.devices import TrvActuator
from ramses_rf.systems.zones import Zone


def _create_mock_zone() -> Zone:
    """Create an isolated Zone instance for testing."""
    mock_tcs = MagicMock()
    mock_tcs.id = "01:123456"
    mock_tcs._gwy = MagicMock()
    mock_tcs.zone_by_idx = {}
    mock_tcs._max_zones = 12
    mock_tcs.ctl = MagicMock()

    return Zone(mock_tcs, "00")


def _create_mock_trv(state: bool | None) -> MagicMock:
    """Create a mock TRV actuator returning a specific window state."""
    trv = MagicMock(spec=TrvActuator)
    trv.window_open = AsyncMock(return_value=state)
    return trv


@pytest.mark.asyncio
async def test_window_open_no_actuators() -> None:
    """Test zone window state when no actuators are present."""

    # Arrange
    zone = _create_mock_zone()
    zone.actuators = []

    # Act
    result = await zone.window_open()

    # Assert
    assert result is None


@pytest.mark.asyncio
async def test_window_open_all_closed() -> None:
    """Test zone window state when all TRVs report closed."""

    # Arrange
    zone = _create_mock_zone()
    zone.actuators = [
        _create_mock_trv(False),
        _create_mock_trv(False),
    ]

    # Act
    result = await zone.window_open()

    # Assert
    assert result is False


@pytest.mark.asyncio
async def test_window_open_one_open() -> None:
    """Test zone window state when at least one TRV reports open."""

    # Arrange
    zone = _create_mock_zone()
    zone.actuators = [
        _create_mock_trv(False),
        _create_mock_trv(True),
    ]

    # Act
    result = await zone.window_open()

    # Assert
    assert result is True


@pytest.mark.asyncio
async def test_window_open_mixed_unknown_and_closed() -> None:
    """Test zone window state with unknown and closed TRVs."""

    # Arrange
    zone = _create_mock_zone()
    zone.actuators = [
        _create_mock_trv(None),
        _create_mock_trv(False),
    ]

    # Act
    result = await zone.window_open()

    # Assert
    assert result is None


@pytest.mark.asyncio
async def test_window_open_mixed_unknown_and_open() -> None:
    """Test zone window state with unknown and open TRVs."""

    # Arrange
    zone = _create_mock_zone()
    zone.actuators = [
        _create_mock_trv(None),
        _create_mock_trv(True),
    ]

    # Act
    result = await zone.window_open()

    # Assert
    assert result is True
