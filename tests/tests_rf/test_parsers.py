import asyncio
from datetime import datetime as dt
from unittest.mock import MagicMock

import pytest
import serial

from ramses_rf import Gateway
from ramses_rf.config import GatewayConfig
from ramses_rf.const import I_, SZ_PHASE, W_, Code
from ramses_rf.messages import Message
from ramses_rf.models import TopologyChangedEvent
from ramses_rf.parsers.heating import parser_0004, parser_12c0
from ramses_rf.parsers.system import parser_1fc9
from ramses_rf.pipeline.topology_builder import TopologyBuilder
from ramses_tx import Packet
from ramses_tx.address import Address
from ramses_tx.config import EngineConfig
from ramses_tx.const import SZ_BINDINGS, SZ_NAME, SZ_TEMPERATURE, SZ_ZONE_IDX
from ramses_tx.schemas import SZ_INBOUND
from tests_rf.virtual_rf import VirtualRf

# --- Parser 0004 Tests ---


def test_parser_0004_includes_zone_idx() -> None:
    """Verify that parser_0004 returns both zone_idx and name."""
    # Arrange
    # zone 0B, name "Bedroom 5"
    payload = "0B00426564726F6F6D20350000000000000000000000"
    mock_msg = MagicMock(spec=Message)

    # Act
    result = parser_0004(payload, mock_msg)

    # Assert
    assert result[SZ_ZONE_IDX] == "0B"
    assert result[SZ_NAME] == "Bedroom 5"


def test_parser_0004_zone_idx_is_first_byte() -> None:
    """Verify zone_idx extraction across multiple zone indices."""
    # Arrange & Act & Assert
    for zone_idx in ("00", "01", "05", "0A", "0B"):
        payload = f"{zone_idx}00436F756E67650000000000000000000000000000"
        result = parser_0004(payload, MagicMock(spec=Message))
        assert result[SZ_ZONE_IDX] == zone_idx


def test_parser_0004_null_name_returns_empty_dict() -> None:
    """Verify empty dict returned when name payload is null sentinel."""
    # Arrange
    payload = "08007F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F"

    # Act
    result = parser_0004(payload, MagicMock(spec=Message))

    # Assert
    assert result == {}


def test_parser_0004_all_zero_name() -> None:
    """Verify empty string returned when name payload is all zeros."""
    # Arrange
    payload = "06000000000000000000000000000000000000000000"

    # Act
    result = parser_0004(payload, MagicMock(spec=Message))

    # Assert
    assert result[SZ_ZONE_IDX] == "06"
    assert result[SZ_NAME] == ""


# --- Parser 12C0 Tests ---


def test_parser_12c0_parses_celsius_correctly() -> None:
    """Verify parsing of temperature in Celsius."""
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
    """Verify temperature in Fahrenheit normalises to Celsius."""
    # Arrange
    # Prefix: 00 | Temp: 44 (68 dec, 68F) | Units: 00 (Fahrenheit)
    payload = "004400"
    mock_msg = MagicMock(spec=Message)

    # Act
    result = parser_12c0(payload, mock_msg)

    # Assert
    assert result[SZ_TEMPERATURE] == 20.0
    assert result.get("units") == "Celsius"


def test_parser_12c0_handles_null_temperature() -> None:
    """Verify null temperature sentinel returns None."""
    # Arrange
    # Prefix: 00 | Temp: 80 (Null sentinel) | Units: 01 (Celsius)
    payload = "008001"
    mock_msg = MagicMock(spec=Message)

    # Act
    result = parser_12c0(payload, mock_msg)

    # Assert
    assert result[SZ_TEMPERATURE] is None


# --- Parser 1FC9 Tests ---


