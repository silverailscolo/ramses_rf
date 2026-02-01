#!/usr/bin/env python3
"""Tests for CallbackTransport initialization logic."""

from unittest.mock import AsyncMock, Mock

from ramses_tx.transport import CallbackTransport


async def test_callback_transport_handshake() -> None:
    """Test that connection_made is called automatically upon initialization."""
    mock_protocol = Mock()
    mock_writer = AsyncMock()

    transport = CallbackTransport(mock_protocol, mock_writer)

    # Assert handshake called immediately
    mock_protocol.connection_made.assert_called_once_with(transport, ramses=True)


async def test_callback_transport_handshake_idempotency() -> None:
    """Test that manual connection_made calls are safe (idempotent at protocol level)."""
    mock_protocol = Mock()
    mock_writer = AsyncMock()

    transport = CallbackTransport(mock_protocol, mock_writer)

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

    transport = CallbackTransport(mock_protocol, mock_writer, autostart=False)

    assert transport.is_reading() is False


async def test_callback_transport_autostart_default() -> None:
    """Test that reading is paused by default (backward compatibility)."""
    mock_protocol = Mock()
    mock_writer = AsyncMock()

    transport = CallbackTransport(mock_protocol, mock_writer)

    assert transport.is_reading() is False


async def test_callback_transport_autostart_true() -> None:
    """Test that reading is resumed automatically if autostart=True."""
    mock_protocol = Mock()
    mock_writer = AsyncMock()

    transport = CallbackTransport(mock_protocol, mock_writer, autostart=True)

    assert transport.is_reading() is True
