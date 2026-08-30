"""Unit tests for OpenTherm protocol mapping models, decoding, and encoding."""

from __future__ import annotations

from typing import cast
from unittest.mock import patch

import pytest

from ramses_rf.protocol.opentherm import (
    F8_8,
    FLAG8,
    OPENTHERM_PARAMS_DATA_IDS,
    OPENTHERM_POLL_DATA_IDS,
    OPENTHERM_STATUS_DATA_IDS,
    OPENTHERM_TO_RAMSES_MAP,
    PARAMS_DATA_IDS,
    RAMSES_TO_OPENTHERM_MAP,
    S8,
    S16,
    SCHEMA_DATA_IDS,
    STATUS_DATA_IDS,
    SZ_VALUE,
    SZ_VALUE_HB,
    SZ_VALUE_LB,
    U8,
    U16,
    OtDataId,
    _msg_value,
    decode_frame,
    encode_opentherm_payload,
    parity,
)
from ramses_tx.const import Code


def build_frame(msg_type: int, data_id: int, data_value: str) -> str:
    """Build an OpenTherm 8-character hex frame with valid parity."""
    # Arrange: Calculate 31 bits excluding parity (msg_type in bits 6-4)
    byte0_no_parity = (msg_type & 0x07) << 4
    val_int = int(data_value, 16)
    bits31 = (byte0_no_parity << 24) | (data_id << 16) | val_int

    # Act: Calculate parity and insert into bit 7 of byte 0
    p = parity(bits31)
    byte0 = byte0_no_parity | (p << 7)

    # Assert: Return full 8-character frame
    return f"{byte0:02X}{data_id:02X}{data_value}"


def test_opentherm_to_ramses_map_integrity() -> None:
    # Arrange & Act & Assert
    for ot_data_id, code in OPENTHERM_TO_RAMSES_MAP.items():
        assert isinstance(ot_data_id, OtDataId)
        assert isinstance(code, Code)

    assert OPENTHERM_TO_RAMSES_MAP[OtDataId.STATUS] == Code._3EF0
    assert OPENTHERM_TO_RAMSES_MAP[OtDataId.CONTROL_SETPOINT] == Code._22D9
    assert OPENTHERM_TO_RAMSES_MAP[OtDataId.REL_MODULATION_LEVEL] == Code._3EF0
    assert OPENTHERM_TO_RAMSES_MAP[OtDataId.CH_WATER_PRESSURE] == Code._1300
    assert OPENTHERM_TO_RAMSES_MAP[OtDataId.DHW_FLOW_RATE] == Code._12F0
    assert OPENTHERM_TO_RAMSES_MAP[OtDataId.BOILER_OUTPUT_TEMP] == Code._3200
    assert OPENTHERM_TO_RAMSES_MAP[OtDataId.DHW_TEMP] == Code._1260
    assert OPENTHERM_TO_RAMSES_MAP[OtDataId.OUTSIDE_TEMP] == Code._1290
    assert OPENTHERM_TO_RAMSES_MAP[OtDataId.BOILER_RETURN_TEMP] == Code._3210
    assert OPENTHERM_TO_RAMSES_MAP[OtDataId.DHW_SETPOINT] == Code._10A0
    assert OPENTHERM_TO_RAMSES_MAP[OtDataId.CH_MAX_SETPOINT] == Code._1081


