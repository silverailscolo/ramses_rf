"""Reproduction and regression test for ramses_cc issue 976.

Evohome zone current_temperature fluctuating when zone contains multiple
TRVs or TRV(s) with an external thermostat.

Non-authoritative child devices (e.g. TRVs when a separate sensor is bound)
broadcast 30C9 for their own internal measurements. These packets must NOT
clobber the parent zone's temp_state.temperature.

See: https://github.com/ramses-rf/ramses_cc/issues/976
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ramses_rf.devices import TrvActuator

from .helpers import TEST_DIR, load_test_gwy

MULTI_TRV_DIR = Path(f"{TEST_DIR}/systems/_heat_multi_trv_30c9")
DESIGNATED_TRV_DIR = Path(f"{TEST_DIR}/systems/_heat_multi_trv_designated_trv")
SINGLE_TRV_DIR = Path(f"{TEST_DIR}/systems/_heat_single_trv_no_sensor")
MULTI_TRV_NO_SENSOR_DIR = Path(f"{TEST_DIR}/systems/_heat_multi_trv_no_sensor")


@pytest.mark.asyncio
async def test_zone_temperature_not_clobbered_by_multi_trvs() -> None:
    """The Zone.temperature must reflect the designated sensor (22:017762),
    and must not be overwritten by subsequent 30C9 packets from TRV
    actuators (04:005646, 04:005647).
    """
    # Arrange & Act
    gwy = await load_test_gwy(MULTI_TRV_DIR)
    try:
        tcs = gwy.tcs
        assert tcs is not None, "no TCS loaded"
        zone = tcs.zone_by_index.get("00")
        assert zone is not None, "no zone 00 loaded"
        assert zone.sensor is not None, "zone has no sensor"
        assert zone.sensor.id == "22:017762"

        # Assert: Zone temperature remains that of the sensor (27.1),
        # not the TRV temperatures (19.5 or 22.5)
        temp = await zone.temperature()
        assert temp == 27.1, (
            f"Zone temperature was clobbered by non-sensor TRVs: {temp!r}"
        )

        # Assert: TRV devices still maintain their own temperatures
        trv1 = gwy.device_registry.get_device("04:005646")
        assert isinstance(trv1, TrvActuator)
        assert await trv1.temperature() == 19.5

        trv2 = gwy.device_registry.get_device("04:005647")
        assert isinstance(trv2, TrvActuator)
        assert await trv2.temperature() == 22.5
    finally:
        await gwy.stop()


@pytest.mark.asyncio
async def test_zone_temperature_from_designated_trv_sensor() -> None:
    """When a TRV (04:005646) is designated as the zone sensor, only its
    30C9 packets must hydrate Zone.temperature. Subsequent 30C9 from another
    TRV (04:005647) must not overwrite it.
    """
    # Arrange & Act
    gwy = await load_test_gwy(DESIGNATED_TRV_DIR)
    try:
        tcs = gwy.tcs
        assert tcs is not None, "no TCS loaded"
        zone = tcs.zone_by_index.get("00")
        assert zone is not None, "no zone 00 loaded"
        assert zone.sensor is not None, "zone has no sensor"
        assert zone.sensor.id == "04:005646"

        # Assert: Zone temperature is from designated TRV (27.1),
        # not the second TRV (19.5)
        temp = await zone.temperature()
        assert temp == 27.1, (
            f"Zone temperature was clobbered by non-sensor TRV: {temp!r}"
        )
    finally:
        await gwy.stop()


@pytest.mark.asyncio
async def test_zone_temperature_from_sole_actuator() -> None:
    """When a zone has a single TRV (04:005646) and no designated sensor,
    its 30C9 packets must hydrate Zone.temperature.
    """
    # Arrange & Act
    gwy = await load_test_gwy(SINGLE_TRV_DIR)
    try:
        tcs = gwy.tcs
        assert tcs is not None, "no TCS loaded"
        zone = tcs.zone_by_index.get("00")
        assert zone is not None, "no zone 00 loaded"

        # Assert: Zone temperature is hydrated from the sole TRV (20.5)
        temp = await zone.temperature()
        assert temp == 20.5, (
            f"Zone temperature not hydrated from sole TRV: {temp!r}"
        )
    finally:
        await gwy.stop()


@pytest.mark.asyncio
async def test_zone_temperature_controller_broadcast_with_multi_trvs() -> None:
    """When a zone has multiple TRVs and no designated sensor, non-sensor
    TRVs must not set zone temperature, but the controller's 30C9 broadcast
    (with zone_index) must hydrate Zone.temperature.
    """
    # Arrange & Act
    gwy = await load_test_gwy(MULTI_TRV_NO_SENSOR_DIR)
    try:
        tcs = gwy.tcs
        assert tcs is not None, "no TCS loaded"
        zone = tcs.zone_by_index.get("00")
        assert zone is not None, "no zone 00 loaded"

        # Assert: Zone temperature is from the controller broadcast (21.0),
        # not from the TRVs (19.5 or 22.5)
        temp = await zone.temperature()
        assert temp == 21.0, (
            f"Zone temperature not hydrated from controller broadcast: {temp!r}"
        )
    finally:
        await gwy.stop()
