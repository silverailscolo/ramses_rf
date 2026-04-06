#!/usr/bin/env python3
"""Tests for the ramses_tx.opentherm protocol decoder."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ramses_tx.opentherm import (
    F8_8,
    FLAG8,
    S8,
    S16,
    SZ_VALUE,
    SZ_VALUE_HB,
    SZ_VALUE_LB,
    U8,
    U16,
    OtDataId,
    _decode_flags,
    _msg_value,
    decode_frame,
    parity,
)


def build_frame(msg_type: int, data_id: int, data_value: str) -> str:
    """Helper to build a strictly valid OpenTherm frame with correct parity."""
    # Calculate the 31 bits excluding the parity bit (msg_type in bits 6-4)
    byte0_no_parity = (msg_type & 0x07) << 4
    val_int = int(data_value, 16)
    bits31 = (byte0_no_parity << 24) | (data_id << 16) | val_int

    # Calculate parity and insert into bit 7 of the first byte
    p = parity(bits31)
    byte0 = byte0_no_parity | (p << 7)

    return f"{byte0:02X}{data_id:02X}{data_value}"


def test_parity() -> None:
    # Validate parity calculation across binary forms
    assert parity(0b000) == 0
    assert parity(0b001) == 1
    assert parity(0b010) == 1
    assert parity(0b011) == 0
    assert parity(0b111) == 1


def test_msg_value_validation() -> None:
    # Length validation
    with pytest.raises(AssertionError):
        _msg_value("123", U8)

    # Unsupported value types return the input string natively
    assert _msg_value("1234", "UNSUPPORTED") == "1234"


def test_msg_value_data_types() -> None:
    # FLAG8 bit reversal mapping
    assert _msg_value("03", FLAG8) == [1, 1, 0, 0, 0, 0, 0, 0]

    # U8 and S8
    assert _msg_value("FF", U8) == 255
    assert _msg_value("FF", S8) == -1

    # U16 and S16
    assert _msg_value("0100", U16) == 256
    assert _msg_value("FF00", S16) == -256

    # F8_8 conversion
    assert _msg_value("0100", F8_8) == 1.0


def test_msg_value_value_errors() -> None:
    # Specific types explicitly raise ValueError for "FF" / "FFFF" bounds
    assert _msg_value("FFFF", U16) is None
    assert _msg_value("FFFF", S16) is None
    assert _msg_value("FFFF", F8_8) is None


def test_decode_flags() -> None:
    # Valid flag lookup
    res = _decode_flags(OtDataId.STATUS, "0000")
    assert "StatusCHEnabled" in res[0x0100]["var"]

    # Invalid flag lookup (ID has no flags associated in schema)
    with pytest.raises(KeyError, match="has no flags"):
        _decode_flags(OtDataId.OEM_CODE, "0000")


def test_decode_frame_invalid_inputs() -> None:
    # Type and length validation
    with pytest.raises(TypeError, match="Invalid frame"):
        decode_frame(123)
    with pytest.raises(TypeError, match="Invalid frame"):
        decode_frame("123")

    # Parity check failure (Intentionally corrupt the parity bit)
    with pytest.raises(ValueError, match="Invalid parity bit"):
        decode_frame("00180100")

    # Spare bits validation failure (Inject 1 into the spare bit position)
    with pytest.raises(ValueError, match="Invalid spare bits"):
        # 0x41 & 0x0F = 0x01 != 0, fixing parity bit to pass first gate
        decode_frame("C1180100")

    # Unknown Data ID validation
    with pytest.raises(KeyError, match="Unknown data-id"):
        decode_frame(build_frame(4, 0x3E, "0000"))  # 0x3E (62) doesn't exist


def test_decode_frame_read_data_null_injection() -> None:
    # Msg type 0b000 (READ_DATA) injects None mapping for upstream protection

    # 1. VAL is a dict of FLAG8, FLAG8 (SZ_VALUE injected as None)
    _, _, data_1, _ = decode_frame(build_frame(0b000, 0x00, "0000"))
    assert data_1[SZ_VALUE] is None
    assert SZ_VALUE_HB not in data_1

    # 2. VAL is a dict of FLAG8, U8 (SZ_VALUE_HB & LB injected as None)
    _, _, data_2, _ = decode_frame(build_frame(0b000, 0x02, "0000"))
    assert data_2[SZ_VALUE_HB] is None
    assert data_2[SZ_VALUE_LB] is None
    assert SZ_VALUE not in data_2

    # 3. VAR is dict, VAL is scalar (SZ_VALUE_HB & LB injected as None)
    _, _, data_3, _ = decode_frame(build_frame(0b000, 0x0A, "0000"))
    assert data_3[SZ_VALUE_HB] is None
    assert data_3[SZ_VALUE_LB] is None

    # 4. VAL is standard scalar (SZ_VALUE injected as None)
    _, _, data_4, _ = decode_frame(build_frame(0b000, 0x01, "0000"))
    assert data_4[SZ_VALUE] is None

    # 5. Empty / corrupt schema fallback mapping (SZ_VALUE injected as None)
    with patch.dict("ramses_tx.opentherm.OPENTHERM_MESSAGES", {0x3E: {}}):
        _, _, data_5, _ = decode_frame(build_frame(0b000, 0x3E, "0000"))
        assert data_5[SZ_VALUE] is None


def test_decode_frame_read_ack_valid_values() -> None:
    # Msg type 0b100 (READ_ACK) processes payload accurately

    # 1. VAL is dict of FLAG8, FLAG8
    _, _, data_1, _ = decode_frame(build_frame(0b100, 0x00, "0305"))
    assert data_1[SZ_VALUE] == [1, 1, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0]

    # 2. VAL is dict of FLAG8, U8
    _, _, data_2, _ = decode_frame(build_frame(0b100, 0x02, "0305"))
    assert data_2[SZ_VALUE_HB] == [1, 1, 0, 0, 0, 0, 0, 0]
    assert data_2[SZ_VALUE_LB] == 5

    # 3. VAR is dict, parses both bytes securely
    _, _, data_3, _ = decode_frame(build_frame(0b100, 0x0A, "0305"))
    assert data_3[SZ_VALUE_HB] == 3
    assert data_3[SZ_VALUE_LB] == 5

    # 4. VAL is scalar FLAG8
    _, _, data_4, _ = decode_frame(build_frame(0b100, 0x06, "0300"))
    assert data_4[SZ_VALUE] == [1, 1, 0, 0, 0, 0, 0, 0]

    # 5. VAL is scalar U16
    _, _, data_5, _ = decode_frame(build_frame(0b100, 0x73, "0305"))
    assert data_5[SZ_VALUE] == 773

    # 6. VAL is F8_8 -> SENSOR PERCENTAGE mapping
    _, _, data_6, _ = decode_frame(build_frame(0b100, 0x0E, "6400"))
    assert data_6[SZ_VALUE] == 1.0

    # 7. VAL is F8_8 -> SENSOR FLOW_RATE mapping
    _, _, data_7, _ = decode_frame(build_frame(0b100, 0x13, "0100"))
    assert data_7[SZ_VALUE] == 1.0

    # 8. VAL is F8_8 -> SENSOR PRESSURE mapping
    _, _, data_8, _ = decode_frame(build_frame(0b100, 0x12, "0100"))
    assert data_8[SZ_VALUE] == 1.0

    # 9. VAL is F8_8 -> SENSOR TEMPERATURE mapping
    _, _, data_9, _ = decode_frame(build_frame(0b100, 0x18, "0100"))
    assert data_9[SZ_VALUE] == 1.0

    # 10. VAL is F8_8 -> Result resolves to None ("FFFF" bypasses mapping)
    _, _, data_10, _ = decode_frame(build_frame(0b100, 0x18, "FFFF"))
    assert data_10[SZ_VALUE] is None


def test_decode_frame_fallback_values() -> None:
    # 1. Unrecognized VAL string string falls back to U16 processing
    with patch.dict(
        "ramses_tx.opentherm.OPENTHERM_MESSAGES", {0x3E: {"val": "UNKNOWN"}}
    ):
        _, _, data_1, _ = decode_frame(build_frame(0b100, 0x3E, "0305"))
        assert data_1[SZ_VALUE] == 773

    # 2. Corrupt / empty schema dictionary falls back to U16 processing
    with patch.dict("ramses_tx.opentherm.OPENTHERM_MESSAGES", {0x3E: {}}):
        _, _, data_2, _ = decode_frame(build_frame(0b100, 0x3E, "0305"))
        assert data_2[SZ_VALUE] == 773