def test_1fc9_binary_parsing_parity_with_legacy_parser() -> None:
    """Verify binary parser parity with legacy string-slicing parser."""
    # Arrange
    test_cases = [
        (
            "FC0008053376FC3150053376FB3150053376FC1FC9053376",
            I_,
            "01:078710",
            "01:078710",
            "offer",
        ),
        (
            "003EF0290693",
            W_,
            "10:067219",
            "01:078710",
            "accept",
        ),
        (
            "00FFFF053376",
            I_,
            "01:078710",
            "10:067219",
            "confirm",
        ),
        (
            "FA000806368EFC3B0006368EFA1FC906368E",
            I_,
            "01:145038",
            "63:262142",
            "offer",
        ),
    ]

    for payload_hex, verb, src_id, dst_id, expected_phase in test_cases:
        # Act 1: Legacy parser execution
        mock_msg = MagicMock(spec=Message)
        mock_msg.verb = verb
        mock_msg.src = Address(src_id)
        mock_msg.dst = Address(dst_id)
        mock_msg.len = len(payload_hex) // 2

        legacy_result = parser_1fc9(payload_hex, mock_msg)

        # Act 2: New Binary Parser execution in TopologyBuilder
        events: list[TopologyChangedEvent] = []
        builder = TopologyBuilder(emit_event_cb=events.append, enable_eavesdrop=True)

        mock_pkt = MagicMock()
        mock_pkt.payload = payload_hex

        mock_header = MagicMock()
        mock_header.code = Code._1FC9
        mock_header.verb = verb

        topology_msg = MagicMock(spec=Message)
        topology_msg.header = mock_header
        topology_msg.src = Address(src_id)
        topology_msg.dst = Address(dst_id)
        topology_msg._dto = mock_pkt

        builder._evaluate_rf_bind_rules(topology_msg)

        # Assert
        assert legacy_result[SZ_PHASE] == expected_phase

        legacy_bindings = legacy_result[SZ_BINDINGS]
        bind_events = [e for e in events if e.action.name == "BIND_DEVICE"]

        assert len(bind_events) == len(legacy_bindings)

        for legacy_b, event in zip(legacy_bindings, bind_events, strict=True):
            exp_domain, exp_opcode, exp_dev_id = legacy_b
            assert event.metadata["domain_id"] == exp_domain
            assert event.metadata["opcode"] == exp_opcode
            assert event.metadata["phase"] == expected_phase
            assert event.child_id == exp_dev_id or event.parent_id == exp_dev_id


# --- Inbound Regex Parser Tests ---

RULES_INBOUND = {
    "63:262143": "04:262143",
    "(W.*) 1FC9 (...) 21": "\\g<1> 1FC9 \\g<2> 00",
    "--:------ --:------ 12:215819": "01:215819 --:------ 01:215819",
    "000C 006 02(04|08)00FFFFFF": "000C 006 02\\g<1>0013FFFF",
}

TESTS_INBOUND = {
    " I --- --:------ --:------ 12:215819 0009 003 0000FF": "000  I --- 01:215819 --:------ 01:215819 0009 003 0000FF",
    " I --- 63:262143 --:------ 63:262143 30C9 003 000713": "000  I --- 04:262143 --:------ 04:262143 30C9 003 000713",
}


@pytest.mark.xdist_group(name="virt_serial")
async def test_regex_inbound_parsing() -> None:
    """Check the inbound regex transformation filters work as expected."""
    rf = VirtualRf(2)

    gwy_0 = Gateway(
        rf.ports[0],
        config=GatewayConfig(
            disable_discovery=True,
            engine=EngineConfig(
                disable_qos=False,
                enforce_known_list=False,
                use_regex={SZ_INBOUND: RULES_INBOUND},
            ),
        ),
    )
    ser_1 = serial.Serial(rf.ports[1])

    try:
        await gwy_0.start()
        assert gwy_0._engine._protocol._transport

        for cmd, pkt in TESTS_INBOUND.items():
            ser_1.write(bytes(cmd.encode("ascii")) + b"\r\n")

            expected = Packet.from_port(dt.now(), pkt)
            for _ in range(100):
                await asyncio.sleep(0.001)
                if gwy_0._this_msg and gwy_0._this_msg.raw_frame == expected._frame:
                    break
            assert gwy_0._this_msg and gwy_0._this_msg.raw_frame == expected._frame

    finally:
        await gwy_0.stop()
        await rf.stop()
