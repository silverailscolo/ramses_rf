"""Zone temperature when a dedicated sensor is only known via 000C.

A zone may have a dedicated broadcast-only sensor (THM/RND) that never
sends zone-indexed traffic, so it is never attributed to the zone and
lands in ``orphans_heat``.  The zone stays sensorless, so the
sole-actuator fallback routes the TRV's own broadcast 30C9 to
``zone.temperature`` — the observed symptom is the zone temperature
jumping to the TRV's reading until the next controller sync restores it.

The controller's 000C binding table is the authoritative fix: its
role-04 (zone_sensor) item for the zone names the real sensor.  Binding
it reparents the device to the zone, after which the TRV broadcast is no
longer routed to the zone.

See: https://github.com/ramses-rf/ramses_cc/issues/1334
     https://github.com/ramses-rf/ramses_cc/issues/1344
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .helpers import TEST_DIR, load_test_gwy

SENSOR_BOUND_DIR = Path(f"{TEST_DIR}/systems/_heat_000c_zone_sensor")
SENSOR_ABSENT_DIR = Path(f"{TEST_DIR}/systems/_heat_000c_zone_sensor_absent")


@pytest.mark.asyncio
async def test_000c_zone_sensor_binding_blocks_actuator_fallback() -> None:
    """An RP 000C role-04 reply binds the orphan THM as zone sensor.

    After the binding lands, the sole actuator's broadcast 30C9 no longer
    overwrites the zone temperature — the THM's broadcast hydrates the
    zone instead.
    """
    gwy = await load_test_gwy(SENSOR_BOUND_DIR)
    try:
        tcs = gwy.tcs
        assert tcs is not None, "no TCS loaded"
        zone = tcs.zone_by_index.get("01")
        assert zone is not None, "no zone 01 loaded"

        # The 000C binding-table reply bound the orphan THM to the zone
        assert zone.sensor is not None, "zone sensor not bound via 000C"
        assert zone.sensor.id == "34:218857", zone.sensor
        assert "34:218857" not in (await gwy.schema()).get("orphans_heat", [])

        # The TRV's second broadcast (18.7) must not overwrite the zone
        # temperature — the sensor's broadcast (19.8) wins.
        temp = await zone.temperature()
        assert temp == 19.8, (
            f"Zone temperature overwritten by sole actuator 30C9 despite "
            f"000C-bound sensor: {temp!r}"
        )
    finally:
        await gwy.stop()


@pytest.mark.asyncio
async def test_sensorless_zone_sole_actuator_fallback_unchanged() -> None:
    """Control: without the 000C binding the sole-actuator fallback wins.

    The orphan THM broadcasts its temperature, but the sensorless zone
    keeps taking its temperature from the sole actuator (issue 976
    behaviour) — the fallback must not be globally disabled.
    """
    gwy = await load_test_gwy(SENSOR_ABSENT_DIR)
    try:
        tcs = gwy.tcs
        assert tcs is not None, "no TCS loaded"
        zone = tcs.zone_by_index.get("01")
        assert zone is not None, "no zone 01 loaded"
        assert zone.sensor is None, "zone unexpectedly has a sensor"

        temp = await zone.temperature()
        assert temp == 18.7, (
            f"Sensorless zone did not use sole actuator temperature: {temp!r}"
        )
    finally:
        await gwy.stop()
