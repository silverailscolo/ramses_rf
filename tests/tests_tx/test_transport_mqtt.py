#!/usr/bin/env python3
"""Comprehensive unit and resilience tests for the MqttTransport layer.

Exempt from formal docstrings under repository rules.
Applies AAA (Arrange, Act, Assert) pattern strictly.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from paho.mqtt import MQTTException, client as mqtt

from ramses_tx import exceptions as exc
from ramses_tx.const import SZ_ACTIVE_HGI
from ramses_tx.transport import TransportConfig
from ramses_tx.transport.mqtt import MqttTransport, validate_topic_path


@pytest.fixture
def mock_protocol() -> MagicMock:
    """Provide a mock RamsesProtocol."""
    proto = MagicMock()
    proto.pause_writing = MagicMock()
    proto.resume_writing = MagicMock()
    proto.connection_made = MagicMock()
    return proto


@pytest.fixture
def broker_url_specific() -> str:
    """Provide a broker URL with an explicit gateway device ID."""
    return "mqtt://mqtt_user:mqtt_pass@localhost:1883/RAMSES/GATEWAY/01:123456"


@pytest.fixture
def broker_url_wildcard() -> str:
    """Provide a broker URL with a wildcard gateway topic."""
    return "mqtt://mqtt_user:mqtt_pass@localhost:1883/RAMSES/GATEWAY/+"


# ── 1. Topic Path Validation Tests ──────────────────────────────────────────


def test_validate_topic_path_default() -> None:
    # Arrange & Act
    topic = validate_topic_path("")

    # Assert
    assert topic == "RAMSES/GATEWAY/+"


def test_validate_topic_path_valid_specific() -> None:
    # Arrange & Act
    topic = validate_topic_path("/RAMSES/GATEWAY/01:123456")

    # Assert
    assert topic == "RAMSES/GATEWAY/01:123456"


def test_validate_topic_path_invalid_prefix() -> None:
    # Arrange, Act & Assert
    with pytest.raises(exc.TransportMqttError, match="Invalid topic path"):
        validate_topic_path("INVALID/PREFIX/01:123456")


def test_validate_topic_path_invalid_depth() -> None:
    # Arrange, Act & Assert
    with pytest.raises(exc.TransportMqttError, match="Invalid topic path"):
        validate_topic_path("RAMSES/GATEWAY/EXTRA/DEPTH")


# ── 2. Connection Lifecycle & Reconnection Backoff Tests ────────────────────


@pytest.mark.asyncio
async def test_attempt_connection_connect_failure_triggers_reconnect(
    mock_protocol: MagicMock, broker_url_specific: str
) -> None:
    # Arrange
    with (
        patch(
            "paho.mqtt.client.Client.connect_async",
            side_effect=OSError("Network unreachable"),
        ),
        patch("paho.mqtt.client.Client.loop_start"),
    ):
        # Act
        transport = MqttTransport(
            broker_url_specific,
            mock_protocol,
            config=TransportConfig(),
        )

        # Assert
        assert transport._connecting is False
        assert transport._reconnect_task is not None

        # Clean up
        transport.close()


@pytest.mark.asyncio
async def test_attempt_connection_already_connecting_early_returns(
    mock_protocol: MagicMock, broker_url_specific: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async") as mock_connect,
        patch("paho.mqtt.client.Client.loop_start"),
    ):
        transport = MqttTransport(
            broker_url_specific,
            mock_protocol,
            config=TransportConfig(),
        )
        mock_connect.reset_mock()
        transport._connecting = True

        # Act
        transport._attempt_connection()

        # Assert
        mock_connect.assert_not_called()

        # Clean up
        transport.close()


@pytest.mark.asyncio
async def test_reconnect_after_delay_executes_and_backs_off(
    mock_protocol: MagicMock, broker_url_specific: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
    ):
        transport = MqttTransport(
            broker_url_specific,
            mock_protocol,
            config=TransportConfig(),
        )
        transport._current_reconnect_interval = 2.0
        initial_interval = transport._current_reconnect_interval

        with (
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch.object(transport, "_attempt_connection") as mock_attempt,
        ):
            # Act
            await transport._reconnect_after_delay()

            # Assert
            mock_sleep.assert_called_once_with(initial_interval)
            assert transport._current_reconnect_interval == 2.0 * 1.5
            mock_attempt.assert_called_once()

        # Clean up
        transport.close()


@pytest.mark.asyncio
async def test_reconnect_task_cancelled_silently(
    mock_protocol: MagicMock, broker_url_specific: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
    ):
        transport = MqttTransport(
            broker_url_specific,
            mock_protocol,
            config=TransportConfig(),
        )

        with patch("asyncio.sleep", side_effect=asyncio.CancelledError):
            # Act & Assert (should not raise)
            await transport._reconnect_after_delay()
            assert transport._reconnect_task is None

        # Clean up
        transport.close()


# ── 3. Connect & Disconnect Callbacks Tests ─────────────────────────────────


@pytest.mark.asyncio
async def test_on_connect_failure_code_schedules_reconnect(
    mock_protocol: MagicMock, broker_url_specific: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
    ):
        transport = MqttTransport(
            broker_url_specific,
            mock_protocol,
            config=TransportConfig(),
        )
        mock_reason = MagicMock()
        mock_reason.is_failure = True
        mock_reason.getName.return_value = "Bad username or password"

        with patch.object(transport, "_schedule_reconnect") as mock_reconnect:
            # Act
            transport._on_connect(
                transport.client, None, {}, mock_reason, None
            )

            # Assert
            assert transport._connecting is False
            mock_reconnect.assert_called_once()

        # Clean up
        transport.close()


@pytest.mark.asyncio
async def test_on_connect_success_wildcard_topic(
    mock_protocol: MagicMock, broker_url_wildcard: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
        patch("paho.mqtt.client.Client.subscribe") as mock_sub,
    ):
        transport = MqttTransport(
            broker_url_wildcard,
            mock_protocol,
            config=TransportConfig(),
        )
        mock_reason = MagicMock()
        mock_reason.is_failure = False
        mock_reason.getName.return_value = "Success"

        # Act
        transport._on_connect(transport.client, None, {}, mock_reason, None)

        # Assert
        assert transport._connected is True
        assert transport._connection_established is True
        mock_sub.assert_any_call("RAMSES/GATEWAY/+")
        mock_sub.assert_any_call("RAMSES/GATEWAY/+/rx", qos=0)

        # Clean up
        transport.close()


@pytest.mark.asyncio
async def test_on_connect_fail_sets_disconnected_state(
    mock_protocol: MagicMock, broker_url_specific: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
    ):
        transport = MqttTransport(
            broker_url_specific,
            mock_protocol,
            config=TransportConfig(),
        )
        transport._connected = True

        with patch.object(transport, "_schedule_reconnect") as mock_reconnect:
            # Act
            transport._on_connect_fail(transport.client, None)

            # Assert
            assert transport._connected is False
            assert transport._connecting is False
            mock_reconnect.assert_called_once()

        # Clean up
        transport.close()


@pytest.mark.asyncio
async def test_on_disconnect_pauses_writing_and_schedules_reconnect(
    mock_protocol: MagicMock, broker_url_specific: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
    ):
        transport = MqttTransport(
            broker_url_specific,
            mock_protocol,
            config=TransportConfig(),
        )
        transport._connected = True
        transport._topic_sub = "RAMSES/GATEWAY/01:123456/rx"
        mock_reason = MagicMock()
        mock_reason.getName.return_value = "Keepalive timeout"

        with (
            patch.object(
                transport._loop, "call_soon_threadsafe"
            ) as mock_call_soon,
            patch.object(transport, "_schedule_reconnect") as mock_reconnect,
        ):
            # Act
            transport._on_disconnect(transport.client, None, mock_reason)

            # Assert
            assert transport._connected is False
            mock_call_soon.assert_called_once_with(mock_protocol.pause_writing)
            mock_reconnect.assert_called_once()

        # Clean up
        transport.close()


# ── 4. Online / Offline Message & State Transition Tests ───────────────────


@pytest.mark.asyncio
async def test_create_connection_deferred_rx_subscription(
    mock_protocol: MagicMock, broker_url_wildcard: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
        patch("paho.mqtt.client.Client.subscribe") as mock_sub,
        patch("paho.mqtt.client.Client.unsubscribe") as mock_unsub,
    ):
        transport = MqttTransport(
            broker_url_wildcard,
            mock_protocol,
            config=TransportConfig(),
        )
        transport._connected = True
        transport._data_wildcard_topic = "RAMSES/GATEWAY/+/rx"

        mock_msg = MagicMock()
        mock_msg.payload = b"online"
        mock_msg.topic = "RAMSES/GATEWAY/01:123456"

        # Act
        transport._create_connection(mock_msg)

        # Assert
        assert transport.get_extra_info(SZ_ACTIVE_HGI) == "01:123456"
        assert transport._topic_pub == "RAMSES/GATEWAY/01:123456/tx"
        assert transport._topic_sub == "RAMSES/GATEWAY/01:123456/rx"
        mock_sub.assert_called_with("RAMSES/GATEWAY/01:123456/rx", qos=0)
        mock_unsub.assert_called_with("RAMSES/GATEWAY/+/rx")
        assert transport._data_wildcard_topic == ""

        # Clean up
        transport.close()


@pytest.mark.asyncio
async def test_create_connection_resumes_writing_when_sub_already_present(
    mock_protocol: MagicMock, broker_url_specific: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
    ):
        transport = MqttTransport(
            broker_url_specific,
            mock_protocol,
            config=TransportConfig(),
        )
        transport._connected = True
        transport._topic_sub = "RAMSES/GATEWAY/01:123456/rx"

        mock_msg = MagicMock()
        mock_msg.payload = b"online"
        mock_msg.topic = "RAMSES/GATEWAY/01:123456"

        with patch.object(
            transport._loop, "call_soon_threadsafe"
        ) as mock_call_soon:
            # Act
            transport._create_connection(mock_msg)

            # Assert
            mock_call_soon.assert_called_once_with(
                mock_protocol.resume_writing
            )

        # Clean up
        transport.close()


@pytest.mark.asyncio
async def test_on_message_lwt_offline_pauses_writing(
    mock_protocol: MagicMock, broker_url_specific: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
    ):
        transport = MqttTransport(
            broker_url_specific,
            mock_protocol,
            config=TransportConfig(),
        )
        transport._topic_sub = "RAMSES/GATEWAY/01:123456/rx"

        mock_msg = MagicMock()
        mock_msg.topic = "RAMSES/GATEWAY/01:123456"
        mock_msg.payload = b"offline"

        with patch.object(
            transport._loop, "call_soon_threadsafe"
        ) as mock_call_soon:
            # Act
            transport._on_message(transport.client, None, mock_msg)

            # Assert
            mock_call_soon.assert_called_once_with(mock_protocol.pause_writing)

        # Clean up
        transport.close()


@pytest.mark.asyncio
async def test_on_message_closing_drops_inbound_messages(
    mock_protocol: MagicMock, broker_url_specific: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
    ):
        transport = MqttTransport(
            broker_url_specific,
            mock_protocol,
            config=TransportConfig(),
        )
        transport._closing = True

        mock_msg = MagicMock()
        mock_msg.topic = "RAMSES/GATEWAY/01:123456/rx"
        mock_msg.payload = b'{"ts": "2026-08-14T10:00:00", "msg": "..."}'

        with patch.object(
            transport._loop, "call_soon_threadsafe"
        ) as mock_call_soon:
            # Act
            transport._on_message(transport.client, None, mock_msg)

            # Assert
            mock_call_soon.assert_not_called()

        # Clean up
        transport.close()


# ── 5. Frame Writing & Rate Limiting Tests ──────────────────────────────────


@pytest.mark.asyncio
async def test_write_frame_when_not_connected_raises_state_error(
    mock_protocol: MagicMock, broker_url_specific: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
    ):
        transport = MqttTransport(
            broker_url_specific,
            mock_protocol,
            config=TransportConfig(),
        )
        transport._connected = False

        # Act & Assert
        with pytest.raises(exc.TransportStateError):
            await transport.write_frame("--- RQ --- 18:000730 01:123456")

        # Clean up
        transport.close()


@pytest.mark.asyncio
async def test_write_frame_duty_cycle_token_consumption_and_publish(
    mock_protocol: MagicMock, broker_url_specific: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
        patch("paho.mqtt.client.Client.publish") as mock_pub,
    ):
        mock_info = MagicMock()
        mock_info.rc = mqtt.MQTT_ERR_SUCCESS
        mock_pub.return_value = mock_info

        transport = MqttTransport(
            broker_url_specific,
            mock_protocol,
            config=TransportConfig(),
        )
        transport._connected = True
        transport._topic_pub = "RAMSES/GATEWAY/01:123456/tx"
        frame_str = "... RQ ... 18:000730 01:123456 --:------ 313F 001 00"

        # Act
        await transport.write_frame(frame_str)

        # Assert
        mock_pub.assert_called_once()
        args, kwargs = mock_pub.call_args
        assert args[0] == "RAMSES/GATEWAY/01:123456/tx"
        assert frame_str in kwargs["payload"]

        # Clean up
        transport.close()


@pytest.mark.asyncio
async def test_write_frame_rate_limit_token_exhaustion_discards(
    mock_protocol: MagicMock, broker_url_specific: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
        patch("paho.mqtt.client.Client.publish") as mock_pub,
    ):
        transport = MqttTransport(
            broker_url_specific,
            mock_protocol,
            config=TransportConfig(),
        )
        transport._connected = True
        transport._topic_pub = "RAMSES/GATEWAY/01:123456/tx"
        transport._num_tokens = -5.0

        # Act
        await transport.write_frame("... RQ ... 18:000730 01:123456")

        # Assert
        mock_pub.assert_not_called()

        # Clean up
        transport.close()


@pytest.mark.asyncio
async def test_publish_connection_lost_triggers_reconnect(
    mock_protocol: MagicMock, broker_url_specific: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
        patch("paho.mqtt.client.Client.publish") as mock_pub,
    ):
        mock_info = MagicMock()
        mock_info.rc = mqtt.MQTT_ERR_CONN_LOST
        mock_pub.return_value = mock_info

        transport = MqttTransport(
            broker_url_specific,
            mock_protocol,
            config=TransportConfig(),
        )
        transport._connected = True
        transport._topic_pub = "RAMSES/GATEWAY/01:123456/tx"

        with patch.object(transport, "_schedule_reconnect") as mock_reconnect:
            # Act
            transport._publish('{"msg": "test"}')

            # Assert
            assert transport._connected is False
            mock_reconnect.assert_called_once()

        # Clean up
        transport.close()


@pytest.mark.asyncio
async def test_publish_without_topic_pub_warns_and_returns(
    mock_protocol: MagicMock, broker_url_wildcard: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
        patch("paho.mqtt.client.Client.publish") as mock_pub,
    ):
        transport = MqttTransport(
            broker_url_wildcard,
            mock_protocol,
            config=TransportConfig(),
        )
        transport._connected = True
        transport._topic_pub = ""

        # Act
        transport._publish('{"msg": "test"}')

        # Assert
        mock_pub.assert_not_called()

        # Clean up
        transport.close()


@pytest.mark.asyncio
async def test_write_bytes_raises_not_implemented(
    mock_protocol: MagicMock, broker_url_specific: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
    ):
        transport = MqttTransport(
            broker_url_specific,
            mock_protocol,
            config=TransportConfig(),
        )

        # Act & Assert
        with pytest.raises(exc.TransportError, match="use write_frame"):
            transport.write(b"--- RQ --- 18:000730 01:123456\r\n")

        # Clean up
        transport.close()


# ── 6. Inbound Message Processing & Error Handling Tests ───────────────────


@pytest.mark.asyncio
async def test_on_message_infers_gateway_from_rx_topic(
    mock_protocol: MagicMock, broker_url_wildcard: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
        patch("paho.mqtt.client.Client.subscribe") as mock_sub,
        patch("paho.mqtt.client.Client.unsubscribe") as mock_unsub,
    ):
        transport = MqttTransport(
            broker_url_wildcard,
            mock_protocol,
            config=TransportConfig(),
        )
        transport._data_wildcard_topic = "RAMSES/GATEWAY/+/rx"

        mock_msg = MagicMock()
        mock_msg.topic = "RAMSES/GATEWAY/01:123456/rx"
        mock_msg.payload = b'{"ts": "2026-08-14T10:00:00+00:00", "msg": "059 RP --- 01:123456 04:017982 --:------ 313F 009 00FC2300C4150C07E9"}'

        # Act
        transport._on_message(transport.client, None, mock_msg)

        # Assert
        assert transport._topic_sub == "RAMSES/GATEWAY/01:123456/rx"
        assert transport._topic_pub == "RAMSES/GATEWAY/01:123456/tx"
        mock_sub.assert_called_with("RAMSES/GATEWAY/01:123456/rx", qos=0)
        mock_unsub.assert_called_with("RAMSES/GATEWAY/+/rx")

        # Clean up
        transport.close()


@pytest.mark.asyncio
async def test_on_message_invalid_json_payload_ignored(
    mock_protocol: MagicMock, broker_url_specific: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
    ):
        transport = MqttTransport(
            broker_url_specific,
            mock_protocol,
            config=TransportConfig(),
        )
        transport._connection_established = True

        mock_msg = MagicMock()
        mock_msg.topic = "RAMSES/GATEWAY/01:123456/rx"
        mock_msg.payload = b"NOT_JSON_DATA"

        with patch.object(
            transport._loop, "call_soon_threadsafe"
        ) as mock_call_soon:
            # Act
            transport._on_message(transport.client, None, mock_msg)

            # Assert
            mock_call_soon.assert_not_called()

        # Clean up
        transport.close()


@pytest.mark.asyncio
async def test_write_frame_publish_exception_triggers_reconnect(
    mock_protocol: MagicMock, broker_url_specific: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
        patch(
            "paho.mqtt.client.Client.publish",
            side_effect=MQTTException("Publish error"),
        ),
    ):
        transport = MqttTransport(
            broker_url_specific,
            mock_protocol,
            config=TransportConfig(),
        )
        transport._connected = True
        transport._topic_pub = "RAMSES/GATEWAY/01:123456/tx"

        with patch.object(transport, "_schedule_reconnect") as mock_reconnect:
            # Act
            await transport._write_frame("... RQ ...")

            # Assert
            assert transport._connected is False
            mock_reconnect.assert_called_once()

        # Clean up
        transport.close()


@pytest.mark.asyncio
async def test_create_connection_when_disconnected_establishes(
    mock_protocol: MagicMock, broker_url_wildcard: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
        patch("paho.mqtt.client.Client.subscribe") as mock_sub,
    ):
        transport = MqttTransport(
            broker_url_wildcard,
            mock_protocol,
            config=TransportConfig(),
        )
        transport._connected = False
        transport._connection_established = False

        mock_msg = MagicMock()
        mock_msg.payload = b"online"
        mock_msg.topic = "RAMSES/GATEWAY/01:123456"

        with patch.object(
            transport._loop, "call_soon_threadsafe"
        ) as mock_call_soon:
            # Act
            transport._create_connection(mock_msg)

            # Assert
            assert transport._connected is True
            assert transport._connection_established is True
            mock_sub.assert_called_with("RAMSES/GATEWAY/01:123456/rx", qos=0)
            mock_call_soon.assert_called_once_with(
                transport._make_connection, "01:123456"
            )

        # Clean up
        transport.close()


@pytest.mark.asyncio
async def test_establish_connection_idempotent_updates_hgi(
    mock_protocol: MagicMock, broker_url_specific: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
    ):
        transport = MqttTransport(
            broker_url_specific,
            mock_protocol,
            config=TransportConfig(),
        )
        transport._connection_established = True

        # Act
        transport._establish_connection("01:654321")

        # Assert
        assert transport.get_extra_info(SZ_ACTIVE_HGI) == "01:654321"

        # Clean up
        transport.close()


@pytest.mark.asyncio
async def test_on_connect_success_specific_topic_presets_pub_sub(
    mock_protocol: MagicMock, broker_url_specific: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
        patch("paho.mqtt.client.Client.subscribe") as mock_sub,
    ):
        transport = MqttTransport(
            broker_url_specific,
            mock_protocol,
            config=TransportConfig(),
        )
        mock_reason = MagicMock()
        mock_reason.is_failure = False
        mock_reason.getName.return_value = "Success"

        # Act
        transport._on_connect(transport.client, None, {}, mock_reason, None)
        await asyncio.sleep(0)

        # Assert
        assert transport._connected is True
        assert transport._topic_pub == "RAMSES/GATEWAY/01:123456/tx"
        assert transport._topic_sub == "RAMSES/GATEWAY/01:123456/rx"
        assert transport.get_extra_info(SZ_ACTIVE_HGI) == "01:123456"
        mock_sub.assert_any_call("RAMSES/GATEWAY/01:123456/rx", qos=0)

        # Clean up
        transport.close()


@pytest.mark.asyncio
async def test_write_frame_negative_tokens_triggers_throttle_sleep(
    mock_protocol: MagicMock, broker_url_specific: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
        patch("paho.mqtt.client.Client.publish") as mock_pub,
    ):
        mock_info = MagicMock()
        mock_info.rc = mqtt.MQTT_ERR_SUCCESS
        mock_pub.return_value = mock_info

        transport = MqttTransport(
            broker_url_specific,
            mock_protocol,
            config=TransportConfig(),
        )
        transport._connected = True
        transport._topic_pub = "RAMSES/GATEWAY/01:123456/tx"
        # Set tokens between -(1 - rate) and 0 so it throttles without discarding
        transport._num_tokens = 0.5  # after consuming 1.0 it will be -0.5

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            # Act
            await transport.write_frame("... RQ ... 18:000730 01:123456")

            # Assert
            mock_sleep.assert_called_once()
            mock_pub.assert_called_once()

        # Clean up
        transport.close()


@pytest.mark.asyncio
async def test_publish_when_disconnected_raises_state_error(
    mock_protocol: MagicMock, broker_url_specific: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
    ):
        transport = MqttTransport(
            broker_url_specific,
            mock_protocol,
            config=TransportConfig(),
        )
        transport._connected = False

        # Act & Assert
        with pytest.raises(
            exc.TransportStateError, match="MQTT not connected"
        ):
            transport._publish('{"msg": "test"}')

        # Clean up
        transport.close()


# ── 7. Transport Cleanup & Close Tests ──────────────────────────────────────


@pytest.mark.asyncio
async def test_close_disconnects_client_and_cancels_reconnect(
    mock_protocol: MagicMock, broker_url_specific: str
) -> None:
    # Arrange
    with (
        patch("paho.mqtt.client.Client.connect_async"),
        patch("paho.mqtt.client.Client.loop_start"),
        patch("paho.mqtt.client.Client.disconnect") as mock_disc,
        patch("paho.mqtt.client.Client.loop_stop") as mock_loop_stop,
    ):
        transport = MqttTransport(
            broker_url_specific,
            mock_protocol,
            config=TransportConfig(),
        )
        mock_task = MagicMock()
        transport._reconnect_task = mock_task

        # Act
        transport.close()

        # Assert
        assert transport._closing is True
        mock_task.cancel.assert_called_once()
        mock_disc.assert_called_once()
        mock_loop_stop.assert_called_once()
