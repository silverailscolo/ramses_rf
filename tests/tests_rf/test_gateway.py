# tests/tests_rf/test_gateway.py
"""Tests for the Gateway backward compatibility, deprecation shims, and lifecycle."""

import json
import warnings
from datetime import datetime as dt
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ramses_rf.gateway import Gateway, GatewayConfig
from ramses_tx import I_, RP, RQ
from ramses_tx.config import EngineConfig
from ramses_tx.packet import Packet
from ramses_tx.typing import PktLogConfigT


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
    config = GatewayConfig(
        gateway_timeout=15,
        engine=EngineConfig(enforce_known_list=True),
    )

    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        gwy = Gateway("/dev/null", config=config)

    assert gwy.config.engine.enforce_known_list is True
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
@patch("ramses_rf.lifecycle.set_pkt_logging_config", new_callable=AsyncMock)
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
        engine=EngineConfig(
            packet_log={"flush_interval": 60},
        ),
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

        # Cancel the periodic_flush task that was created but not tracked
        # (because add_task is mocked) to avoid lingering task errors.
        for call in mock_add_task.call_args_list:
            task = call.args[0] if call.args else None
            if task and hasattr(task, "cancel"):
                task.cancel()

    # Clean up the MessageStore housekeeper task that gwy.start() created.
    if gwy._message_store:
        gwy._message_store.stop()


@pytest.mark.asyncio
async def test_gateway_restore_cached_packets_dto() -> None:
    """
    Test that the Gateway seamlessly parses JSON DTOs into Packet objects
    and directly injects them into the protocol.
    """
    config = GatewayConfig(disable_discovery=True)
    gwy = Gateway("/dev/null", config=config)

    with (
        patch("ramses_rf.lifecycle.protocol_factory") as mock_pf,
        patch("ramses_rf.lifecycle.Packet.from_dict") as mock_from_dict,
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
            "2023-01-01T12:00:00.000000Z": {
                "rssi": 45,
                "frame": "I --- 01:145038 --:------ 01:145038 1F09 003 0004B5",
            }
        }

        await gwy._restore_cached_packets(packets, _clear_state=True)

        # Verify from_dict was called with the correct args
        mock_from_dict.assert_called_once_with(
            "2023-01-01T12:00:00.000000Z", packets["2023-01-01T12:00:00.000000Z"]
        )

        # Verify the protocol layer was handed the parsed Packet object directly
        mock_protocol.pkt_received.assert_called_once_with(mock_pkt)


@pytest.mark.asyncio
async def test_gateway_restore_cached_packets_naive_dtm() -> None:
    """Restoring cached packets with naive datetime strings should not crash.

    Regression for the TypeError raised by comparing offset-naive packet dtm
    against the offset-aware cutoff (`dt.now(tz=UTC) - td(hours=1)`).
    """
    config = GatewayConfig(disable_discovery=True)
    gwy = Gateway("/dev/null", config=config)

    with (
        patch("ramses_rf.lifecycle.protocol_factory") as mock_pf,
        patch("ramses_rf.lifecycle.Packet.from_dict") as mock_from_dict,
    ):
        mock_protocol = MagicMock()
        mock_pf.return_value = mock_protocol

        mock_pkt = MagicMock()
        mock_pkt.__class__.__name__ = "Packet"
        mock_pkt.rssi = "045"
        mock_pkt._frame = "I --- 01:145038 --:------ 01:145038 1F09 003 0004B5"
        mock_from_dict.return_value = mock_pkt

        # Naive datetime (no Z, no offset) as written by older cache files
        packets = {
            "2023-01-01T12:00:00.000000": {
                "rssi": 45,
                "frame": "I --- 01:145038 --:------ 01:145038 1F09 003 0004B5",
            }
        }

        await gwy._restore_cached_packets(packets, _clear_state=True)

        mock_protocol.pkt_received.assert_called_once_with(mock_pkt)


@pytest.mark.asyncio
async def test_gateway_legacy_kwargs_deprecation() -> None:
    """Test that legacy kwargs are gracefully mapped to config objects.

    This ensures backward compatibility for ramses_cc while it transitions
    to using the strict GatewayConfig/EngineConfig DTOs.
    """
    with pytest.warns(
        DeprecationWarning,
        match=r"Initializing Gateway with \*\*kwargs.*is deprecated",
    ):
        gwy = Gateway(
            port_name="/dev/null",
            disable_sending=True,  # Transport-level (EngineConfig) kwarg
            disable_discovery=True,  # RF-level (GatewayConfig) kwarg
            invalid_fake_arg="ignore",  # Unsupported kwarg
        )

    # 1. Verify EngineConfig absorbed the transport kwarg
    assert gwy.config.engine.disable_sending is True
    assert gwy.config.engine.port_name == "/dev/null"

    # 2. Verify GatewayConfig absorbed the RF kwarg
    assert gwy.config.disable_discovery is True

    # 3. Verify unsupported arguments were safely ignored
    assert not hasattr(gwy.config, "invalid_fake_arg")
    assert not hasattr(gwy.config.engine, "invalid_fake_arg")