def test_ramses_to_opentherm_map_integrity() -> None:
    # Arrange & Act & Assert
    for code, ot_data_ids in RAMSES_TO_OPENTHERM_MAP.items():
        assert isinstance(code, Code)
        assert isinstance(ot_data_ids, tuple)
        assert all(isinstance(data_id, OtDataId) for data_id in ot_data_ids)

    assert RAMSES_TO_OPENTHERM_MAP[Code._3EF0] == (
        OtDataId.STATUS,
        OtDataId.REL_MODULATION_LEVEL,
    )
    assert RAMSES_TO_OPENTHERM_MAP[Code._3EF1] == (
        OtDataId.REL_MODULATION_LEVEL,
    )
    assert RAMSES_TO_OPENTHERM_MAP[Code._3200] == (
        OtDataId.BOILER_OUTPUT_TEMP,
    )
    assert RAMSES_TO_OPENTHERM_MAP[Code._3210] == (
        OtDataId.BOILER_RETURN_TEMP,
    )
    assert RAMSES_TO_OPENTHERM_MAP[Code._22D9] == (OtDataId.CONTROL_SETPOINT,)
    assert RAMSES_TO_OPENTHERM_MAP[Code._1300] == (OtDataId.CH_WATER_PRESSURE,)
    assert RAMSES_TO_OPENTHERM_MAP[Code._12F0] == (OtDataId.DHW_FLOW_RATE,)
    assert RAMSES_TO_OPENTHERM_MAP[Code._1260] == (OtDataId.DHW_TEMP,)
    assert RAMSES_TO_OPENTHERM_MAP[Code._1290] == (OtDataId.OUTSIDE_TEMP,)
    assert RAMSES_TO_OPENTHERM_MAP[Code._10A0] == (OtDataId.DHW_SETPOINT,)
    assert RAMSES_TO_OPENTHERM_MAP[Code._1081] == (OtDataId.CH_MAX_SETPOINT,)


def test_constant_data_id_sets() -> None:
    # Arrange & Act & Assert
    assert OtDataId._00 in STATUS_DATA_IDS
    assert OtDataId._0E in PARAMS_DATA_IDS
    assert OtDataId._03 in SCHEMA_DATA_IDS

    assert OtDataId.STATUS in OPENTHERM_STATUS_DATA_IDS
    assert OtDataId.BOILER_OUTPUT_TEMP in OPENTHERM_STATUS_DATA_IDS
    assert OtDataId.BOILER_RETURN_TEMP in OPENTHERM_STATUS_DATA_IDS
    assert OtDataId.CONTROL_SETPOINT in OPENTHERM_STATUS_DATA_IDS

    assert OtDataId.DHW_SETPOINT in OPENTHERM_PARAMS_DATA_IDS
    assert OtDataId.CH_MAX_SETPOINT in OPENTHERM_PARAMS_DATA_IDS

    # Ensure modulation IDs are strictly excluded from periodic polling
    assert OtDataId.REL_MODULATION_LEVEL not in OPENTHERM_POLL_DATA_IDS
    assert OtDataId._0E not in OPENTHERM_POLL_DATA_IDS


def test_parity_calculations() -> None:
    # Arrange & Act & Assert
    assert parity(0b000) == 0
    assert parity(0b001) == 1
    assert parity(0b010) == 1
    assert parity(0b011) == 0
    assert parity(0b100) == 1
    assert parity(0b111) == 1
    assert parity(0b1111) == 0
    assert parity(0x7FFFFFFF) == 1
    assert parity(0x55555555) == 0


def test_encode_opentherm_payload() -> None:
    # Arrange: Select Data-IDs with known parity values
    # Act & Assert
    assert encode_opentherm_payload(OtDataId.STATUS) == "0000000000"
    assert encode_opentherm_payload(OtDataId.CONTROL_SETPOINT) == "0080010000"
    assert (
        encode_opentherm_payload(OtDataId.BOILER_OUTPUT_TEMP) == "0080190000"
    )
    assert (
        encode_opentherm_payload(OtDataId.BOILER_RETURN_TEMP) == "00801C0000"
    )
    assert encode_opentherm_payload(OtDataId.DHW_SETPOINT) == "0080380000"
    assert encode_opentherm_payload(OtDataId.CH_MAX_SETPOINT) == "0000390000"


def test_msg_value_flag8() -> None:
    # Arrange & Act & Assert: Verify LSB-first bit ordering
    assert _msg_value("00", FLAG8) == [0, 0, 0, 0, 0, 0, 0, 0]
    assert _msg_value("01", FLAG8) == [1, 0, 0, 0, 0, 0, 0, 0]
    assert _msg_value("02", FLAG8) == [0, 1, 0, 0, 0, 0, 0, 0]
    assert _msg_value("03", FLAG8) == [1, 1, 0, 0, 0, 0, 0, 0]
    assert _msg_value("80", FLAG8) == [0, 0, 0, 0, 0, 0, 0, 1]
    assert _msg_value("FF", FLAG8) == [1, 1, 1, 1, 1, 1, 1, 1]


