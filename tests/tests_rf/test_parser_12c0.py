from unittest.mock import MagicMock

from ramses_rf.messages import Message
from ramses_rf.parsers.heating import parser_12c0
from ramses_tx.const import SZ_TEMPERATURE


def test_parser_12c0_parses_celsius_correctly() -> None:
    # Arrange
    # Prefix: 00 | Temp: 28 (40 dec, 20.0C) | Units: 01 (Celsius)
    payload = "002801"
    mock_msg = MagicMock(spec=Message)

    # Act
    result = parser_12c0(payload, mock_msg)

    # Assert
    assert result[SZ_TEMPERATURE] == 20.0
    assert result.get("units") == "Celsius"


def test_parser_12c0_normalises_fahrenheit_to_celsius() -> None:
    # Arrange
    # Prefix: 00 | Temp: 44 (68 dec, 68F) | Units: 00 (Fahrenheit)
    payload = "004400"
    mock_msg = MagicMock(spec=Message)

    # Act
    result = parser_12c0(payload, mock_msg)

    # Assert
    # 68F should be converted to 20.0C by the parser
    assert result[SZ_TEMPERATURE] == 20.0
    assert result.get("units") == "Celsius"


def test_parser_12c0_handles_null_temperature() -> None:
    # Arrange
    # Prefix: 00 | Temp: 80 (Null sentinel) | Units: 01 (Celsius)
    payload = "008001"
    mock_msg = MagicMock(spec=Message)

    # Act
    result = parser_12c0(payload, mock_msg)

    # Assert
    assert result[SZ_TEMPERATURE] is None
