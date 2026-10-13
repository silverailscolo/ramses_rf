"""Zone temperature hydration when the zone sensor is a controller-class device.

A zone may declare a controller-class device (e.g. ``01:150003``, classed
CTL) as its sensor in the schema.  ``Zone._update_schema`` refuses to bind
CTL/UFC/HGI devices as zone sensors, so ``zone.sensor`` stays ``None`` and
no ``_parent`` link is created — the sensor-sourced 30C9 cannot be routed
to the zone via the parent lookup.

``_resolve_logical_targets`` falls back to the sensor id declared in the
configured schema, so the zone's ``current_temperature`` is hydrated even
when the declared sensor is a CTL-classed device.

See: https://github.com/wimpie70/ramses_extras/issues/241 (item 2.6)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .helpers import TEST_DIR, load_test_gwy

SENSOR_DIR = Path(f"{TEST_DIR}/systems/_heat_ctl_sensor_30c9")
SENSOR_TRV_DIR = Path(f"{TEST_DIR}/systems/_heat_ctl_sensor_30c9_trv")
THM_SENSOR_TRV_IDX_DIR = Path(
    f"{TEST_DIR}/systems/_heat_thm_sensor_30c9_trv_idx"
)


@pytest.mark.asyncio
async def test_zone_temperature_hydrated_from_ctl_sensor_30c9() -> None:
    """The Zone.temperature must reflect a 30C9 packet from a CTL-classed
    device that is declared as the zone's sensor in the schema, even
    though the sensor binding was refused.
    """
    gwy = await load_test_gwy(SENSOR_DIR)
    try:
        tcs = gwy.tcs
        assert tcs is not None, "no TCS loaded"
        zone = tcs.zone_by_index.get("03")
        assert zone is not None, "no zone 03 loaded"
        # CTL-classed devices are refused as zone sensors
        assert zone.sensor is None, "expected refused sensor binding"

        temp = await zone.temperature()
        assert temp == 22.0, (
            f"Zone temperature not hydrated from CTL-classed sensor 30C9: "
            f"{temp!r}"
        )
    finally:
        await gwy.stop()


@pytest.mark.asyncio
async def test_actuator_30c9_does_not_overwrite_declared_sensor_temp() -> None:
    """A sole actuator's 30C9 must not overwrite the zone temperature when
    a sensor is declared in the schema, even if that sensor is a
    controller-class device whose binding was refused.

    Zone 03 declares ``01:150003`` (classed CTL) as sensor and
    ``04:150003`` (TRV) as its only actuator.  The zone sensor stays
    unbound (``zone.sensor is None``), so without the declared-sensor
    check the TRV qualifies for the sole-actuator fallback and its 30C9
    overwrites the zone temperature.

    See: https://github.com/ramses-rf/ramses_cc/issues/1328
    """
    gwy = await load_test_gwy(SENSOR_TRV_DIR)
    try:
        tcs = gwy.tcs
        assert tcs is not None, "no TCS loaded"
        zone = tcs.zone_by_index.get("03")
        assert zone is not None, "no zone 03 loaded"
        assert zone.sensor is None, "expected refused sensor binding"

        temp = await zone.temperature()
        assert temp == 22.0, (
            f"Zone temperature overwritten by sole actuator 30C9 despite "
            f"declared sensor: {temp!r}"
        )
    finally:
        await gwy.stop()


@pytest.mark.asyncio
async def test_indexed_actuator_30c9_does_not_overwrite_thm_sensor_temp() -> (
    None
):
    """An addressed TRV->CTL 30C9 carries zone_index and routes to the zone
    via the controller-index path, bypassing the sensor-sourced guards —
    it must not overwrite the temperature when the zone designates a
    THM-class sensor.

    Zone 03 binds ``12:150003`` (THM) as sensor — the binding succeeds, so
    ``zone.sensor`` is set — and ``04:150003`` (TRV) as actuator.  The TRV's
    addressed 30C9 (``I 04:150003 01:150000 30C9 003 0307B0``) is injected
    with ``zone_index`` by ``_build_index_dict`` and reaches the zone
    through the controller-source/destination routing, so the
    sole-actuator check never sees it.

    See: https://github.com/ramses-rf/ramses_cc/issues/1334
    """
    gwy = await load_test_gwy(THM_SENSOR_TRV_IDX_DIR)
    try:
        tcs = gwy.tcs
        assert tcs is not None, "no TCS loaded"
        zone = tcs.zone_by_index.get("03")
        assert zone is not None, "no zone 03 loaded"
        assert zone.sensor is not None, "expected bound THM sensor"
        assert zone.sensor.id == "12:150003"

        temp = await zone.temperature()
        assert temp == 22.0, (
            f"Zone temperature overwritten by indexed actuator 30C9 "
            f"despite bound THM sensor: {temp!r}"
        )
    finally:
        await gwy.stop()
