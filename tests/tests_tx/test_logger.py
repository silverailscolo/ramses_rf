#!/usr/bin/env python3
"""Test for Issue #397: Move logging off the main event loop."""

import asyncio
import logging
from logging.handlers import QueueHandler, QueueListener
from pathlib import Path

import pytest

from ramses_rf import Gateway, GatewayConfig
from ramses_tx.logger import flush_packet_log
from ramses_tx.packet import PKT_LOGGER


@pytest.mark.asyncio
async def test_logging_lifecycle(tmp_path: Path) -> None:
    """Verify that packet logging uses a QueueHandler and listener starts/stops.

    :param tmp_path: The temporary directory path provided by pytest.
    """

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
        config=GatewayConfig(
            input_file=str(input_file),
            packet_log={
                "packet_log_path": str(tmp_path),
                "packet_log_prefix": "packet",
            },
        ),
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

        # Poll for the log to be written (up to 1 second)
        for _ in range(100):
            await asyncio.sleep(0.01)
            if log_file.exists() and "TEST_LOG_ENTRY" in log_file.read_text():
                break

    finally:
        # 5. Stop
        await gwy.stop()
        # Verify the listener cleanly stopped
        assert gwy._pkt_log_listener is None


@pytest.mark.asyncio
async def test_flight_recorder_auto_flush(tmp_path: Path) -> None:
    """Verify that the flight recorder buffers logs and auto-flushes on warnings.

    :param tmp_path: The temporary directory path provided by pytest.
    """
    log_file = tmp_path / "flight_recorder_auto.log"
    input_file = tmp_path / "empty_input.log"
    input_file.touch()

    logging.disable(logging.NOTSET)
    for h in list(PKT_LOGGER.handlers):
        PKT_LOGGER.removeHandler(h)
    PKT_LOGGER.handlers.clear()
    PKT_LOGGER.filters.clear()
    PKT_LOGGER.setLevel(logging.DEBUG)
    PKT_LOGGER.disabled = False
    PKT_LOGGER.propagate = False

    gwy = Gateway(
        None,
        config=GatewayConfig(
            input_file=str(input_file),
            packet_log={
                "packet_log_path": str(tmp_path),
                "packet_log_prefix": "flight_recorder_auto",
                "buffer_capacity": 10,
                "flush_level": logging.WARNING,  # Adjusted to pass PktLogFilter
            },
        ),
    )
    await gwy.start()

    try:
        # 1. Emit an INFO log; it should remain in memory, NOT on disk
        PKT_LOGGER.info(
            "BUFFERED_INFO_LOG",
            extra={
                "_frame": "READ",
                "_rssi": "00",
                "frame": " 00 READ",
                "error_text": "",
                "comment": "",
            },
        )

        await asyncio.sleep(0.1)  # Allow background queue to process
        if log_file.exists():
            assert "BUFFERED_INFO_LOG" not in log_file.read_text()

        # 2. Emit a WARNING log; this must trigger the MemoryHandler to flush
        PKT_LOGGER.warning(
            "TRIGGER_WARNING_LOG",
            extra={
                "_frame": "READ",
                "_rssi": "00",
                "frame": " 00 READ",
                "error_text": "",
                "comment": "",
            },
        )

        # Poll for the flush to hit the disk
        for _ in range(100):
            await asyncio.sleep(0.01)
            if log_file.exists() and "TRIGGER_WARNING_LOG" in log_file.read_text():
                break

        content = log_file.read_text()
        assert "BUFFERED_INFO_LOG" in content, "Buffered INFO log was lost"
        assert "TRIGGER_WARNING_LOG" in content, "WARNING log failed to trigger flush"

    finally:
        await gwy.stop()


@pytest.mark.asyncio
async def test_flight_recorder_manual_flush(tmp_path: Path) -> None:
    """Verify that the flight recorder flushes cleanly when manually requested.

    :param tmp_path: The temporary directory path provided by pytest.
    """
    log_file = tmp_path / "flight_recorder_manual.log"
    input_file = tmp_path / "empty_input.log"
    input_file.touch()

    logging.disable(logging.NOTSET)
    for h in list(PKT_LOGGER.handlers):
        PKT_LOGGER.removeHandler(h)
    PKT_LOGGER.handlers.clear()
    PKT_LOGGER.filters.clear()
    PKT_LOGGER.setLevel(logging.DEBUG)
    PKT_LOGGER.disabled = False
    PKT_LOGGER.propagate = False

    gwy = Gateway(
        None,
        config=GatewayConfig(
            input_file=str(input_file),
            packet_log={
                "packet_log_path": str(tmp_path),
                "packet_log_prefix": "flight_recorder_manual",
                "buffer_capacity": 10,
                "flush_level": logging.ERROR,
            },
        ),
    )
    await gwy.start()
    listener = gwy._pkt_log_listener

    try:
        # Emit an INFO log; verify it stays in memory
        PKT_LOGGER.info(
            "MANUAL_FLUSH_TARGET",
            extra={
                "_frame": "READ",
                "_rssi": "00",
                "frame": " 00 READ",
                "error_text": "",
                "comment": "",
            },
        )

        await asyncio.sleep(0.1)
        if log_file.exists():
            assert "MANUAL_FLUSH_TARGET" not in log_file.read_text()

        # Trigger manual flush
        flush_packet_log(listener)

        for _ in range(100):
            await asyncio.sleep(0.01)
            if log_file.exists() and "MANUAL_FLUSH_TARGET" in log_file.read_text():
                break

        assert "MANUAL_FLUSH_TARGET" in log_file.read_text()

    finally:
        await gwy.stop()


@pytest.mark.asyncio
async def test_flight_recorder_time_flush(tmp_path: Path) -> None:
    """Verify that the flight recorder flushes cleanly on a timer.

    :param tmp_path: The temporary directory path provided by pytest.
    """
    log_file = tmp_path / "flight_recorder_time.log"
    input_file = tmp_path / "empty_input.log"
    input_file.touch()

    logging.disable(logging.NOTSET)
    for h in list(PKT_LOGGER.handlers):
        PKT_LOGGER.removeHandler(h)
    PKT_LOGGER.handlers.clear()
    PKT_LOGGER.filters.clear()
    PKT_LOGGER.setLevel(logging.DEBUG)
    PKT_LOGGER.disabled = False
    PKT_LOGGER.propagate = False

    gwy = Gateway(
        None,
        config=GatewayConfig(
            input_file=str(input_file),
            packet_log={
                "packet_log_path": str(tmp_path),
                "packet_log_prefix": "flight_recorder_time",
                "buffer_capacity": 10,
                "flush_level": logging.ERROR,
                "flush_interval": 0.2,  # Flush every 200ms
            },
        ),
    )
    await gwy.start()

    try:
        # Emit an INFO log; verify it stays in memory initially
        PKT_LOGGER.info(
            "TIMER_FLUSH_TARGET",
            extra={
                "_frame": "READ",
                "_rssi": "00",
                "frame": " 00 READ",
                "error_text": "",
                "comment": "",
            },
        )

        # Allow time to hit the queue but assert it hasn't flushed to disk yet
        await asyncio.sleep(0.05)
        if log_file.exists():
            assert "TIMER_FLUSH_TARGET" not in log_file.read_text()

        # Wait for timer to trigger naturally (after 200ms)
        for _ in range(100):
            await asyncio.sleep(0.05)
            if log_file.exists() and "TIMER_FLUSH_TARGET" in log_file.read_text():
                break

        assert "TIMER_FLUSH_TARGET" in log_file.read_text()

    finally:
        await gwy.stop()
