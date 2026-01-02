#!/usr/bin/env python3
"""Test the CLI utility's ability to use the transport factory."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from ramses_cli.client import cli  # type: ignore[import-untyped]
from ramses_tx import transport_factory


# Mock the Gateway to prevent actual connections/file creation
@patch("ramses_cli.client.Gateway")
def test_cli_uses_transport_factory(mock_gateway: MagicMock) -> None:
    """Check that client.py passes the transport_factory to Gateway."""

    runner = CliRunner()

    # We use a valid-looking MQTT URL
    mqtt_url = "mqtt://user:pass@localhost:1883"

    # Run the 'listen' command which requires a port/url
    runner.invoke(cli, ["listen", mqtt_url])

    # 1. Assert the CLI ran without crashing (exit code might be non-zero due to our mocks,
    # but we check the call args)
    # Note: invoke catches exceptions, so we check mock_gateway usage.

    # 2. Assert Gateway was initialized with our URL
    args, kwargs = mock_gateway.call_args
    assert args[0] == mqtt_url

    # 3. Assert transport_constructor was passed
    assert "transport_constructor" in kwargs

    # 4. Verify it is actually the function we expect
    assert kwargs["transport_constructor"] is transport_factory


@patch("ramses_cli.client.Gateway")
def test_cli_serial_backward_compatibility(mock_gateway: MagicMock) -> None:
    """Check that legacy serial ports still work."""

    runner = CliRunner()
    serial_port = "/dev/ttyUSB0"

    runner.invoke(cli, ["listen", serial_port])

    args, kwargs = mock_gateway.call_args
    assert args[0] == serial_port
    assert "transport_constructor" in kwargs
