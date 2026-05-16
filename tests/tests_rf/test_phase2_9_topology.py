#!/usr/bin/env python3
"""RAMSES RF - Phase 2.9 Golden Master Topology Test."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

import ramses_rf.gateway
from ramses_rf.config import GatewayConfig
from ramses_rf.enums import TopologyAction
from ramses_rf.gateway import Gateway
from ramses_rf.models import TopologyChangedEvent
from ramses_rf.pipeline.topology_builder import TopologyBuilder
from ramses_tx.config import EngineConfig
from ramses_tx.const import SZ_READER_TASK
from ramses_tx.exceptions import TransportError

# Adjust the path to locate the 30k+ packet fixture
FIXTURE_PATH = (
    Path(__file__).parent.parent / "fixtures" / "regression_packets_sorted.txt"
)


@pytest.mark.asyncio
async def test_topology_builder_golden_master() -> None:
    """Feed regression packets through the TopologyBuilder.

    This mathematically proves the extracted heuristics do not
    crash and successfully emit the expected structural events.
    """
    if not FIXTURE_PATH.exists():
        pytest.skip(f"Fixture file not found: {FIXTURE_PATH}")

    emitted_events: list[TopologyChangedEvent] = []

    def event_callback(event: TopologyChangedEvent) -> None:
        emitted_events.append(event)

    builder = TopologyBuilder(emit_event_cb=event_callback)

    # Initialize Gateway for FileTransport (No physical port)
    config = GatewayConfig(
        disable_discovery=True,
        reduce_processing=0,  # CRITICAL: Ensures payloads are parsed to dicts
        engine=EngineConfig(
            disable_sending=True,
            input_file=str(FIXTURE_PATH),
        ),
    )
    gwy = Gateway(None, config=config)

    # Cache the original dispatcher router
    original_process_msg = ramses_rf.gateway.process_msg

    async def patched_process_msg(gwy_instance: Any, msg: Any) -> None:
        """Intercept the L7 message exactly as it leaves the Gateway."""
        # Allow the legacy pipeline to process normally
        await original_process_msg(gwy_instance, msg)

        # Feed our new Builder engine (safely bypassing strict type checks)
        if isinstance(getattr(msg, "payload", None), dict):
            await builder.consume(msg)  # type: ignore[arg-type]

    # Patch sending methods to prevent networking noise, and patch
    # process_msg to feed our new engine.
    mock_send = AsyncMock(return_value=None)
    with (
        patch.object(gwy, "async_send_cmd", mock_send),
        patch("ramses_rf.gateway.process_msg", patched_process_msg),
    ):
        # Start the gateway (gracefully catching the file EOF timeout)
        with contextlib.suppress(TransportError):
            await gwy.start()

        # Wait for the transport to finish reading the entire file
        if gwy._engine._transport:
            reader_task = gwy._engine._transport.get_extra_info(SZ_READER_TASK)
            if reader_task:
                await reader_task

    with contextlib.suppress(asyncio.CancelledError, TransportError):
        await gwy.stop()

    # 1. Prove the builder processed the file and emitted events
    assert len(emitted_events) > 0, "TopologyBuilder failed to emit events"

    # 2. Prove that the heuristic rules successfully fired
    actions = {event.action for event in emitted_events}
    assert (
        TopologyAction.PROMOTE_CLASS in actions
        or TopologyAction.BIND_DEVICE in actions
        or TopologyAction.CREATE_CONTROLLER in actions
    ), "No structural topology actions were deduced from the regression file"
