from datetime import datetime as dt

from ramses_rf.parsers.decoder import decode_packet
from ramses_rf.payloads.adapters import payload_to_dict
from ramses_rf.payloads.heating import (
    BindingPayload,
    DhwTemperaturePayload,
    HeatDemandPayload,
    ScheduleSwitchpointPayload,
    SystemSyncPayload,
    TemperaturePayload,
    ZoneConfigPayload,
)
from ramses_rf.payloads.hvac import FanModePayload
from ramses_tx.dtos import PacketDTO


def test_heat_demand_payload_3150_parity() -> None:
    # Arrange
    raw_hex = "C8"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = HeatDemandPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.demand_percent == 200
    assert reencoded == raw_hex
    assert as_dict == {"demand_percent": 200}


def test_temperature_payload_30c9_simple_parity() -> None:
    # Arrange
    raw_hex = "07D0"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = TemperaturePayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.zone_idx is None
    assert payload.temperature == 20.0
    assert reencoded == raw_hex
    assert as_dict == {"zone_idx": None, "temperature": 20.0}


def test_temperature_payload_30c9_zone_parity() -> None:
    # Arrange
    raw_hex = "0107D0"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = TemperaturePayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.zone_idx == 1
    assert payload.temperature == 20.0
    assert reencoded == raw_hex
    assert as_dict == {"zone_idx": 1, "temperature": 20.0}


def test_schedule_switchpoint_payload_0404_parity() -> None:
    # Arrange
    raw_hex = "00000000010000000100000068010000D0070000"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = ScheduleSwitchpointPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.zone_idx == 1
    assert payload.day_of_week == 1
    assert payload.time_of_day_mins == 360  # 0168 hex -> 360 mins = 06:00
    assert payload.setpoint_value == 2000  # 07D0 hex -> 2000
    assert reencoded == raw_hex
    assert as_dict == {
        "zone_idx": 1,
        "day_of_week": 1,
        "time_of_day_mins": 360,
        "setpoint_value": 2000,
    }


def test_dhw_temperature_payload_10a0_parity() -> None:
    # Arrange
    raw_hex = "000ED8"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = DhwTemperaturePayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.dhw_idx == 0
    assert payload.temperature == 38.0
    assert reencoded == raw_hex
    assert as_dict == {"dhw_idx": 0, "temperature": 38.0}


def test_system_sync_payload_1030_parity() -> None:
    # Arrange
    raw_hex = "00"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = SystemSyncPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.sync_flag == 0
    assert reencoded == raw_hex
    assert as_dict == {"sync_flag": 0}


def test_binding_payload_1fc9_parity() -> None:
    # Arrange
    raw_hex = "000102030405"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = BindingPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.binding_type == 0
    assert payload.binding_data == b"\x01\x02\x03\x04\x05"
    assert reencoded == raw_hex
    assert as_dict == {
        "binding_type": 0,
        "binding_data": b"\x01\x02\x03\x04\x05",
    }


def test_zone_config_payload_000a_parity() -> None:
    # Arrange
    raw_hex = "000001F40DB8"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = ZoneConfigPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.zone_idx == 0
    assert payload.zone_flags == 0
    assert payload.min_temp == 5.0
    assert payload.max_temp == 35.12
    assert reencoded == raw_hex
    assert as_dict == {
        "zone_idx": 0,
        "zone_flags": 0,
        "min_temp": 5.0,
        "max_temp": 35.12,
    }


def test_fan_mode_payload_22f1_parity() -> None:
    # Arrange
    raw_hex = "000204"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = FanModePayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.header == 0
    assert payload.mode_idx == 2
    assert payload.mode_max == 4
    assert reencoded == raw_hex
    assert as_dict == {"header": 0, "mode_idx": 2, "mode_max": 4}


def test_pipeline_shadow_parity_execution() -> None:
    # Arrange
    dto = PacketDTO(
        timestamp=dt.now(),
        rssi="-70",
        verb=" I",
        seq="001",
        addr1="04:123456",
        addr2="--:------",
        addr3="--:------",
        code="3150",
        length="002",
        payload="00C8",
    )

    # Act
    result = decode_packet(dto)

    # Assert
    assert isinstance(result, dict)
    assert result.get("seqx_num") == "001"
