#!/usr/bin/env python3
"""Tests for CallbackTransport initialization logic."""

import asyncio
from functools import partial
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ramses_tx import exceptions as exc
from ramses_tx.discovery import is_hgi80
from ramses_tx.transport import TransportConfig, transport_factory
from ramses_tx.transport.callback import CallbackTransport
from ramses_tx.typing import SerPortNameT


async def _async_callback_factory(
    protocol: Any, io_writer: Any = None, *, config: TransportConfig, **kwargs: Any
) -> CallbackTransport:
    """Async wrapper for CallbackTransport to satisfy transport_factory signature."""
    return CallbackTransport(protocol, io_writer, config=config, **kwargs)


async def test_callback_transport_handshake() -> None:
    """Test that connection_made is called automatically upon initialization."""
    mock_protocol = Mock()
    mock_writer = AsyncMock()

    transport = CallbackTransport(mock_protocol, mock_writer, config=TransportConfig())

    # Assert handshake called immediately
    mock_protocol.connection_made.assert_called_once_with(transport, ramses=True)


async def test_callback_transport_handshake_idempotency() -> None:
    """Test that manual connection_made calls are safe (idempotent at protocol level)."""
    mock_protocol = Mock()
    mock_writer = AsyncMock()

    transport = CallbackTransport(mock_protocol, mock_writer, config=TransportConfig())

    # Verify initial call
    mock_protocol.connection_made.assert_called_once()

    # Manually call again (simulating legacy consumer behavior)
    mock_protocol.connection_made(transport, ramses=True)

    # Assert called twice without error (protocol impl handles idempotency logic)
    assert mock_protocol.connection_made.call_count == 2


async def test_callback_transport_autostart_false() -> None:
    """Test that reading is paused by default (autostart=False)."""
    mock_protocol = Mock()
    mock_writer = AsyncMock()

    transport = CallbackTransport(
        mock_protocol, mock_writer, config=TransportConfig(autostart=False)
    )

    assert transport.is_reading() is False


async def test_callback_transport_autostart_default() -> None:
    """Test that reading is paused by default (backward compatibility)."""
    mock_protocol = Mock()
    mock_writer = AsyncMock()

    transport = CallbackTransport(mock_protocol, mock_writer, config=TransportConfig())

    assert transport.is_reading() is False


async def test_callback_transport_autostart_true() -> None:
    """Test that reading is resumed automatically if autostart=True."""
    mock_protocol = Mock()
    mock_writer = AsyncMock()

    transport = CallbackTransport(
        mock_protocol, mock_writer, config=TransportConfig(autostart=True)
    )

    assert transport.is_reading() is True


async def test_factory_routes_autostart_to_custom_constructor() -> None:
    """Check that autostart is passed to a custom transport_constructor."""
    mock_protocol = Mock()
    mock_writer = AsyncMock()

    # 1. Test with autostart=True
    # NOTE: transport_factory awaits the constructor, so we pass an async callable via partial
    transport = await transport_factory(
        mock_protocol,
        transport_constructor=partial(_async_callback_factory, io_writer=mock_writer),
        config=TransportConfig(autostart=True),
    )
    assert isinstance(transport, CallbackTransport)
    assert transport.is_reading() is True

    # 2. Test with autostart=False (default)
    transport_paused = await transport_factory(
        mock_protocol,
        transport_constructor=partial(_async_callback_factory, io_writer=mock_writer),
        config=TransportConfig(autostart=False),
    )
    assert isinstance(transport_paused, CallbackTransport)
    assert transport_paused.is_reading() is False


