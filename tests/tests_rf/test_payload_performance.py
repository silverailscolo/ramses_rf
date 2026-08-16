import time

from ramses_rf.const import SZ_IS_DAYLIGHT_SAVING
from ramses_rf.payloads.hvac import (
    HvacAirQualityPayload,
    HvacFanModePayload,
    HvacFanRatePayload,
)
from ramses_rf.payloads.opentherm import ReturnTempPayload
from ramses_rf.payloads.system import (
    SystemDateTimePayload,
    SystemOpenThermBridgePayload,
)


def test_hvac_fan_mode_to_dict_performance_and_parity() -> None:
    # Arrange
    payload_bytes = bytes.fromhex("000204")
    payload = HvacFanModePayload.from_bytes(payload_bytes)
    expected_dict = {
        "fan_mode": "low",
        "_mode_index": "02",
        "_mode_max": "04",
        "_scheme": "itho",
    }

    # Act
    start_time = time.perf_counter()
    for _ in range(10000):
        result_dict = payload.to_dict()
    elapsed_us = (time.perf_counter() - start_time) * 1e6 / 10000

    # Assert
    assert result_dict == expected_dict
    assert elapsed_us < 50.0  # Must execute under 50 microseconds per call


def test_hvac_fan_rate_to_dict_performance_and_parity() -> None:
    # Arrange
    payload_bytes = bytes.fromhex("00E600")
    payload = HvacFanRatePayload.from_bytes(payload_bytes)

    # Act
    start_time = time.perf_counter()
    for _ in range(10000):
        result_dict = payload.to_dict()
    elapsed_us = (time.perf_counter() - start_time) * 1e6 / 10000

    # Assert
    assert "fan_rate" in result_dict
    assert elapsed_us < 50.0


def test_opentherm_bridge_to_dict_performance_and_parity() -> None:
    # Arrange
    payload_bytes = bytes.fromhex("000064")
    payload = SystemOpenThermBridgePayload.from_bytes(payload_bytes)

    # Act
    start_time = time.perf_counter()
    for _ in range(10000):
        result_dict = payload.to_dict()
    elapsed_us = (time.perf_counter() - start_time) * 1e6 / 10000

    # Assert
    assert "_value" in result_dict
    assert elapsed_us < 50.0


def test_return_temp_sentinel_to_dict_performance_and_parity() -> None:
    # Arrange
    payload_bytes = bytes.fromhex("007FFF")
    payload = ReturnTempPayload.from_bytes(payload_bytes)
    expected_dict = {"temperature": None}

    # Act
    start_time = time.perf_counter()
    for _ in range(10000):
        result_dict = payload.to_dict()
    elapsed_us = (time.perf_counter() - start_time) * 1e6 / 10000

    # Assert
    assert result_dict == expected_dict
    assert elapsed_us < 50.0


def test_system_date_time_is_dst_to_dict_performance_and_parity() -> None:
    # Arrange
    payload_bytes = bytes.fromhex("001A08070C1E00")
    payload = SystemDateTimePayload.from_bytes(payload_bytes)

    # Act
    start_time = time.perf_counter()
    for _ in range(10000):
        result_dict = payload.to_dict()
    elapsed_us = (time.perf_counter() - start_time) * 1e6 / 10000

    # Assert
    assert SZ_IS_DAYLIGHT_SAVING in result_dict
    assert result_dict[SZ_IS_DAYLIGHT_SAVING] is None
    assert elapsed_us < 50.0


def test_hvac_spider_air_quality_demand_performance_and_parity() -> None:
    # Arrange
    payload_bytes = bytes.fromhex("00010064")
    payload = HvacAirQualityPayload.from_bytes(payload_bytes)

    # Act
    start_time = time.perf_counter()
    for _ in range(10000):
        result_dict = payload.to_dict()
    elapsed_us = (time.perf_counter() - start_time) * 1e6 / 10000

    # Assert
    assert "demand" in result_dict
    assert elapsed_us < 50.0
