#!/usr/bin/env python3
"""RAMSES RF - CLI Payload and Packet Inspector.

This module provides utilities to dissect arbitrary hex payloads and RAMSES
packets into multi-representation word blocks (1, 2, 4, 6, and 8 bytes) with
endianness, signed/unsigned decimal, binary, ASCII, IEEE-754 float conversions,
and schema-driven decoding.
"""

from __future__ import annotations

import math
import re
import struct
from typing import Any

from ramses_rf.payloads import PAYLOAD_REGISTRY, PayloadBase
from ramses_rf.payloads.adapters import payload_to_dict
from ramses_tx.const import Code, Verb

__all__ = [
    "dissect_payload",
    "dissect_payload_blocks",
    "extract_packet_details",
    "format_dissection_output",
    "parse_hex_value",
]

_PACKET_REGEX = re.compile(
    r"(?P<verb>I|RP|RQ|W)\s+"
    r"(?:[0-9]{3}|---|\.\.\.)\s+"
    r"(?P<src>[0-9]{2}:[0-9]{6}|--:------)\s+"
    r"(?P<dst>[0-9]{2}:[0-9]{6}|--:------)\s+"
    r"(?P<gw>[0-9]{2}:[0-9]{6}|--:------)\s+"
    r"(?P<code>[0-9A-Fa-f]{4})\s+"
    r"(?P<len>[0-9]{3})\s+"
    r"(?P<payload>[0-9A-Fa-f]+)"
)


def parse_hex_value(hex_str: str) -> dict[str, Any]:
    """Parse a hex string slice into multiple numeric representations.

    :param hex_str: Hexadecimal string slice to parse.
    :type hex_str: str
    :returns: Dictionary with decoded representations across endianness.
    :rtype: dict[str, Any]
    """
    clean_hex = hex_str.strip().upper()
    result: dict[str, Any] = {
        "raw": clean_hex,
        "hex": f"0x{clean_hex}",
    }

    try:
        dec = int(clean_hex, 16)
        result["dec"] = dec
    except ValueError:
        result["error"] = "Invalid hexadecimal digits"
        return result

    if len(clean_hex) % 2 != 0:
        return result

    raw_bytes = bytes.fromhex(clean_hex)
    byte_count = len(raw_bytes)

    # Byte-swapped hex and little-endian unsigned decimal
    swapped_hex = "".join(
        clean_hex[i : i + 2] for i in range(len(clean_hex) - 2, -2, -2)
    )
    result["swapped_hex"] = f"0x{swapped_hex}"
    result["le_dec"] = int.from_bytes(raw_bytes, byteorder="little", signed=False)

    # Signed decimal conversions for standard integer sizes
    if byte_count in (1, 2, 4, 8):
        result["signed_dec"] = int.from_bytes(raw_bytes, byteorder="big", signed=True)
        result["le_signed_dec"] = int.from_bytes(
            raw_bytes, byteorder="little", signed=True
        )

    # IEEE 754 Floating-point conversions
    if byte_count == 4:
        val_f = struct.unpack(">f", raw_bytes)[0]
        le_val_f = struct.unpack("<f", raw_bytes)[0]
        result["float"] = None if math.isnan(val_f) else round(val_f, 6)
        result["le_float"] = None if math.isnan(le_val_f) else round(le_val_f, 6)
    elif byte_count == 8:
        val_d = struct.unpack(">d", raw_bytes)[0]
        le_val_d = struct.unpack("<d", raw_bytes)[0]
        result["float"] = None if math.isnan(val_d) else round(val_d, 6)
        result["le_float"] = None if math.isnan(le_val_d) else round(le_val_d, 6)

    # Binary string representation
    result["bin"] = f"0b{dec:0{len(clean_hex) * 4}b}"

    # Printable ASCII detection
    if all(32 <= b <= 126 for b in raw_bytes):
        result["ascii"] = raw_bytes.decode("ascii")

    return result


