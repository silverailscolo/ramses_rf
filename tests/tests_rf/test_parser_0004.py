"""Unit tests for the 0004 (zone_name) parser.

The parser must include ``zone_idx`` in the returned dict so that the TCS
``_handle_msg`` routing and the CQRS StateProjector can route 0004 packets
to the correct zone.  Without ``zone_idx``, zone names are never populated
(see https://github.com/ramses-rf/ramses_cc/issues/822).
"""

from unittest.mock import MagicMock

from ramses_rf.messages import Message
from ramses_rf.parsers.heating import parser_0004
from ramses_tx.const import SZ_NAME, SZ_ZONE_IDX


def test_parser_0004_includes_zone_idx() -> None:
    """The parser must return both zone_idx and name."""
    # zone 0B, name "Bedroom 5"
    payload = "0B00426564726F6F6D20350000000000000000000000"
    mock_msg = MagicMock(spec=Message)

    result = parser_0004(payload, mock_msg)

    assert result[SZ_ZONE_IDX] == "0B"
    assert result[SZ_NAME] == "Bedroom 5"


def test_parser_0004_zone_idx_is_first_byte() -> None:
    """zone_idx is the first hex byte of the payload (zz)."""
    for zone_idx in ("00", "01", "05", "0A", "0B"):
        payload = f"{zone_idx}00436F756E67650000000000000000000000000000"
        result = parser_0004(payload, MagicMock(spec=Message))
        assert result[SZ_ZONE_IDX] == zone_idx


def test_parser_0004_null_name_returns_empty_dict() -> None:
    """When the name is all 0x7F, return an empty dict (no zone)."""
    payload = "08007F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F"
    result = parser_0004(payload, MagicMock(spec=Message))
    assert result == {}


def test_parser_0004_all_zero_name() -> None:
    """A name of all zeros is a valid (empty) name, not a null zone."""
    payload = "06000000000000000000000000000000000000000000"
    result = parser_0004(payload, MagicMock(spec=Message))
    assert result[SZ_ZONE_IDX] == "06"
    assert result[SZ_NAME] == ""
