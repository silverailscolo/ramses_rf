"""Tests for the Gateway backward compatibility, deprecation shims, and lifecycle."""

import warnings
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ramses_rf.gateway import Gateway, GatewayConfig


@pytest.mark.asyncio
async def test_gateway_positional_port_name() -> None:
    """
    Test that initializing Gateway with a positional port_name succeeds.

    This ensures standard initialization does not trigger deprecation warnings.

    :returns: None
    """
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        Gateway("/dev/null")

    deprecation_warnings = [
        w for w in recorded_warnings if issubclass(w.category, DeprecationWarning)
    ]
    assert len(deprecation_warnings) == 0


@pytest.mark.asyncio
async def test_gateway_keyword_port_name() -> None:
    """
    Test that port_name can be passed as a keyword argument.

    This specifically tests the fix for Issue #501 where the positional-only
    marker ('/') caused a TypeError for legacy integrations like ramses_cc.

    :returns: None
    """
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        Gateway(port_name="/dev/null")

    deprecation_warnings = [
        w for w in recorded_warnings if issubclass(w.category, DeprecationWarning)
    ]
    assert len(deprecation_warnings) == 0


@pytest.mark.asyncio
async def test_gateway_legacy_kwargs_warning() -> None:
    """
    Test that passing undefined kwargs triggers a DeprecationWarning safely.

    This ensures that older versions of downstream libraries passing arbitrary
    kwargs do not crash (TypeError), but instead notify the user to upgrade
    their config.

    :returns: None
    """
    with pytest.warns(DeprecationWarning, match="deprecated"):
        # We pass a nonsensical kwarg to trigger the graceful warning
        Gateway(port_name="/dev/null", legacy_unsupported_flag=True)


@pytest.mark.asyncio
async def test_gateway_with_config() -> None:
    """
    Test initializing the Gateway using the strictly typed GatewayConfig DTO.

    :returns: None
    """
    # Added gateway_timeout=15 to the initialization
    config = GatewayConfig(enforce_known_list=True, gateway_timeout=15)

    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        gwy = Gateway("/dev/null", config=config)

    assert gwy.config.enforce_known_list is True
    # Assert that the gateway config retained the custom timeout
    assert gwy.config.gateway_timeout == 15

    deprecation_warnings = [
        w for w in recorded_warnings if issubclass(w.category, DeprecationWarning)
    ]
    assert len(deprecation_warnings) == 0


@pytest.mark.asyncio
async def test_gateway_stop_closes_listener_in_executor() -> None:
    """
    Test that stopping the Gateway shuts down the packet log listener via
    the executor.

    This ensures that blocking I/O operations (like closing file handlers)
    are offloaded to a background thread, preventing the asyncio event loop
    from blocking.

    :returns: None
    """
    config = GatewayConfig(disable_discovery=True)
    gwy = Gateway("/dev/null", config=config)

    # Mock a packet log listener
    mock_listener = MagicMock()
    gwy._pkt_log_listener = mock_listener

    # Use patch.object to avoid Mypy [method-assign] errors
    with (
        patch.object(gwy._engine, "stop", new_callable=AsyncMock) as mock_stop,
        patch.object(
            gwy._engine._loop, "run_in_executor", new_callable=AsyncMock
        ) as mock_run_in_executor,
    ):
        await gwy.stop()

        # Verify the engine was stopped
        mock_stop.assert_awaited_once()

        # Verify run_in_executor was called to stop the listener
        mock_run_in_executor.assert_awaited_once()

        # Extract arguments passed to run_in_executor to ensure correct targeting
        call_args = mock_run_in_executor.call_args
        assert call_args is not None

        # Arg 0: executor (None=default), Arg 1: function, Arg 2: listener instance
        executor, func, listener_arg = call_args.args
        assert executor is None
        assert listener_arg is mock_listener


@pytest.mark.asyncio
@patch("ramses_rf.gateway.set_pkt_logging_config", new_callable=AsyncMock)
async def test_gateway_start_initiates_periodic_flush(
    mock_set_pkt_logging_config: AsyncMock,
) -> None:
    """
    Test that starting the Gateway sets up the periodic flush task if
    configured.

    :param mock_set_pkt_logging_config: The patched configuration function.
    :returns: None
    """
    mock_listener = MagicMock()
    # set_pkt_logging_config returns a tuple: (logger, listener)
    mock_set_pkt_logging_config.return_value = (None, mock_listener)

    # Configure a flush interval to trigger the task creation
    config = GatewayConfig(
        disable_discovery=True,
        packet_log={"flush_interval": 60},
    )
    gwy = Gateway("/dev/null", config=config)

    # Track tasks added to the gateway and mock the engine start
    # Use a combined context manager to adhere to clean code standards
    with (
        patch.object(gwy._engine, "start", new_callable=AsyncMock),
        patch.object(gwy, "add_task") as mock_add_task,
    ):
        await gwy.start(start_discovery=False)

        # Verify the listener itself was started
        mock_listener.start.assert_called_once()

        # Verify a task was added to the event loop for the periodic flush
        mock_add_task.assert_called()


@pytest.mark.asyncio
async def test_gateway_restore_cached_packets_dto() -> None:
    """
    Test that the Gateway seamlessly parses JSON DTOs into Packet objects
    and directly injects them into the protocol.
    """
    config = GatewayConfig(disable_discovery=True)
    gwy = Gateway("/dev/null", config=config)

    with (
        patch("ramses_rf.gateway.protocol_factory") as mock_pf,
        patch("ramses_rf.gateway.Packet.from_dict") as mock_from_dict,
    ):
        mock_protocol = MagicMock()
        mock_pf.return_value = mock_protocol

        # Mock the packet returned by from_dict to bypass strict frame regex
        mock_pkt = MagicMock()
        mock_pkt.__class__.__name__ = "Packet"
        mock_pkt.rssi = "045"
        mock_pkt._frame = "I --- 01:145038 --:------ 01:145038 1F09 003 0004B5"
        mock_from_dict.return_value = mock_pkt

        # Simulate the new dictionary format provided by ramses_cc
        packets = {
            "2023-01-01T12:00:00.000000": {
                "rssi": 45,
                "frame": "I --- 01:145038 --:------ 01:145038 1F09 003 0004B5",
            }
        }

        await gwy._restore_cached_packets(packets, _clear_state=True)

        # Verify from_dict was called with the correct args
        mock_from_dict.assert_called_once_with(
            "2023-01-01T12:00:00.000000", packets["2023-01-01T12:00:00.000000"]
        )

        # Verify the protocol layer was handed the parsed Packet object directly
        mock_protocol.pkt_received.assert_called_once_with(mock_pkt)