def test_msg_value_u8_and_s8() -> None:
    # Arrange & Act & Assert
    assert _msg_value("00", U8) == 0
    assert _msg_value("7F", U8) == 127
    assert _msg_value("80", U8) == 128
    assert _msg_value("FF", U8) == 255

    assert _msg_value("00", S8) == 0
    assert _msg_value("7F", S8) == 127
    assert _msg_value("80", S8) == -128
    assert _msg_value("FF", S8) == -1


def test_msg_value_u16_and_s16() -> None:
    # Arrange & Act & Assert
    assert _msg_value("0000", U16) == 0
    assert _msg_value(Code._0100, U16) == 256
    assert _msg_value("0305", U16) == 773
    assert _msg_value("FFFE", U16) == 65534
    assert _msg_value("FFFF", U16) is None  # Sentinel raised ValueError caught

    assert _msg_value("0000", S16) == 0
    assert _msg_value(Code._0100, S16) == 256
    assert _msg_value("FF00", S16) == -256
    assert _msg_value("8000", S16) == -32768
    assert _msg_value("FFFF", S16) is None  # Sentinel raised ValueError caught


def test_msg_value_f8_8() -> None:
    # Arrange & Act & Assert
    assert _msg_value("0000", F8_8) == 0.0
    assert _msg_value("0080", F8_8) == 0.5
    assert _msg_value(Code._0100, F8_8) == 1.0
    assert _msg_value("1400", F8_8) == 20.0
    assert _msg_value("FF00", F8_8) == -1.0

    # Sentinels resolve to None
    assert _msg_value("FFFF", F8_8) is None
    assert _msg_value("47AB", F8_8) is None
    assert _msg_value("1980", F8_8) is None


def test_msg_value_validation_and_unsupported_types() -> None:
    # Arrange & Act & Assert
    with pytest.raises(AssertionError):
        _msg_value("1", U8)

    with pytest.raises(AssertionError):
        _msg_value("123", U8)

    with pytest.raises(AssertionError):
        _msg_value("12345", U8)

    # Unsupported value types return raw string
    assert _msg_value("1234", "UNSUPPORTED") == "1234"


def test_decode_frame_invalid_inputs() -> None:
    # Arrange & Act & Assert: Type and length validation
    with pytest.raises(TypeError, match="Invalid frame"):
        decode_frame(cast(str, 123))

    with pytest.raises(TypeError, match="Invalid frame"):
        decode_frame("1234567")

    with pytest.raises(TypeError, match="Invalid frame"):
        decode_frame("123456789")

    # Parity check failure (Intentionally corrupt the parity bit)
    with pytest.raises(ValueError, match="Invalid parity bit"):
        decode_frame("00180100")

    # Spare bits validation failure (Inject 1 into spare bit positions 0-3)
    with pytest.raises(ValueError, match="Invalid spare bits"):
        decode_frame("C1180100")

    # Unknown Data ID validation
    with pytest.raises(KeyError, match="Unknown data-id"):
        decode_frame(build_frame(4, 0x3E, "0000"))


def test_decode_frame_read_data_null_injection() -> None:
    # Arrange: Build READ_DATA frames (msg_type 0b000)
    # Act: Decode frames for various schema types
    # Assert: Verify null value injection for upstream stability

    # 1. Dual FLAG8 bytes (DataId 0x00) -> SZ_VALUE is None
    _, _, data_1, _ = decode_frame(build_frame(0b000, 0x00, "0000"))
    assert data_1[SZ_VALUE] is None
    assert SZ_VALUE_HB not in data_1

    # 2. Mixed FLAG8 + U8 (DataId 0x02) -> SZ_VALUE_HB & LB are None
    _, _, data_2, _ = decode_frame(build_frame(0b000, 0x02, "0000"))
    assert data_2[SZ_VALUE_HB] is None
    assert data_2[SZ_VALUE_LB] is None
    assert SZ_VALUE not in data_2

    # 3. Scalar U16 / F8.8 (DataId 0x01) -> SZ_VALUE is None
    _, _, data_3, _ = decode_frame(build_frame(0b000, 0x01, "0000"))
    assert data_3[SZ_VALUE] is None


