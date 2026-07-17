"""Test suite ensuring the TopologyBuilder parses packet logs identically over time."""

import asyncio
import contextlib
from pathlib import Path
from typing import Any, cast

import pytest

from ramses_rf import Gateway

from .conftest import TEST_DIR

# Define the log files to use for parity testing
LOG_STANDARD = Path(f"{TEST_DIR}/logs/test_phase2_95_topology_parity_packet_log.log")
LOG_OPENTHERM = Path(
    f"{TEST_DIR}/logs/test_phase2_95_topology_parity_packet_log_OpenTherm.log"
)


@pytest.fixture(autouse=True)
def suppress_asyncio_warnings(caplog: pytest.LogCaptureFixture) -> None:
    """Suppress noisy asyncio task cancelled warnings during Gateway shutdown."""
    import logging

    caplog.set_level(logging.CRITICAL, logger="asyncio")


@pytest.fixture(params=[LOG_STANDARD, LOG_OPENTHERM], ids=["standard", "opentherm"])
def log_file_path(request: pytest.FixtureRequest) -> Path:
    """Provide the packet log file path for topology parity testing."""
    return cast(Path, request.param)


async def drain_cqrs_queues(gwy_cqrs: Gateway) -> None:
    """Ensure all CQRS event bus queues are fully drained before proceeding."""
    dispatcher = getattr(gwy_cqrs, "dispatcher", None)

    if dispatcher:
        if hasattr(dispatcher, "discovery_queue"):
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(dispatcher.discovery_queue.join(), timeout=10)

        if hasattr(dispatcher, "ssot_queue"):
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(dispatcher.ssot_queue.join(), timeout=10)

        if hasattr(dispatcher, "binding_fsm_queue"):
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(dispatcher.binding_fsm_queue.join(), timeout=10)

    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_topology_builder_snapshot(log_file_path: Path, snapshot: Any) -> None:
    """Test that the async TopologyBuilder yields a consistent schema over time."""
    # ------------------------------------------------------------------------
    # STEP 1: Run the Async Pipeline
    # ------------------------------------------------------------------------
    # Instantiate the Gateway directly with eavesdrop enabled
    from ramses_rf.gateway import GatewayConfig

    async_config = GatewayConfig(enable_eavesdrop=True)
    async_config.engine.input_file = str(log_file_path)

    async_gwy = Gateway(None, config=async_config)

    await async_gwy.start()
    if async_gwy._engine._transport:
        reader_task = async_gwy._engine._transport.get_extra_info("reader_task")
        if reader_task:
            with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(reader_task, timeout=30)

    # ------------------------------------------------------------------------
    # STEP 2: Explicit Queue Drain
    # ------------------------------------------------------------------------
    await drain_cqrs_queues(async_gwy)

    raw_schema = await async_gwy.device_registry.generate_schema()  # type: ignore[attr-defined]

    await async_gwy.stop()

    # ------------------------------------------------------------------------
    # STEP 3: Assert against Snapshot
    # ------------------------------------------------------------------------
    # We use syrupy to lock the schema into a snapshot file, so any future
    # refactors that alter the schema unexpectedly will flag as regressions.
    assert raw_schema == snapshot
