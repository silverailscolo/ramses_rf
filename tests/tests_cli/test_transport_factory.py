#!/usr/bin/env python3
"""Test the CLI utility's ability to use the transport factory.

This module ensures that the CLI correctly parses connection strings (including MQTT URLs)
and passes them to the Gateway.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asyncclick.testing import CliRunner

# Import async_main so we can run the logic that creates the Gateway
from ramses_cli.client import async_main, cli


@pytest.mark.asyncio
@patch("ramses_cli.client.Gateway")
async def test_cli_uses_transport_factory(mock_gateway: MagicMock) -> None:
    """Check that client.py passes the connection string to Gateway.

    Verifies that when a non-standard port (like an MQTT URL) is passed,
    the Gateway is initialized correctly.
    """
    runner = CliRunner()

    # We use a valid-looking MQTT URL
    mqtt_url = "mqtt://user:pass@localhost:1883"

    # 1. Run the CLI argument parsing
    # standalone_mode=False ensures we get the return value (command, lib_kwargs, kwargs)
    # instead of a system exit code.
    result = await runner.invoke(cli, ["listen", mqtt_url], standalone_mode=False)

    assert result.exit_code == 0, f"CLI parsing failed: {result.exception}"

    # The result.return_value is the tuple returned by the 'listen' command
    command, lib_kwargs, kwargs = result.return_value

    # 2. Configure Mocks for async methods
    # We must make start() and stop() awaitable to prevent "MagicMock can't be used in await" errors
    mock_gateway.return_value.start.side_effect = lambda: asyncio.sleep(0)
    mock_gateway.return_value.stop.side_effect = lambda: asyncio.sleep(0)

    # Explicitly mock wait_for_connection_lost as an async method on the nested engine
    mock_gateway.return_value._engine._protocol.wait_for_connection_lost = AsyncMock()

    # 3. Run the main logic that instantiates Gateway
    # We await the async_main function directly since we are already in an async test
    await async_main(command, lib_kwargs, **kwargs)

    # 4. Assert Gateway was initialized with our URL
    args, kwargs_call = mock_gateway.call_args
    assert args[0] == mqtt_url


@pytest.mark.asyncio
@patch("ramses_cli.client.Gateway")
async def test_cli_serial_backward_compatibility(mock_gateway: MagicMock) -> None:
    """Check that legacy serial ports still work.

    Verifies that standard serial port paths are still accepted and handled
    correctly by the Gateway initialization logic.
    """
    runner = CliRunner()
    serial_port = "/dev/ttyUSB0"

    # 1. Run the CLI argument parsing
    result = await runner.invoke(cli, ["listen", serial_port], standalone_mode=False)

    assert result.exit_code == 0, f"CLI parsing failed: {result.exception}"

    command, lib_kwargs, kwargs = result.return_value

    # 2. Configure Mocks for async methods
    mock_gateway.return_value.start.side_effect = lambda: asyncio.sleep(0)
    mock_gateway.return_value.stop.side_effect = lambda: asyncio.sleep(0)

    # Explicitly mock wait_for_connection_lost as an async method on the nested engine
    mock_gateway.return_value._engine._protocol.wait_for_connection_lost = AsyncMock()

    # 3. Run the main logic
    await async_main(command, lib_kwargs, **kwargs)

    # 4. Assert Gateway was instantiated
    args, kwargs_call = mock_gateway.call_args
    assert args[0] == serial_port
