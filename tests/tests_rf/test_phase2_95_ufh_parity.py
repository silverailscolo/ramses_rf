"""Phase 2.95 UFH and Actuator CQRS Shadow State Parity Tests.

This suite mathematically verifies that the modern, asynchronous CQRS
StateProjector correctly maps complex Underfloor Heating (UFH) arrays
and Actuator telemetry to frozen memory states, ensuring perfect parity
with the legacy synchronous database lookup values.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Final, cast

import pytest

from ramses_rf import Gateway
from ramses_rf.gateway import GatewayConfig
from ramses_rf.models import ActuatorState, UfhState
from ramses_rf.pipeline.dispatcher import CentralDispatcher
from ramses_rf.pipeline.ingestion import StateProjector
from ramses_tx.const import SZ_READER_TASK

# Constants defining the target log file fixtures
LOG_HEATING: Final[Path] = (
    Path(__file__).parent / "logs" / "test_phase2_95_topology_parity_packet_log.log"
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
    """Safely extract legacy state values across synchronous or async bounds.

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


async def test_cqrs_ufh_and_actuator_state_parity() -> None:
    """Verify async ingestion builds perfect UFH and Actuator state parity.

    Streams packets through the Gateway engine and checks that the newly
    populated frozen memory fields exactly match the legacy gateway's
    complex array and dict lookup properties.

    :return: None
    :rtype: None
    """
    if not LOG_HEATING.exists():
        pytest.skip(f"Heating fixture not found at {LOG_HEATING}")

    # Arrange
    config = GatewayConfig(enable_eavesdrop=True)
    config.engine.input_file = str(LOG_HEATING)

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

    # Act
    await gwy.start()

    if gwy._engine._transport:
        reader_task = gwy._engine._transport.get_extra_info(SZ_READER_TASK)
        if reader_task:
            await reader_task

    await asyncio.sleep(0.5)

    # Assert
    devices = gwy.device_registry.devices
    assert devices, "No devices extracted from the Heating log stream"

    ufc_count = 0
    act_count = 0

    for dev in devices:
        # 1. Assert Underfloor Heating (UFH) Parity
        if hasattr(dev, "ufh_state"):
            ufc_count += 1
            cqrs_ufh = cast(UfhState, dev.ufh_state)

            legacy_demands = await _get_legacy_value(dev, "heat_demands")
            if legacy_demands is not None:
                assert cqrs_ufh.heat_demands == legacy_demands

            legacy_setpoints = await _get_legacy_value(dev, "setpoints")
            if legacy_setpoints is not None:
                assert cqrs_ufh.setpoints == legacy_setpoints

            legacy_relay_fa = await _get_legacy_value(dev, "relay_demand_fa")
            if legacy_relay_fa is not None:
                assert cqrs_ufh.relay_demand_fa == legacy_relay_fa

        # 2. Assert Actuator (BDR91/OTB) Parity
        # Notice we changed 'actuator_state' to 'act_state' to avoid method masking
        if hasattr(dev, "act_state"):
            act_count += 1
            cqrs_act = cast(ActuatorState, dev.act_state)

            legacy_state = await _get_legacy_value(dev, "actuator_state")
            if legacy_state is not None:
                if "modulation_level" in legacy_state:
                    assert cqrs_act.modulation_level == legacy_state["modulation_level"]
                elif "rel_modulation_level" in legacy_state:
                    assert (
                        cqrs_act.modulation_level
                        == legacy_state["rel_modulation_level"]
                    )

                if "actuator_enabled" in legacy_state:
                    assert cqrs_act.actuator_enabled == legacy_state["actuator_enabled"]

                if "ch_active" in legacy_state:
                    assert cqrs_act.ch_active == legacy_state["ch_active"]

                if "ch_enabled" in legacy_state:
                    assert cqrs_act.ch_enabled == legacy_state["ch_enabled"]

                if "dhw_active" in legacy_state:
                    assert cqrs_act.dhw_active == legacy_state["dhw_active"]

                if "flame_on" in legacy_state:
                    assert cqrs_act.flame_active == legacy_state["flame_on"]

    assert ufc_count > 0 or act_count > 0, (
        "No UFH or Actuator entities found in the test context"
    )

    await dispatcher.stop()
    await worker.stop()
    await gwy.stop()