def dissect_payload_blocks(
    payload_hex: str,
    block_size_bytes: int,
    skip_bytes: int = 0,
) -> dict[str, dict[str, Any]]:
    """Slice a hex payload into fixed-size byte blocks and decode them.

    :param payload_hex: Sanitised hexadecimal string.
    :type payload_hex: str
    :param block_size_bytes: Size of each word block in bytes.
    :type block_size_bytes: int
    :param skip_bytes: Number of leading bytes to skip before slicing.
    :type skip_bytes: int
    :returns: Mapping of block names to parsed block dictionaries.
    :rtype: dict[str, dict[str, Any]]
    """
    clean_hex = re.sub(r"[^0-9A-Fa-f]", "", payload_hex)
    skip_chars = skip_bytes * 2
    data_section = clean_hex[skip_chars:]
    block_chars = block_size_bytes * 2

    blocks: dict[str, dict[str, Any]] = {}
    total_blocks = len(data_section) // block_chars

    for block_index in range(total_blocks):
        start_char = block_index * block_chars
        end_char = start_char + block_chars
        block_hex = data_section[start_char:end_char]
        block_info = parse_hex_value(block_hex)
        byte_offset = skip_bytes + (block_index * block_size_bytes)
        block_info["offset_bytes"] = byte_offset
        block_info["offset_range"] = (
            f"+{byte_offset:02d}..+{byte_offset + block_size_bytes - 1:02d}"
            if block_size_bytes > 1
            else f"+{byte_offset:02d}"
        )
        blocks[f"word_{block_index + 1}"] = block_info

    # Capture remaining trailing bytes if not evenly divisible
    remainder_chars = len(data_section) % block_chars
    if remainder_chars > 0:
        start_char = total_blocks * block_chars
        rem_hex = data_section[start_char:]
        if len(rem_hex) % 2 == 0:
            rem_info = parse_hex_value(rem_hex)
            byte_offset = skip_bytes + (total_blocks * block_size_bytes)
            rem_info["offset_bytes"] = byte_offset
            rem_info["offset_range"] = f"+{byte_offset:02d} (rem)"
            blocks["remainder"] = rem_info

    return blocks


_VERB_MAP: dict[str, Verb] = {
    "I": Verb.I_,
    " I": Verb.I_,
    "RP": Verb.RP,
    "RQ": Verb.RQ,
    "W": Verb.W_,
    " W": Verb.W_,
}


def extract_packet_details(
    packet_line: str,
) -> tuple[Code | str | None, Verb | None, str]:
    """Extract opcode, verb, and payload hex from a log line or raw string.

    :param packet_line: Raw input text from CLI or pipeline.
    :type packet_line: str
    :returns: A tuple of (opcode, verb, payload_hex).
    :rtype: tuple[Code | str | None, Verb | None, str]
    """
    cleaned = packet_line.strip()
    match = _PACKET_REGEX.search(cleaned)
    if match:
        code_str = match.group("code").upper()
        verb_str = match.group("verb")
        try:
            code_val: Code | str = Code(code_str)
        except ValueError:
            code_val = code_str
        verb_val = _VERB_MAP.get(verb_str)
        return code_val, verb_val, match.group("payload")

    # Check for short form e.g. "RQ 2411 000007..." or "2411 000007..."
    tokens = cleaned.split()
    if len(tokens) >= 3 and tokens[0] in _VERB_MAP and len(tokens[1]) == 4:
        code_str = tokens[1].upper()
        try:
            code_val = Code(code_str)
        except ValueError:
            code_val = code_str
        return (
            code_val,
            _VERB_MAP[tokens[0]],
            re.sub(r"[^0-9A-Fa-f]", "", tokens[2]),
        )
    if len(tokens) >= 2 and len(tokens[0]) == 4:
        code_str = tokens[0].upper()
        try:
            code_val = Code(code_str)
        except ValueError:
            code_val = code_str
        return code_val, None, re.sub(r"[^0-9A-Fa-f]", "", tokens[1])

    # Bare payload
    pure_hex = re.sub(r"[^0-9A-Fa-f]", "", cleaned)
    return None, None, pure_hex


def dissect_payload(
    payload_hex: str,
    block_sizes: tuple[int, ...] = (1, 2, 4, 6, 8),
    skip_bytes: int = 0,
    opcode: Code | str | None = None,
    verb: Verb | str | None = None,
) -> dict[str, Any]:
    """Dissect a hex payload with multi-block representation and schema lookup.

    :param payload_hex: The hexadecimal payload string.
    :type payload_hex: str
    :param block_sizes: Tuple of block word sizes in bytes to evaluate.
    :type block_sizes: tuple[int, ...]
    :param skip_bytes: Leading bytes to skip for word slicing.
    :type skip_bytes: int
    :param opcode: Optional 4-character RAMSES opcode or Code enum.
    :type opcode: Code | str | None
    :param verb: Optional message verb (e.g. RP, I, RQ, W) or Verb enum.
    :type verb: Verb | str | None
    :returns: Comprehensive payload dissection dictionary.
    :rtype: dict[str, Any]
    """
    clean_hex = re.sub(r"[^0-9A-Fa-f]", "", payload_hex)
    byte_length = len(clean_hex) // 2

    result: dict[str, Any] = {
        "payload_hex": clean_hex,
        "byte_length": byte_length,
        "opcode": opcode,
        "verb": verb,
        "skip_bytes": skip_bytes,
        "blocks": {},
    }

    for size in block_sizes:
        if size <= byte_length:
            result["blocks"][f"block_{size}byte"] = dissect_payload_blocks(
                clean_hex, block_size_bytes=size, skip_bytes=skip_bytes
            )

    # Attempt registered schema decoding if opcode is known
    if opcode and len(clean_hex) >= 2:
        try:
            code_enum = Code(opcode.upper())
        except ValueError:
            code_enum = None

        target_code: Code | str = code_enum if code_enum else opcode.upper()
        payload_cls = PAYLOAD_REGISTRY.get(target_code)

        if payload_cls and issubclass(payload_cls, PayloadBase):
            try:
                raw_bytes = bytes.fromhex(clean_hex)
                parsed_instance = payload_cls.from_bytes(raw_bytes)
                if isinstance(parsed_instance, list):
                    result["schema_decoded"] = [
                        payload_to_dict(inst) for inst in parsed_instance
                    ]
                else:
                    result["schema_decoded"] = payload_to_dict(parsed_instance)
            except Exception as err:  # noqa: BLE001
                result["schema_decode_error"] = str(err)

    return result