def test_decode_frame_read_ack_telemetry() -> None:
    # Arrange: Build valid READ_ACK (msg_type 0b100) frames across telemetry suite
    # Act & Assert:

    # 1. DataId 0x00: Master/Slave status (dual FLAG8 concatenated)
    _, _, data_status, _ = decode_frame(build_frame(0b100, 0x00, "0305"))
    assert data_status[SZ_VALUE] == [
        1,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
    ]

    # 2. DataId 0x02: Master Config (FLAG8 + U8)
    _, _, data_cfg, _ = decode_frame(build_frame(0b100, 0x02, "0305"))
    assert data_cfg[SZ_VALUE_HB] == [1, 1, 0, 0, 0, 0, 0, 0]
    assert data_cfg[SZ_VALUE_LB] == 5

    # 3. DataId 0x06: Remote Flags (FLAG8 scalar)
    _, _, data_rem, _ = decode_frame(build_frame(0b100, 0x06, "0300"))
    assert data_rem[SZ_VALUE] == [1, 1, 0, 0, 0, 0, 0, 0]

    # 4. DataId 0x73: OEM Code (U16)
    _, _, data_oem, _ = decode_frame(build_frame(0b100, 0x73, "0305"))
    assert data_oem[SZ_VALUE] == 773

    # 5. DataId 0x0E: Max Rel Modulation (Sensor.PERCENTAGE -> 0.0-1.0)
    _, _, data_mod_max, _ = decode_frame(build_frame(0b100, 0x0E, "6400"))
    assert data_mod_max[SZ_VALUE] == 1.0

    # 6. DataId 0x11: Rel Modulation Level (Sensor.PERCENTAGE -> 0.0-1.0)
    _, _, data_mod, _ = decode_frame(build_frame(0b100, 0x11, Code._3200))
    assert data_mod[SZ_VALUE] == 0.5

    # 7. DataId 0x12: CH Water Pressure (Sensor.PRESSURE -> 0.1 bar resolution)
    _, _, data_press, _ = decode_frame(build_frame(0b100, 0x12, Code._0100))
    assert data_press[SZ_VALUE] == 1.0

    # 8. DataId 0x13: DHW Flow Rate (Sensor.FLOW_RATE -> 0.01 l/min resolution)
    _, _, data_flow, _ = decode_frame(build_frame(0b100, 0x13, Code._0100))
    assert data_flow[SZ_VALUE] == 1.0

    # 9. DataId 0x18: Room Temperature (Sensor.TEMPERATURE -> 0.01°C resolution)
    _, _, data_temp, _ = decode_frame(build_frame(0b100, 0x18, "1400"))
    assert data_temp[SZ_VALUE] == 20.0

    # 10. DataId 0x18 with sentinel "FFFF" -> None
    _, _, data_temp_null, _ = decode_frame(build_frame(0b100, 0x18, "FFFF"))
    assert data_temp_null[SZ_VALUE] is None


def test_decode_frame_fallback_handling() -> None:
    # Arrange: Unrecognized VAL type falls back to U16 decoding
    # Act & Assert
    with patch.dict(
        "ramses_rf.protocol.opentherm.OPENTHERM_MESSAGES",
        {0x3E: {"val": "UNKNOWN"}},
    ):
        _, _, data_1, _ = decode_frame(build_frame(0b100, 0x3E, "0305"))
        assert data_1[SZ_VALUE] == 773

    # Corrupt / empty schema dictionary falls back to U16 decoding
    with patch.dict(
        "ramses_rf.protocol.opentherm.OPENTHERM_MESSAGES", {0x3E: {}}
    ):
        _, _, data_2, _ = decode_frame(build_frame(0b100, 0x3E, "0305"))
        assert data_2[SZ_VALUE] == 773