@pytest.mark.asyncio
async def test_gateway_nested_kwargs_unpacking() -> None:
    """Test that nested kwargs from Home Assistant are correctly unpacked.

    This ensures that the recursive adapter can reach into nested dictionaries
    passed by ramses_cc to extract DTO-level configuration variables.
    """
    nested_kwargs = {
        "ramses_rf": {
            "enforce_known_list": True,
            "nested_unsupported": "ignore",
        },
        "packet_log": {
            "packet_log_retention_days": 7,
        },
    }

    with pytest.warns(DeprecationWarning, match="deprecated"):
        gwy = Gateway(port_name="/dev/null", **nested_kwargs)

    # 1. Verify EngineConfig absorbed the nested transport/filtering kwarg
    assert gwy.config.engine.enforce_known_list is True

    # 2. Verify EngineConfig absorbed the nested dictionary kwarg directly
    # Use PktLogConfigT to satisfy Mypy strict comparison check
    assert gwy.config.engine.packet_log == cast(
        PktLogConfigT, {"packet_log_retention_days": 7}
    )

    # 3. Verify nesting logic did not create phantom attributes
    assert not hasattr(gwy.config, "ramses_rf")
    assert not hasattr(gwy.config.engine, "nested_unsupported")


def _mock_addr(addr_id: str) -> MagicMock:
    """Helper to create a mocked Address object."""
    mock = MagicMock()
    mock.id = addr_id
    return mock


@pytest.mark.asyncio
async def test_get_state_parity() -> None:
    """Test get_state returns expected structure and filters verbs."""
    # Arrange
    gwy = Gateway(port_name="/dev/null")
    gwy.message_store = MagicMock()

    msg_i = MagicMock()
    msg_i.verb = I_
    msg_i.dtm = dt(2023, 1, 1, 12, 0, 0)
    msg_i.src.id = "01:123456"
    msg_i.dst.id = "01:123456"
    msg_i._addrs = (
        _mock_addr("01:123456"),
        _mock_addr("--:------"),
        _mock_addr("01:123456"),
    )
    msg_i.code = "1F09"
    msg_i.payload = {"temp": 21.0}
    msg_i._pkt._frame = " I --- 01:123456 --:------ 01:123456 1F09 003 0004B5"

    msg_rp = MagicMock()
    msg_rp.verb = RP
    msg_rp.dtm = dt(2023, 1, 1, 12, 1, 0)
    msg_rp.src.id = "04:111111"
    msg_rp.dst.id = "01:123456"
    msg_rp._addrs = (
        _mock_addr("04:111111"),
        _mock_addr("01:123456"),
        _mock_addr("01:123456"),
    )
    msg_rp.code = "2309"
    msg_rp.payload = {"sync": True}
    msg_rp._pkt._frame = "RP --- 04:111111 01:123456 04:111111 2309 003 0004B5"

    msg_rq = MagicMock()
    msg_rq.verb = RQ
    msg_rq.dtm = dt(2023, 1, 1, 12, 2, 0)
    msg_rq.src.id = "01:123456"
    msg_rq.dst.id = "04:111111"
    msg_rq._addrs = (
        _mock_addr("01:123456"),
        _mock_addr("04:111111"),
        _mock_addr("04:111111"),
    )
    msg_rq.code = "2309"
    msg_rq.payload = {}

    gwy.message_store.state_cache = {
        "h1": msg_i,
        "h2": msg_rp,
        "h3": msg_rq,
    }

    # Act
    schema, state = await gwy.get_state()

    # Assert
    assert len(state) == 2

    dtm_i = msg_i.dtm.isoformat(timespec="microseconds")
    dtm_rp = msg_rp.dtm.isoformat(timespec="microseconds")

    assert dtm_i in state
    assert dtm_rp in state

    assert state[dtm_i] == {
        "verb": I_,
        "src": "01:123456",
        "dst": "01:123456",
        "addr1": "01:123456",
        "addr2": "--:------",
        "addr3": "01:123456",
        "code": "1F09",
        "payload": {"temp": 21.0},
        "frame": " I --- 01:123456 --:------ 01:123456 1F09 003 0004B5",
    }

    assert state[dtm_rp] == {
        "verb": RP,
        "src": "04:111111",
        "dst": "01:123456",
        "addr1": "04:111111",
        "addr2": "01:123456",
        "addr3": "01:123456",
        "code": "2309",
        "payload": {"sync": True},
        "frame": "RP --- 04:111111 01:123456 04:111111 2309 003 0004B5",
    }


@pytest.mark.asyncio
async def test_get_state_frame_key_enables_restore() -> None:
    """Test get_state includes frame key required by Packet.from_dict for warm restart."""
    # Arrange
    gwy = Gateway(port_name="/dev/null")
    gwy.message_store = MagicMock()

    msg = MagicMock()
    msg.verb = I_
    msg.dtm = dt(2023, 1, 1, 12, 0, 0)
    msg.src.id = "01:123456"
    msg.dst.id = "01:123456"
    msg._addrs = (
        _mock_addr("01:123456"),
        _mock_addr("--:------"),
        _mock_addr("01:123456"),
    )
    msg.code = "1F09"
    msg.payload = {"temp": 21.0}
    msg._pkt._frame = " I --- 01:123456 --:------ 01:123456 1F09 003 0004B5"

    gwy.message_store.state_cache = {"h1": msg}

    # Act
    _schema, state = await gwy.get_state()

    dtm_str = msg.dtm.isoformat(timespec="microseconds")
    assert "frame" in state[dtm_str]

    # Assert
    json_roundtrip = json.loads(json.dumps(state))
    pkt = Packet.from_dict(dtm_str, json_roundtrip[dtm_str])
    assert pkt.code == "1F09"
    assert pkt._frame == " I --- 01:123456 --:------ 01:123456 1F09 003 0004B5"
