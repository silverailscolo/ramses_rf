#!/usr/bin/env python3
"""Test the Message class and its exposed attributes, including RSSI."""

from datetime import datetime as dt, timedelta as td
from typing import Any
from unittest.mock import Mock

import pytest

from ramses_tx.application_message import ApplicationMessage
from ramses_tx.message import Message
from ramses_tx.packet import Packet

# Constants for testing frames
FRAME_STR_1 = "045 RQ --- 18:006402 13:049798 --:------ 1FC9 001 00"
FRAME_STR_2 = "095  I --- 01:145038 --:------ 01:145038 1F09 003 0004B5"
FRAME_STR_EMPTY = "045 RP --- 37:153226 29:123160 --:------ 2411 001 00"


@pytest.fixture
def patch_parsers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock out payload validation and parsing for isolated testing.

    :param monkeypatch: The pytest monkeypatch fixture.
    :type monkeypatch: pytest.MonkeyPatch
    :return: None
    """
    monkeypatch.setattr(
        "ramses_tx.message.PayloadDecoderPipeline.decode",
        lambda self, msg: {"mock_key": "mock_val"},
    )


def test_message_attributes(patch_parsers: Any) -> None:
    """Test that the Message class correctly surfaces basic attributes and RSSI.

    :param patch_parsers: The mock fixture for parsers.
    :type patch_parsers: Any
    :return: None
    """
    dtm = dt(2023, 1, 1, 12, 0, 0)
    packet = Packet(dtm, FRAME_STR_1)
    message = Message(packet)

    # Validate physical attributes
    assert message.rssi == "045"
    assert message.dtm == dtm

    # Validate payload properties
    assert message.verb == "RQ"
    assert message.code == "1FC9"
    assert message.len == 1
    assert message.src.id == "18:006402"
    assert message.dst.id == "13:049798"
    assert message._has_payload is False


def test_message_parsing_and_rssi(patch_parsers: Any) -> None:
    """Test that a different frame correctly sets RSSI and parses payload.

    :param patch_parsers: The mock fixture for parsers.
    :type patch_parsers: Any
    :return: None
    """
    dtm = dt.now()
    packet = Packet(dtm, FRAME_STR_2)
    message = Message(packet)

    assert message.rssi == "095"
    assert message.verb == " I"
    assert message.code == "1F09"
    assert message.len == 3
    assert message._has_payload is True

    # Validates that mock payload parsing was successfully invoked and merged
    assert message.payload.get("mock_key") == "mock_val"


def test_message_equality_and_comparison(patch_parsers: Any) -> None:
    """Test the equality and less-than operators of the Message class.

    :param patch_parsers: The mock fixture for parsers.
    :type patch_parsers: Any
    :return: None
    """
    dtm1 = dt(2023, 1, 1, 12, 0, 0)
    dtm2 = dt(2023, 1, 1, 12, 0, 5)

    packet1 = Packet(dtm1, FRAME_STR_1)
    packet2 = Packet(dtm1, FRAME_STR_1)
    packet3 = Packet(dtm2, FRAME_STR_2)

    msg1 = Message(packet1)
    msg2 = Message(packet2)
    msg3 = Message(packet3)

    # Equality is based on address signatures and payload
    assert msg1 == msg2
    assert msg1 != msg3

    # Inequality is chronologically evaluated
    assert msg1 < msg3


def test_message_string_representations(patch_parsers: Any) -> None:
    """Test the string and repr outputs of the Message class.

    :param patch_parsers: The mock fixture for parsers.
    :type patch_parsers: Any
    :return: None
    """
    dtm = dt(2023, 1, 1, 12, 0, 0)
    packet = Packet(dtm, FRAME_STR_1)
    message = Message(packet)

    # __repr__ should fallback identically to the wrapped packet string
    assert repr(message) == str(packet)

    # __str__ formats a pretty table. We check for core identifiers.
    msg_str = str(message)
    assert "18:006402" in msg_str
    assert "13:049798" in msg_str
    assert "RQ" in msg_str


def test_startup_empty_payload_reproduction() -> None:
    """Test that an empty payload bypasses strict regex and parses safely.

    This test runs WITHOUT mock parsers to confirm the heartbeat fallback:
    functionally empty payloads ("00") that fail validation return {}.

    :return: None
    """
    dtm = dt.now()
    packet = Packet(dtm, FRAME_STR_EMPTY)

    # With the fix applied, 2411 RP "00" fails validation but safely returns {}
    message = Message(packet)

    assert message._has_payload is False
    assert message.len == 1
    assert message.payload == {}


def test_message_valid_empty_payload() -> None:
    """Test that a valid empty payload is accurately parsed and NOT dropped.

    Some protocol commands (like 1FC9 ' I') legitimately use a "00" payload
    as actionable data (e.g., the "Confirm" phase of a binding process).
    This ensures they are routed to the parser rather than fallback logic.

    :return: None
    """
    dtm = dt.now()
    # 1FC9 explicitly allows "00" in CODES_SCHEMA. It must successfully parse.
    packet = Packet(dtm, "045  I --- 18:006402 13:049798 --:------ 1FC9 001 00")
    message = Message(packet)

    assert message._has_payload is False
    assert message.payload.get("phase") == "confirm"
    assert "bindings" in message.payload


def test_pure_message_separation(patch_parsers: Any) -> None:
    """Test that the base Message class enforces strict separation of concerns.

    It must NOT possess application-layer properties like `_expired`.

    :param patch_parsers: The mock fixture for parsers.
    :type patch_parsers: Any
    :return: None
    """
    dtm = dt.now()
    packet = Packet(dtm, FRAME_STR_1)
    message = Message(packet)

    with pytest.raises(AttributeError):
        _ = message._expired


def test_application_message_factory(patch_parsers: Any) -> None:
    """Test ApplicationMessage successfully wraps a Message and handles expiration.

    :param patch_parsers: The mock fixture for parsers.
    :type patch_parsers: Any
    :return: None
    """
    now = dt.now()
    packet = Packet(now, FRAME_STR_1)
    base_msg = Message(packet)

    # 1. Test Factory Promotion ensures identical data mapping
    app_msg = ApplicationMessage.from_message(base_msg)

    assert app_msg.src == base_msg.src
    assert app_msg.dst == base_msg.dst
    assert app_msg.code == base_msg.code
    assert app_msg.verb == base_msg.verb

    # 2. Test Context Binding
    mock_gwy = object()
    app_msg.bind_context(mock_gwy)
    assert app_msg._gwy is mock_gwy

    # 3. Test Expiration (Fresh Packet)
    # Should not be expired because (now - dtm) is ~0 seconds
    assert app_msg._expired is False

    # 4. Test Expiration (Old Packet > 7 Days)
    old_dtm = now - td(days=8)
    old_packet = Packet(old_dtm, FRAME_STR_1)
    old_app_msg = ApplicationMessage.from_message(Message(old_packet))

    # We must provide a mock engine so the isolated message has a concept of real time
    mock_engine = Mock()
    mock_engine._dt_now.return_value = now
    old_app_msg.set_gateway(mock_engine)

    # Now the 7-day expiration logic will correctly trigger!
    assert old_app_msg._expired is True