async def test_factory_passes_config_to_standard_transport() -> None:
    """Check that config is strictly passed to standard transports.

    If it isn't passed, the standard transports (PortTransport/MqttTransport)
    would raise TypeError missing 'config' in __init__.
    """
    mock_protocol = Mock()
    mock_protocol.wait_for_connection_made = AsyncMock()

    # We patch where they are USED (factory.py), not where they are DEFINED
    with (
        patch("ramses_tx.transport.factory.PortTransport") as MockPortTransport,
        patch("ramses_tx.transport.factory.serial_for_url") as mock_serial_for_url,
    ):
        # Setup the mock serial object to pass validity checks
        mock_serial = Mock()
        mock_serial.portstr = "/dev/ttyUSB0"
        mock_serial_for_url.return_value = mock_serial

        # valid-looking config so factory enters the Serial branch
        port_config: Any = {}
        transport_config = TransportConfig(autostart=True)

        await transport_factory(
            mock_protocol,
            port_name=SerPortNameT("/dev/ttyUSB0"),
            port_config=port_config,
            config=transport_config,
        )

        # Assert PortTransport was called
        assert MockPortTransport.call_count == 1

        # Verify 'autostart' was NOT in the call args
        call_args = MockPortTransport.call_args
        assert "config" in call_args.kwargs
        assert call_args.kwargs["config"] is transport_config


async def test_factory_passes_config_to_mqtt_transport() -> None:
    """Check that config is strictly passed to MqttTransport."""
    mock_protocol = Mock()
    mock_protocol.wait_for_connection_made = AsyncMock()

    # We patch where it is USED (factory.py)
    with patch("ramses_tx.transport.factory.MqttTransport") as MockMqttTransport:
        # valid-looking config so factory enters the MQTT branch
        # We must provide port_config because transport_factory validates it
        # is not None even for MQTT
        port_config: Any = {}
        transport_config = TransportConfig(autostart=True)

        await transport_factory(
            mock_protocol,
            port_name=SerPortNameT("mqtt://broker:1883"),
            port_config=port_config,
            config=transport_config,
        )

        assert MockMqttTransport.call_count == 1
        call_args = MockMqttTransport.call_args
        assert "config" in call_args.kwargs
        assert call_args.kwargs["config"] is transport_config


async def test_port_transport_close_robustness() -> None:
    """Check that PortTransport.close() does not raise AttributeError if init failed.

    This ensures that _close() checks for the existence of _init_task before
    attempting to cancel it.
    """
    from ramses_tx.transport.port import PortTransport

    mock_protocol = Mock()
    mock_serial = Mock()

    # Define a side_effect for SerialTransport.__init__ that sets required attributes
    # PortTransport expects _loop to be set by the parent class
    def mock_init(self: Any, loop: Any, protocol: Any, serial_instance: Any) -> None:
        self._loop = loop or asyncio.get_event_loop()
        self._protocol = protocol
        self._serial = serial_instance  # Set backing attribute directly

    # Patch SerialTransport.__init__ using 'new' to replace it with the function directly.
    # This ensures 'self' is passed correctly, which doesn't happen with a standard Mock side_effect.
    with patch(
        "ramses_tx.transport.port.serial_asyncio.SerialTransport.__init__",
        new=mock_init,
    ):
        transport = PortTransport(mock_serial, mock_protocol, config=TransportConfig())

        # Pre-condition: _init_task is created asynchronously, so it shouldn't exist yet
        # because we haven't yielded to the event loop
        assert not hasattr(transport, "_init_task")

        # Execute close - should not raise AttributeError
        transport.close()


async def test_is_hgi80_async_file_check() -> None:
    """Check that is_hgi80 uses loop.run_in_executor for file existence checks."""

    # We define a path that contains "by-id" and "evofw3".
    # This ensures that is_hgi80 returns False immediately after the file check,
    # preventing it from proceeding to the complex 'comports' logic which triggers I/O.
    test_port = SerPortNameT("/dev/serial/by-id/usb-SparkFun_evofw3_TEST")

    # 1. Test: File exists (should return False due to 'evofw3' in name)
    # We patch os.path.exists where it is used (port.py)
    with patch("ramses_tx.discovery.os.path.exists", return_value=True) as mock_exists:
        result = await is_hgi80(test_port)

        # Assert: os.path.exists was called with the correct path
        mock_exists.assert_called_once_with(test_port)
        # Assert: Logic correctly identified it as NOT HGI80 (due to evofw3 name)
        assert result is False

    # 2. Test: File does NOT exist (should raise TransportSerialError)
    # We patch os.path.exists to return False
    with patch("ramses_tx.discovery.os.path.exists", return_value=False) as mock_exists:
        with pytest.raises(exc.TransportSerialError):
            await is_hgi80(test_port)

        # Assert: os.path.exists was called
        mock_exists.assert_called_once_with(test_port)


