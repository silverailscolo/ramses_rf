#!/usr/bin/env python3
"""Unit tests for the CallbackTransport (Inversion of Control)."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from ramses_tx import exceptions as exc
from ramses_tx.transport import CallbackTransport


class TestCallbackTransport(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.mock_protocol = MagicMock()
        self.mock_writer = AsyncMock()

        # Initialize transport with our mocks
        self.transport = CallbackTransport(
            self.mock_protocol, io_writer=self.mock_writer
        )

    async def test_initial_state_is_paused(self) -> None:
        """Verify transport starts in PAUSED state (Circuit Breaker default)."""
        # It should default to not reading until explicitly resumed
        self.assertFalse(self.transport.is_reading())

    async def test_write_frame_delegates_to_writer(self) -> None:
        """Verify outbound frames are passed to the injected io_writer."""
        test_frame = "RQ --- 18:000730 18:000730 --:------ 00E0 001 00"

        await self.transport.write_frame(test_frame)

        # Check if the injected writer was called with the exact frame
        self.mock_writer.assert_awaited_once_with(test_frame)

    async def test_receive_frame_respects_circuit_breaker(self) -> None:
        """Verify inbound frames are gated by pause/resume state."""
        test_frame = "I --- 18:000730 --:------ 18:000730 0008 002 0000"

        # 1. Test while PAUSED (Initial State)
        self.transport.pause_reading()
        self.transport.receive_frame(test_frame)

        # Protocol should NOT have received data
        self.mock_protocol.pkt_received.assert_not_called()

        # 2. Test while RESUMED
        self.transport.resume_reading()
        self.transport.receive_frame(test_frame)

        # Protocol SHOULD receive data now
        # Note: pkt_received is called with a Packet object, so we verify call count
        self.assertEqual(self.mock_protocol.pkt_received.call_count, 1)

    async def test_write_error_handling(self) -> None:
        """Verify writer exceptions are wrapped in TransportError."""
        self.mock_writer.side_effect = Exception("MQTT Connection Lost")

        with self.assertRaises(exc.TransportError):
            await self.transport.write_frame("test_frame")
