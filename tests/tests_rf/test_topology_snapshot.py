"""Test suite ensuring the TopologyBuilder parses packet logs identically over time."""

import asyncio
import contextlib
from pathlib import Path
from typing import Any, cast

import pytest

from ramses_rf import Gateway

from .conftest import TEST_DIR

# Define the log files to use for topology snapshot testing
LOG_STANDARD = Path(f"{TEST_DIR}/logs/topology_sample.log")
LOG_OPENTHERM = Path(f"{TEST_DIR}/logs/topology_sample_opentherm.log")


@pytest.fixture(autouse=True)
def suppress_asyncio_warnings(caplog: pytest.LogCaptureFixture) -> None:
    """Suppress noisy asyncio task cancelled warnings during Gateway shutdown."""
    import logging

    caplog.set_level(logging.CRITICAL, logger="asyncio")


@pytest.fixture(
    params=[LOG_STANDARD, LOG_OPENTHERM], ids=["standard", "opentherm"]
)
def log_file_path(request: pytest.FixtureRequest) -> Path:
    """Provide the packet log file path for topology snapshot testing."""
    return cast(Path, request.param)


async def drain_cqrs_queues(gwy_cqrs: Gateway) -> None:
    """Ensure all CQRS event bus queues are fully drained before proceeding."""
    dispatcher = getattr(gwy_cqrs, "dispatcher", None)

    if dispatcher:
        if hasattr(dispatcher, "discovery_queue"):
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    dispatcher.discovery_queue.join(), timeout=10
                )

        if hasattr(dispatcher, "ssot_queue"):
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    dispatcher.ssot_queue.join(), timeout=10
                )

        if hasattr(dispatcher, "binding_fsm_queue"):
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    dispatcher.binding_fsm_queue.join(), timeout=10
                )

    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_topology_builder_snapshot(
    log_file_path: Path, snapshot: Any
) -> None:
    """Test that the async TopologyBuilder yields a consistent schema over time."""
    # Arrange
    from ramses_rf.gateway import GatewayConfig

    async_config = GatewayConfig(enable_eavesdrop=False)
    async_config.engine.input_file = str(log_file_path)

    async_gwy = Gateway(None, config=async_config)

    # Act
    await async_gwy.start()
    if async_gwy._engine._transport:
        reader_task = async_gwy._engine._transport.get_extra_info(
            "reader_task"
        )
        if reader_task:
            with contextlib.suppress(
                asyncio.TimeoutError, asyncio.CancelledError
            ):
                await asyncio.wait_for(reader_task, timeout=30)

    await drain_cqrs_queues(async_gwy)

    raw_schema = await async_gwy.device_registry.generate_schema()  # type: ignore[attr-defined]

    await async_gwy.stop()

    # Assert
    assert raw_schema == snapshot
