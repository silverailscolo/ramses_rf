"""Phase 2.95 OpenTherm and HVAC Ingestion State Parity Tests.

This suite mathematically verifies that the modern, asynchronous CQRS
StateIngestionWorker correctly maps complex OpenTherm boiler matrices
and heating telemetry to frozen memory states in parallel parity with
the legacy synchronous database lookup values.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Final, cast

import pytest

from ramses_rf import Gateway
from ramses_rf.const import DevType
from ramses_rf.gateway import GatewayConfig
from ramses_rf.models import HvacState, OpenThermState
from ramses_rf.pipeline.dispatcher import CentralDispatcher
from ramses_rf.pipeline.ingestion import StateProjector
from ramses_tx.const import SZ_READER_TASK

# Constants defining the target log file fixtures
LOG_OPENTHERM: Final[Path] = (
    Path(__file__).parent
    / "logs"
    / "test_phase2_95_topology_parity_packet_log_OpenTherm.log"
)

# Nuaire HVAC system capture test log file
LOG_HVAC: Final[Path] = (
    Path(__file__).parent.parent / "tests" / "systems" / "_hvac_nuaire" / "packet.log"
)

_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def suppress_noisy_logs(caplog: pytest.LogCaptureFixture) -> None:
    """Suppress massive volume of parsing warnings for this test file.

    :param caplog: The pytest log capture fixture.
    :type caplog: pytest.LogCaptureFixture
    :return: None
    :rtype: None
    """
    caplog.set_level(logging.CRITICAL, logger="ramses_tx")
    caplog.set_level(logging.CRITICAL, logger="ramses_rf")
    caplog.set_level(logging.CRITICAL, logger="asyncio")


async def _get_legacy_value(dev: Any, attr_name: str) -> Any:
    """Safely extract legacy state values across synchronous or async property bounds.

    Handles standard attributes, @properties, synchronous methods,
    and asynchronous coroutine methods seamlessly.

    :param dev: The hardware device entity instance to look up.
    :type dev: Any
    :param attr_name: The target property name string.
    :type attr_name: str
    :return: The extracted property value or None.
    :rtype: Any
    """
    if not hasattr(dev, attr_name):
        return None

    val = getattr(dev, attr_name)
    if callable(val):
        val = val()
    if asyncio.iscoroutine(val):
        val = await val

    return val


async def test_cqrs_opentherm_state_parity() -> None:
    """Verify that the async ingestion worker builds perfect OpenTherm state parity.

    Streams packets through the Gateway engine and checks that the newly populated
    frozen memory fields exactly match the legacy gateway's database properties.

    :return: None
    :rtype: None
    """
    config = GatewayConfig(enable_eavesdrop=True)
    config.engine.input_file = str(LOG_OPENTHERM)

    gwy = Gateway(None, config=config)

    pipeline_in_queue: asyncio.Queue[Any] = asyncio.Queue()
    dispatcher = CentralDispatcher(pipeline_in_queue)
    worker = StateProjector(gwy, dispatcher.ssot_queue)

    await dispatcher.start()
    await worker.start()

    legacy_handler = gwy._msg_handler

    async def parallel_strangler_bridge(dto: Any) -> None:
        await legacy_handler(dto)
        this_msg = getattr(gwy, "_this_msg", None)
        if this_msg:
            pipeline_in_queue.put_nowait(this_msg)

    gwy._engine._set_msg_handler(parallel_strangler_bridge)

    await gwy.start()

    if gwy._engine._transport:
        reader_task = gwy._engine._transport.get_extra_info(SZ_READER_TASK)
        if reader_task:
            await reader_task

    await asyncio.sleep(0.5)

    devices = gwy.device_registry.devices
    assert devices, "No devices extracted from the OpenTherm log stream"

    otb_count = 0
    for dev in devices:
        if getattr(dev, "_SLUG", "") == DevType.OTB and hasattr(dev, "opentherm_state"):
            otb_count += 1
            cqrs_ot = cast(OpenThermState, dev.opentherm_state)
            assert cqrs_ot is not None, f"{dev} missing CQRS opentherm_state container"

            # 1. Modulation Matrix Verification
            legacy_mod = await _get_legacy_value(dev, "rel_modulation_level")
            if legacy_mod is not None:
                assert cqrs_ot.rel_modulation_level == legacy_mod

            # 2. Boiler Water Flow Telemetry Verification
            legacy_out = await _get_legacy_value(dev, "boiler_output_temp")
            if legacy_out is not None:
                assert cqrs_ot.boiler_output_temp == legacy_out

            # 3. Boiler Return Water Telemetry Verification
            legacy_ret = await _get_legacy_value(dev, "boiler_return_temp")
            if legacy_ret is not None:
                assert cqrs_ot.boiler_return_temp == legacy_ret

            # 4. Status Bitmask Flags Verification
            legacy_flame = await _get_legacy_value(dev, "flame_active")
            if legacy_flame is not None:
                assert cqrs_ot.flame_active == legacy_flame

    assert otb_count > 0, "No OpenTherm Bridge (OTB) entity found in context"

    await dispatcher.stop()
    await worker.stop()
    await gwy.stop()


async def test_cqrs_hvac_state_parity() -> None:
    """Verify that the async ingestion worker builds perfect HVAC state parity.

    Streams a ventilation system packet log and asserts the CQRS HvacState
    perfectly mirrors the legacy state properties.

    :return: None
    :rtype: None
    """
    if not LOG_HVAC.exists():
        pytest.skip(f"HVAC fixture not found at {LOG_HVAC}")

    config = GatewayConfig(enable_eavesdrop=True)
    config.engine.input_file = str(LOG_HVAC)

    gwy = Gateway(None, config=config)

    pipeline_in_queue: asyncio.Queue[Any] = asyncio.Queue()
    dispatcher = CentralDispatcher(pipeline_in_queue)
    worker = StateProjector(gwy, dispatcher.ssot_queue)

    await dispatcher.start()
    await worker.start()

    legacy_handler = gwy._msg_handler

    async def parallel_strangler_bridge(dto: Any) -> None:
        await legacy_handler(dto)
        this_msg = getattr(gwy, "_this_msg", None)
        if this_msg:
            pipeline_in_queue.put_nowait(this_msg)

    gwy._engine._set_msg_handler(parallel_strangler_bridge)

    await gwy.start()

    if gwy._engine._transport:
        reader_task = gwy._engine._transport.get_extra_info(SZ_READER_TASK)
        if reader_task:
            await reader_task

    await asyncio.sleep(0.5)

    devices = gwy.device_registry.devices
    assert devices, "No devices extracted from the HVAC log stream"

    hvac_count = 0
    for dev in devices:
        # HVAC devices usually register as HVC, FAN, or generic devices with hvac_state
        if hasattr(dev, "hvac_state"):
            cqrs_hvac = cast(HvacState, dev.hvac_state)

            # Since the Nuaire log is short, some devices might just be bare shells.
            # We only test if the CQRS engine actually captured data for it.
            if cqrs_hvac.last_updated is not None:
                hvac_count += 1

                # Compare CO2
                legacy_co2 = await _get_legacy_value(dev, "co2_level")
                if legacy_co2 is not None:
                    assert cqrs_hvac.co2_level == legacy_co2

                # Compare Indoor Humidity
                legacy_hum = await _get_legacy_value(dev, "indoor_humidity")
                if legacy_hum is not None:
                    assert cqrs_hvac.indoor_humidity == legacy_hum

                # Compare Fan Mode
                legacy_mode = await _get_legacy_value(dev, "fan_mode")
                if legacy_mode is not None:
                    assert cqrs_hvac.fan_mode == legacy_mode

    assert hvac_count > 0, "No HVAC entity with state found in context"

    await dispatcher.stop()
    await worker.stop()
    await gwy.stop()
