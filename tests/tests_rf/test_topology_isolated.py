# --- START OF FILE test_topology_isolated.py ---

"""Isolated test to prove ramses_rf Phase 2.95 topology regressions.

This test completely bypasses Home Assistant and ramses_cc to evaluate
the raw output of the new TopologyBuilder and CentralDispatcher pipelines,
using the exact fixtures from the failing CI environment.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import pytest

from ramses_rf.gateway import Gateway, GatewayConfig
from ramses_tx.config import EngineConfig


async def async_flush_queues(gwy: Gateway) -> None:
    """Deterministically drain specific backend CQRS queues.

    Hardcoded references are used to avoid introspection side-effects.
    """
    queues: list[asyncio.Queue[Any]] = []

    if hasattr(gwy, "msg_queue") and isinstance(gwy.msg_queue, asyncio.Queue):
        queues.append(gwy.msg_queue)

    engine = getattr(gwy, "_engine", None)
    if engine and hasattr(engine, "_msg_queue"):
        if isinstance(engine._msg_queue, asyncio.Queue):
            queues.append(engine._msg_queue)

    dispatcher = getattr(gwy, "dispatcher", None) or getattr(
        gwy, "central_dispatcher", None
    )
    if dispatcher:
        for q_name in (
            "_in_queue",
            "ssot_queue",
            "discovery_queue",
            "binding_queue",
            "faked_queue",
        ):
            if hasattr(dispatcher, q_name):
                q = getattr(dispatcher, q_name)
                if isinstance(q, asyncio.Queue):
                    queues.append(q)

    for q in queues:
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(q.join(), timeout=5.0)

    for _ in range(50):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_ramses_rf_isolated_topology() -> None:
    """Test ramses_rf parsing an input log and building a graph."""

    # Provide the path to the packets_rcvd.log file you uploaded.
    # Adjust this path if running from a different directory.
    INPUT_FILE = "/home/phil/software/ramses_cc/tests/tests_new/fixtures/default/packets_rcvd.log"

    # 1. Translate configuration.yaml into native ramses_rf config
    known_list = {
        "01:145038": {"class": "CTL"},
        "03:123456": {"class": "THM", "faked": True},
        "10:123456": {"class": "OTB"},
        "18:006402": {"class": "HGI"},
        "13:120241": {"class": "BDR"},
        "13:120242": {"class": "BDR"},
        "07:046947": {"class": "DHW"},
        "34:092243": {"class": "THM"},
        "04:056053": {"class": "TRV"},
        "22:140285": {"class": "THM"},
        "04:189082": {"class": "TRV"},
        "13:081775": {"class": "BDR"},
        "13:202850": {"class": "BDR"},
        "32:097710": {"class": "CO2"},
        "32:139773": {"class": "HUM"},
    }

    # Translate the schema definitions
    schema = {
        "main_tcs": "01:145038",
        "01:145038": {
            "system": {"appliance_control": "10:123456"},
            "zones": {"00": {"sensor": "01:145038"}},
        },
    }

    engine_config = EngineConfig(
        disable_qos=True,
        input_file=INPUT_FILE,
        enforce_known_list=True,  # Crucial setting from config
        disable_sending=True,
    )

    gwy_config = GatewayConfig(
        disable_discovery=True,
        engine=engine_config,
        known_list=known_list,
        schema=schema,
    )

    # 2. Arrange: Instantiate raw Gateway
    gwy = Gateway(port_name=None, config=gwy_config)

    # 3. Act: Start gateway, process log, and flush queues
    await gwy.start()
    await async_flush_queues(gwy)
    await gwy.stop()

    # 4. Assert: Prove what ramses_rf actually built
    devices = {d.id: d for d in gwy.device_registry.devices}
    systems = gwy.device_registry.systems

    print("\n--- RAMSES_RF ISOLATED DIAGNOSTICS ---")
    print(f"Total Devices Found: {len(devices)}")
    print(f"Total Systems Found: {len(systems)}")
    print(f"Device IDs: {list(devices.keys())}")

    # Assert the Gateway / HGI exists
    assert "18:006402" in devices, (
        "CRITICAL: The Gateway (HGI) was not registered! "
        "Check device_registry.py instantiation."
    )

    # Assert the Controller exists (It is in the log AND the known_list)
    assert "01:145038" in devices, (
        "CRITICAL: The Controller was not registered! "
        "Check TopologyBuilder eavesdrop rules."
    )

    # Assert the faked Thermostat exists (It is NOT in the log!)
    # This will likely fail if Phase 2.95 requires packets to build devices.
    assert "03:123456" in devices, (
        "CRITICAL: The Faked Thermostat was not registered! "
        "The new architecture is ignoring configuration schemas."
    )

    # Assert the Evohome system was instantiated
    assert len(systems) > 0, "CRITICAL: TopologyBuilder failed to create a System!"