def _format_field(value: Any, width: int, align: str = "left") -> str:
    """Format an item to a fixed column width.

    :param value: Value to format.
    :param width: Target column width.
    :param align: Text alignment ('left' or 'right').
    :returns: Formatted string padded to column width.
    """
    if value is None:
        text = "-"
    elif isinstance(value, float):
        text = f"{value:g}"
    else:
        text = str(value)

    if len(text) > width:
        text = text[: width - 2] + ".." if width > 2 else text[:width]

    return f"{text:>{width}}" if align == "right" else f"{text:<{width}}"


def format_dissection_table(
    blocks: dict[str, dict[str, Any]],
    title: str,
) -> str:
    """Format block slices into an aligned terminal table.

    :param blocks: Dictionary mapping word block names to parsed details.
    :type blocks: dict[str, dict[str, Any]]
    :param title: Title header for the table.
    :type title: str
    :returns: Multi-line string containing the formatted ASCII table.
    :rtype: str
    """
    if not blocks:
        return f"{title}: No blocks available\n"

    columns = [
        ("Offset", 10, "left", "offset_range"),
        ("Raw Hex", 10, "left", "raw"),
        ("Dec (BE)", 11, "right", "dec"),
        ("Signed (BE)", 12, "right", "signed_dec"),
        ("Dec (LE)", 11, "right", "le_dec"),
        ("Float (BE)", 12, "right", "float"),
        ("ASCII", 8, "left", "ascii"),
        ("Binary", 34, "left", "bin"),
    ]

    header_parts = [
        _format_field(name, width, align) for name, width, align, _ in columns
    ]
    header_line = "  ".join(header_parts)
    divider = "-" * len(header_line)

    lines = [f"\n{title} ({len(blocks)} words):", header_line, divider]

    for block_info in blocks.values():
        row_parts = []
        for _, width, align, key in columns:
            val = block_info.get(key)
            row_parts.append(_format_field(val, width, align))
        lines.append("  ".join(row_parts))

    return "\n".join(lines) + "\n"


def format_dissection_output(dissection: dict[str, Any]) -> str:
    """Format complete payload dissection into formatted human-readable output.

    :param dissection: Dictionary returned by dissect_payload.
    :type dissection: dict[str, Any]
    :returns: Multi-line formatted terminal report.
    :rtype: str
    """
    output: list[str] = [
        "=" * 70,
        "RAMSES RF Payload Dissection Report",
        "=" * 70,
        f"Payload Hex : {dissection['payload_hex']}",
        f"Byte Length : {dissection['byte_length']} bytes ({len(dissection['payload_hex'])} hex characters)",
    ]

    if dissection.get("opcode"):
        output.append(f"Opcode      : {dissection['opcode']}")
    if dissection.get("verb"):
        output.append(f"Verb        : {dissection['verb']}")
    if dissection.get("skip_bytes"):
        output.append(f"Skipped     : {dissection['skip_bytes']} leading bytes")

    if "schema_decoded" in dissection:
        output.append("-" * 70)
        output.append("Schema Decoded Data:")
        schema_data = dissection["schema_decoded"]
        if isinstance(schema_data, dict):
            for k, v in schema_data.items():
                output.append(f"  {k:<20}: {v}")
        elif isinstance(schema_data, list):
            for i, item in enumerate(schema_data):
                output.append(f"  Item {i + 1}: {item}")

    if "schema_decode_error" in dissection:
        output.append("-" * 70)
        output.append(f"Schema Decode Error: {dissection['schema_decode_error']}")

    blocks = dissection.get("blocks", {})
    for block_name, block_dict in blocks.items():
        size_label = block_name.replace("block_", "").replace("byte", "-Byte")
        output.append(
            format_dissection_table(block_dict, title=f"Word Breakdown ({size_label})")
        )

    output.append("=" * 70)
    return "\n".join(output)
