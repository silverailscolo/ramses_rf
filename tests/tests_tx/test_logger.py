#!/usr/bin/env python3
"""Test for Issue #397: Move logging off the main event loop."""

import asyncio
import logging
from logging.handlers import QueueHandler, QueueListener
from pathlib import Path

import pytest

from ramses_rf import Gateway
from ramses_tx.packet import PKT_LOGGER


@pytest.mark.asyncio
async def test_logging_lifecycle(tmp_path: Path) -> None:
    """Verify that packet logging uses a QueueHandler and listener starts/stops."""

    log_file = tmp_path / "packet.log"
    input_file = tmp_path / "empty_input.log"
    input_file.touch()

    # 1. CLEANUP STATE (Aggressive)
    # Reset global disable level (Fixes suite pollution)
    logging.disable(logging.NOTSET)

    # Safely clear handlers
    for h in list(PKT_LOGGER.handlers):
        PKT_LOGGER.removeHandler(h)
    PKT_LOGGER.handlers.clear()
    PKT_LOGGER.filters.clear()
    PKT_LOGGER.setLevel(logging.DEBUG)
    PKT_LOGGER.disabled = False
    PKT_LOGGER.propagate = False

    # 2. Start Gateway
    gwy = Gateway(
        None,
        input_file=str(input_file),
        packet_log={"file_name": str(log_file)},  # type: ignore[arg-type]
    )
    await gwy.start()

    listener = gwy._pkt_log_listener

    try:
        # 3. Verify Wiring
        handlers = PKT_LOGGER.handlers
        assert len(handlers) == 1
        assert isinstance(handlers[0], QueueHandler), "Logger should use QueueHandler"
        assert isinstance(listener, QueueListener)

        # 4. Emit Log
        # ROBUSTNESS: Provide fallback 'frame' for standard Logger instances
        PKT_LOGGER.info(
            "TEST_LOG_ENTRY",
            extra={
                "_frame": "READ",
                "_rssi": "00",
                "frame": " 00 READ",
                "error_text": "",
                "comment": "",
            },
        )

        # Allow brief time for thread to process queue
        await asyncio.sleep(0.1)

    finally:
        # 5. Stop
        await gwy.stop()

    # 6. Check File
    with open(log_file) as f:
        content = f.read()
        assert "TEST_LOG_ENTRY" in content

    assert gwy._pkt_log_listener is None
