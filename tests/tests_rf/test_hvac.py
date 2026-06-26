"""Tests for HVAC payload parsers."""

from unittest.mock import MagicMock

from ramses_rf.messages import Message
from ramses_rf.parsers.hvac import parser_31d9


def test_parser_31d9_orcon_prevents_speed_collision() -> None:
    # Arrange
    # Simulated Orcon 31D9 payload with 12 bytes of space padding (0x20)
    payload = "001A040020202020202020202020202008"
    msg = MagicMock(spec=Message)
    msg.len = 17
    msg._addrs = ["32:123456", "32:123456", "32:123456"]

    # Act
    result = parser_31d9(payload, msg)

    # Assert
    # The exhaust_fan_speed key must be absent to prevent 31DA state collision
    assert "exhaust_fan_speed" not in result
    assert result.get("fan_mode") == "04"
    assert result.get("unknown_16") == "08"
