"""Unit tests for the ramses_cli.inspect payload analysis engine."""

from __future__ import annotations

from typing import Any

import pytest
from asyncclick.testing import CliRunner

from ramses_cli.client import cli
from ramses_cli.inspect import (
    dissect_payload,
    dissect_payload_blocks,
    extract_packet_details,
    format_dissection_output,
    format_dissection_table,
    parse_hex_value,
)
from ramses_tx.const import Code, Verb


def test_parse_hex_value_integers() -> None:
    """Verify numeric conversions for 2-byte and 4-byte words."""
    # Arrange
    hex_word = "1234"

    # Act
    result = parse_hex_value(hex_word)

    # Assert
    assert result["raw"] == "1234"
    assert result["hex"] == "0x1234"
    assert result["dec"] == 4660
    assert result["swapped_hex"] == "0x3412"
    assert result["le_dec"] == 13330
    assert result["signed_dec"] == 4660


def test_parse_hex_value_signed_negative() -> None:
    """Verify signed two's-complement decoding for negative integers."""
    # Arrange
    hex_word = "FFFF"

    # Act
    result = parse_hex_value(hex_word)

    # Assert
    assert result["dec"] == 65535
    assert result["signed_dec"] == -1


def test_parse_hex_value_ascii() -> None:
    """Verify printable ASCII extraction from hex strings."""
    # Arrange
    hex_word = "48656C6C6F"  # "Hello"

    # Act
    result = parse_hex_value(hex_word)

    # Assert
    assert result.get("ascii") == "Hello"


def test_dissect_payload_blocks_with_skip() -> None:
    """Verify slicing payload into word blocks and applying byte offsets."""
    # Arrange
    payload_hex = "000007000000000001000000"

    # Act
    blocks = dissect_payload_blocks(payload_hex, block_size_bytes=4, skip_bytes=3)

    # Assert
    assert "word_1" in blocks
    assert blocks["word_1"]["offset_bytes"] == 3
    assert blocks["word_1"]["raw"] == "00000000"
    assert "word_2" in blocks
    assert blocks["word_2"]["offset_bytes"] == 7
    assert blocks["word_2"]["raw"] == "00010000"


def test_extract_packet_details_full_log_line() -> None:
    """Verify parsing opcode, verb, and payload from a log line."""
    # Arrange
    log_line = (
        "2023-02-18T19:56:43.537735 059  I --- 29:136571 63:262142 --:------ "
        f"{Code._10E0} 038 000001C822030166FEFFFFFFFFFF"
    )

    # Act
    opcode, verb, payload = extract_packet_details(log_line)

    # Assert
    assert opcode == Code._10E0
    assert verb == Verb.I_
    assert payload == "000001C822030166FEFFFFFFFFFF"


def test_extract_packet_details_shorthand() -> None:
    """Verify parsing opcode and verb from shorthand command strings."""
    # Arrange
    shorthand = f"{Verb.RP} {Code._2411} 000007000000000001"

    # Act
    opcode, verb, payload = extract_packet_details(shorthand)

    # Assert
    assert opcode == Code._2411
    assert verb == Verb.RP
    assert payload == "000007000000000001"


def test_extract_packet_details_bare_hex() -> None:
    """Verify bare hex string extraction."""
    # Arrange
    bare = "000007000000000001"

    # Act
    opcode, verb, payload = extract_packet_details(bare)

    # Assert
    assert opcode is None
    assert verb is None
    assert payload == "000007000000000001"


def test_dissect_payload_schema_integration() -> None:
    """Verify schema-decoded payload integration for registered opcodes."""
    # Arrange
    payload_hex = "00000A0010000000050000000000000064000000010001"

    # Act
    dissection = dissect_payload(payload_hex, opcode=Code._2411, verb=Verb.RP)

    # Assert
    assert dissection["opcode"] == Code._2411
    assert dissection["byte_length"] == 23
    assert "schema_decoded" in dissection
    assert "blocks" in dissection
    assert "block_4byte" in dissection["blocks"]


def test_format_dissection_table_renders_rows() -> None:
    """Verify table rendering of individual block dictionaries."""
    # Arrange
    blocks = dissect_payload_blocks("00000700", block_size_bytes=2)

    # Act
    table_str = format_dissection_table(blocks, title="Test Word Breakdown")

    # Assert
    assert "Test Word Breakdown" in table_str
    assert "+00..+01" in table_str
    assert "0000" in table_str


def test_format_dissection_table_empty() -> None:
    """Verify empty block dictionary handling."""
    # Arrange
    blocks: dict[str, dict[str, Any]] = {}

    # Act
    table_str = format_dissection_table(blocks, title="Empty Table")

    # Assert
    assert "No blocks available" in table_str


def test_format_dissection_output_renders_tables() -> None:
    """Verify table formatting produces structured string output."""
    # Arrange
    payload_hex = "0000070000000000010000000000000001000000018A00"
    dissection = dissect_payload(payload_hex, opcode=Code._2411, verb=Verb.RP)

    # Act
    output = format_dissection_output(dissection)

    # Assert
    assert "RAMSES RF Payload Dissection Report" in output
    assert "Word Breakdown" in output
    assert "000007000000000001" in output


@pytest.mark.asyncio
async def test_cli_decode_command_bare_hex() -> None:
    """Verify CLI decode command with bare hex payload argument."""
    # Arrange
    runner = CliRunner()
    payload = "0000070000000000010000000000000001000000018A00"

    # Act
    result = await runner.invoke(cli, ["decode", payload, "--code", str(Code._2411)])

    # Assert
    assert result.exit_code == 0
    assert "RAMSES RF Payload Dissection Report" in result.output
    assert "Word Breakdown" in result.output


@pytest.mark.asyncio
async def test_cli_decode_command_json_output() -> None:
    """Verify CLI decode command JSON output flag."""
    # Arrange
    runner = CliRunner()
    payload = "000007000000"

    # Act
    result = await runner.invoke(cli, ["decode", payload, "--json"])

    # Assert
    assert result.exit_code == 0
    assert '"payload_hex": "000007000000"' in result.output