# --- Event-loop-closed guards (issue 802) ---


def _make_read_transport(loop: asyncio.AbstractEventLoop) -> Any:
    """Create a minimal _ReadTransport for testing _pkt_read/_close."""
    from ramses_tx.transport.base import _ReadTransport

    transport = _ReadTransport.__new__(_ReadTransport)
    transport._loop = loop
    transport._protocol = Mock()
    transport._closing = False
    transport._reading = False
    transport._this_pkt = None
    transport._prev_pkt = None
    transport._extra = {}
    transport._evofw_flag = None
    return transport


async def test_pkt_read_raises_transport_error_when_loop_closed() -> None:
    """_pkt_read raises TransportError (not RuntimeError) when loop is closed.

    This is the fix for issue 802: the paho-mqtt thread receives a message
    after the asyncio loop has been closed, and call_soon_threadsafe would
    raise RuntimeError('Event loop is closed').
    """
    loop = asyncio.get_event_loop()
    transport = _make_read_transport(loop)

    # Simulate a closed loop
    with patch.object(type(loop), "is_closed", return_value=True):
        from ramses_tx import Packet

        pkt = Packet.from_file(
            "2026-07-13T04:40:36",
            "045  I --- 18:130140 32:022222 --:------ 22F2 001 00",
        )
        with pytest.raises(exc.TransportError, match="Event loop is closed"):
            transport._pkt_read(pkt)


async def test_pkt_read_raises_transport_error_on_runtime_error() -> None:
    """_pkt_read catches RuntimeError from call_soon_threadsafe and wraps it.

    Even if is_closed() returns False, the loop may close between the check
    and the call (race condition). The RuntimeError is caught and re-raised
    as TransportError so the MQTT _on_message handler can suppress it.
    """
    loop = asyncio.get_event_loop()
    transport = _make_read_transport(loop)

    from ramses_tx import Packet

    pkt = Packet.from_file(
        "2026-07-13T04:40:36", "045  I --- 18:130140 32:022222 --:------ 22F2 001 00"
    )

    try:
        # is_closed() returns False, but call_soon_threadsafe raises RuntimeError
        with (
            patch.object(type(loop), "is_closed", return_value=False),
            patch.object(
                loop,
                "call_soon_threadsafe",
                side_effect=RuntimeError("Event loop is closed"),
            ),
            pytest.raises(exc.TransportError, match="Event loop is closed"),
        ):
            transport._pkt_read(pkt)
    finally:
        await asyncio.sleep(0.01)


async def test_close_does_not_crash_when_loop_closed() -> None:
    """_close() does not raise when the event loop is already closed."""
    loop = asyncio.get_event_loop()
    transport = _make_read_transport(loop)

    with patch.object(type(loop), "is_closed", return_value=True):
        # Should not raise
        transport._close(None)

    assert transport._closing is True
    # protocol.connection_lost should NOT have been called
    transport._protocol.connection_lost.assert_not_called()


async def test_close_catches_runtime_error_from_call_soon() -> None:
    """_close() catches RuntimeError if loop closes between check and call."""
    loop = asyncio.get_event_loop()
    transport = _make_read_transport(loop)

    with (
        patch.object(type(loop), "is_closed", return_value=False),
        patch.object(
            loop,
            "call_soon_threadsafe",
            side_effect=RuntimeError("Event loop is closed"),
        ),
    ):
        # Should not raise
        transport._close(None)

    assert transport._closing is True


async def test_make_connection_does_not_crash_when_loop_closed() -> None:
    """_make_connection() does not raise when the event loop is closed."""
    loop = asyncio.get_event_loop()
    transport = _make_read_transport(loop)

    with patch.object(type(loop), "is_closed", return_value=True):
        # Should not raise
        transport._make_connection("18:130140")

    # protocol.connection_made should NOT have been called
    transport._protocol.connection_made.assert_not_called()
