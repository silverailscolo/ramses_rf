"""Reproduction test for ramses_cc issue 927.

Zone climate entity not showing current_temperature after the CQRS
cutover when the zone sensor is a standalone thermostat (22: DT4R)
that broadcasts 30C9 independently.

In 0.55.3, the Zone.temperature property queried the msg_db directly
for 30C9 packets from either the controller (with matching zone_idx)
or the sensor.  In 0.59.3, the Zone reads from ``temp_state.temperature``
which is hydrated by the CQRS ingestion pipeline and state_projector.

Both pipelines routed controller-sourced 30C9 (with zone_idx) to zones,
but neither routed sensor-sourced 30C9 (no zone_idx) to the parent zone.
When the controller doesn't broadcast 30C9 for a zone (e.g. a DT4R-only
zone), the zone's ``current_temperature`` stayed None.

See: https://github.com/ramses-rf/ramses_cc/issues/927
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .helpers import TEST_DIR, load_test_gwy

SENSOR_DIR = Path(f"{TEST_DIR}/systems/_heat_sensor_30c9")


@pytest.mark.asyncio
async def test_zone_temperature_hydrated_from_sensor_30c9() -> None:
    """The Zone.temperature must reflect a 30C9 packet from the zone
    sensor (22:), even when the controller does not broadcast 30C9 for
    that zone.
    """
    gwy = await load_test_gwy(SENSOR_DIR)
    try:
        tcs = gwy.tcs
        assert tcs is not None, "no TCS loaded"
        zone = tcs.zone_by_idx.get("00")
        assert zone is not None, "no zone 00 loaded"
        assert zone.sensor is not None, "zone has no sensor"
        assert zone.sensor.id == "22:017762", f"unexpected sensor: {zone.sensor.id}"

        temp = await zone.temperature()
        assert temp == 27.1, f"Zone temperature not hydrated from sensor 30C9: {temp!r}"
    finally:
        await gwy.stop()
