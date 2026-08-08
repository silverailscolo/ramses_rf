from datetime import datetime as dt

from ramses_rf.parsers.decoder import decode_packet
from ramses_rf.payloads.adapters import payload_to_dict
from ramses_rf.payloads.heating import HeatDemandPayload, TemperaturePayload
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
