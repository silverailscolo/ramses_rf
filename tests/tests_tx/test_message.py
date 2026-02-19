#!/usr/bin/env python3
"""Test the Message class and its exposed attributes, including RSSI."""

from datetime import datetime as dt

import pytest

from ramses_tx.message import Message
from ramses_tx.packet import Packet

# Constants for testing frames
FRAME_STR_1 = "045 RQ --- 18:006402 13:049798 --:------ 1FC9 001 00"
FRAME_STR_2 = "095  I --- 01:145038 --:------ 01:145038 1F09 003 0004B5"


@pytest.fixture(autouse=True)
def patch_parsers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock out payload validation and parsing for isolated testing.

    :param monkeypatch: The pytest monkeypatch fixture.
    :type monkeypatch: pytest.MonkeyPatch
    :return: None
    """
    monkeypatch.setattr(
        "ramses_tx.message._check_msg_payload", lambda msg, payload: None
    )
    monkeypatch.setattr(
        "ramses_tx.message.parse_payload", lambda msg: {"mock_key": "mock_val"}
    )


def test_message_attributes() -> None:
    """Test that the Message class correctly surfaces basic attributes and RSSI.

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


def test_message_parsing_and_rssi() -> None:
    """Test that a different frame correctly sets RSSI and parses payload.

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


def test_message_equality_and_comparison() -> None:
    """Test the equality and less-than operators of the Message class.

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


def test_message_string_representations() -> None:
    """Test the string and repr outputs of the Message class.

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
