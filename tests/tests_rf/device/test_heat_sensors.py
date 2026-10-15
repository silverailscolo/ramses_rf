"""Regression tests for faked heating sensor temperature announcements."""

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from ramses_rf.commands.builders import build_dto
from ramses_rf.commands.core import Command
from ramses_rf.devices import Controller, Thermostat
from ramses_rf.enums import Action, ZoneRole
from ramses_rf.systems import Evohome
from ramses_rf.systems.zones import (
    EleZone,
    MixZone,
    RadZone,
    UfhZone,
    ValZone,
    Zone,
)
from ramses_tx import Address
from ramses_tx.const import I_, Code


@pytest.fixture
def gateway() -> MagicMock:
    """Return a gateway with an isolated outbound dispatcher."""
    gateway = MagicMock()
    gateway.config.max_zones = 12
    gateway.config.known_list = {}
    gateway.config.block_list = {}
    gateway.dispatcher.send = AsyncMock(return_value=None)
    return gateway


@pytest.mark.parametrize(
    "zone_class", [RadZone, UfhZone, EleZone, MixZone, ValZone]
)
@pytest.mark.parametrize("zone_index", ["00", "05"])
@pytest.mark.parametrize(
    ("temperature", "expected_payload"),
    [(20.51, "000803"), (-5.25, "00FDF3"), (None, "007FFF")],
)
async def test_controller_bound_temperature_uses_sensor_index(
    gateway: MagicMock,
    zone_class: type[Zone],
    zone_index: str,
    temperature: float | None,
    expected_payload: str,
) -> None:
    # Arrange: a controller-bound sensor in a real Evohome zone.
    controller = Controller(gateway, Address("01:123456"))
    tcs = Evohome(controller)
    zone = zone_class(tcs, zone_index)
    sensor = Thermostat(gateway, Address("03:123456"))
    sensor._parent = zone
    sensor.ctl = controller

    # Act: exercise the device API, intent helper, and packet builder.
    with patch.object(
        Thermostat, "is_faked", new_callable=PropertyMock, return_value=True
    ):
        result = await sensor.set_temperature(temperature)
    gateway.dispatcher.send.assert_awaited_once()
    intent: Command = gateway.dispatcher.send.await_args.args[0]
    packet = build_dto(intent)

    # Assert: RF binding selects the zone, even for underfloor heating.
    assert result is None
    assert sensor.temp_state.temperature == temperature
    assert intent.action == Action.PUT_SENSOR_TEMP
    assert packet.verb == I_
    assert packet.code == Code._30C9
    assert packet.addr1 == sensor.id
    assert packet.addr2 == "--:------"
    assert packet.addr3 == sensor.id
    assert packet.payload == expected_payload


async def test_ufh_temperature_without_controller_retains_index(
    gateway: MagicMock,
) -> None:
    # Arrange: preserve the existing indexed UFH path outside Evohome.
    sensor = Thermostat(gateway, Address("03:123456"))
    sensor._parent = MagicMock(index="05", _SLUG=ZoneRole.UFH)
    assert sensor.ctl is None

    # Act
    with patch.object(
        Thermostat, "is_faked", new_callable=PropertyMock, return_value=True
    ):
        await sensor.set_temperature(20.51)
    intent: Command = gateway.dispatcher.send.await_args.args[0]

    # Assert
    assert build_dto(intent).payload == "050803"
