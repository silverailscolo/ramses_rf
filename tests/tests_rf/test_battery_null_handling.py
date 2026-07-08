from unittest.mock import MagicMock

import pytest

# Assuming the standard module path for the ramses_rf package
from ramses_rf.devices.dev_base import BatteryState
from ramses_rf.models import PowerState


@pytest.mark.asyncio
async def test_battery_status_omits_key_when_level_is_none() -> None:
    # Arrange
    gwy = MagicMock()
    gwy.config.known_list = {}

    addr = MagicMock()
    addr.id = "04:123456"
    addr.type = "04"

    device = BatteryState(gwy, addr)
    device.power_state = PowerState(battery_level=None)

    # Act
    status = await device.status()

    # Assert
    # Ensure we do not exhibit the bug behaviour where null crashes templates
    assert BatteryState.BATTERY_STATE not in status, (
        "The battery_state key must be completely omitted if the level is unknown"
    )


@pytest.mark.asyncio
async def test_battery_status_includes_key_when_level_is_known() -> None:
    # Arrange
    gwy = MagicMock()
    gwy.config.known_list = {}

    addr = MagicMock()
    addr.id = "04:123456"
    addr.type = "04"

    device = BatteryState(gwy, addr)
    device.power_state = PowerState(battery_low=False, battery_level=0.85)

    # Act
    status = await device.status()

    # Assert
    assert BatteryState.BATTERY_STATE in status, (
        "The battery_level key must be included if the level is known"
    )
    assert status[BatteryState.BATTERY_STATE]["battery_level"] == 0.85
