"""Isolated test to prove ramses_rf Phase 2.95 topology regressions.

This test completely bypasses Home Assistant and ramses_cc to evaluate
the raw output of the new TopologyBuilder and CentralDispatcher pipelines.
"""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from ramses_rf.gateway import Gateway, GatewayConfig
from ramses_tx.config import EngineConfig


async def async_flush_queues(gwy: Gateway) -> None:
    """Deterministically drain specific backend CQRS queues."""
    queues: list[asyncio.Queue] = []

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

    # TODO: Update this path to point to the log file you upload
    INPUT_FILE = "/home/phil/software/ramses_cc/tests/tests_old/test_data/system_1.log"

    engine_config = EngineConfig(
        disable_qos=True,
        input_file=INPUT_FILE,
    )

    gwy_config = GatewayConfig(
        disable_discovery=True,  # Match the HA test setup
        hgi_id="18:006402",  # Explicitly declare the physical hardware adapter
        engine=engine_config,
    )

    # 1. Arrange: Instantiate raw Gateway
    gwy = Gateway(port_name=None, config=gwy_config)

    # 2. Act: Start gateway, process log, and flush queues
    await gwy.start()
    await async_flush_queues(gwy)
    await gwy.stop()

    # 3. Assert: Prove what ramses_rf actually built
    devices = {d.id: d for d in gwy.device_registry.devices}
    systems = gwy.device_registry.systems

    print("\n--- RAMSES_RF ISOLATED DIAGNOSTICS ---")
    print(f"Total Devices Found: {len(devices)}")
    print(f"Total Systems Found: {len(systems)}")
    print(f"Device IDs: {list(devices.keys())}")

    # Assert the Gateway / HGI exists
    assert "18:006402" in devices, "CRITICAL: The Gateway (HGI) was not registered!"

    # Assert the Controller exists
    assert "01:145038" in devices, "CRITICAL: The Controller was not registered!"

    # Assert the Evohome system was instantiated
    assert len(systems) > 0, "CRITICAL: The TopologyBuilder failed to create a System!"

    # Assert specific bound devices actually found in system_1.log
    assert "13:120241" in devices, "CRITICAL: The BDR91 (13:120241) was not registered!"
    assert "04:056053" in devices, "CRITICAL: The TRV (04:056053) was not registered!"
