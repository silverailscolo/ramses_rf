"""Unit tests for RAMSES RF Polling API and PollingManager."""

from unittest.mock import MagicMock

import pytest

from ramses_rf.address import Address
from ramses_rf.const import Code
from ramses_rf.devices.dev_base import DeviceBase
from ramses_rf.pipeline.polling import (
    DEFAULT_POLLING_SCHEDULES,
    PollingManager,
)


def test_device_set_polling_interval_device_level() -> None:
    # Arrange
    gwy = MagicMock()
    dev_addr = Address("10:123456")
    dev = DeviceBase(gwy, dev_addr)

    # Act
    dev.set_polling_interval(600)

    # Assert
    assert dev.polling_interval is not None
    assert all(val == 600 for val in dev.polling_interval.values())


def test_device_set_command_polling_interval() -> None:
    # Arrange
    gwy = MagicMock()
    dev_addr = Address("10:123456")
    dev = DeviceBase(gwy, dev_addr)

    # Act
    dev.set_command_polling_interval(Code._3EF0, 900)

    # Assert
    assert dev.polling_interval == {Code._3EF0: 900}


def test_device_set_polling_interval_reset() -> None:
    # Arrange
    gwy = MagicMock()
    dev_addr = Address("10:123456")
    dev = DeviceBase(gwy, dev_addr)
    dev.set_polling_interval(600)

    # Act
    dev.set_polling_interval(None)

    # Assert
    assert dev.polling_interval is None


def test_device_battery_safeguard_raises_exception() -> None:
    # Arrange
    gwy = MagicMock()
    dev_addr = Address("04:123456")
    dev = DeviceBase(gwy, dev_addr)
    dev._is_battery = True

    # Act & Assert
    with pytest.raises(ValueError, match="cannot be set below 300s"):
        dev.set_polling_interval(120)

    with pytest.raises(ValueError, match="cannot be set below 300s"):
        dev.set_command_polling_interval(Code._10E0, 120)


def test_polling_manager_battery_device_returns_empty_schedule() -> None:
    # Arrange
    gwy = MagicMock()
    dev_addr = Address("04:123456")
    dev = DeviceBase(gwy, dev_addr)
    dev._is_battery = True

    # Act
    schedule = PollingManager.resolve_schedule_for_device(dev)

    # Assert
    assert schedule == {}


def test_polling_manager_mains_device_resolves_default_schedule() -> None:
    # Arrange
    gwy = MagicMock()
    dev_addr = Address("10:123456")
    dev = DeviceBase(gwy, dev_addr)
    dev._is_battery = False
    dev._SLUG = "OTB"

    # Act
    schedule = PollingManager.resolve_schedule_for_device(dev)

    # Assert
    assert schedule == DEFAULT_POLLING_SCHEDULES["OTB"]
