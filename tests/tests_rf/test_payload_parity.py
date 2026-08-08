from datetime import datetime as dt

import ramses_tx.const as tx_const
from ramses_rf.parsers.decoder import decode_packet
from ramses_rf.payloads.adapters import payload_to_dict
from ramses_rf.payloads.dhw import DhwConfigPayload, DhwModePayload, DhwStatePayload
from ramses_rf.payloads.heating import (
    BindingPayload,
    BoilerRelayDemandPayload,
    DhwTemperaturePayload,
    HeatDemandPayload,
    OutdoorTempPayload,
    RelayDemandPayload,
    ScheduleFragmentPayload,
    ScheduleSwitchpointPayload,
    SetPointInfoPayload,
    SystemSyncPayload,
    TemperaturePayload,
    ZoneConfigPayload,
    ZoneSetpointPayload,
)
from ramses_rf.payloads.hvac import (
    Co2Payload,
    FanModePayload,
    HvacAirQualityPayload,
    HvacBypassStatePayload,
    HvacFanParamPayload,
    HvacFaultStatusPayload,
    HvacFilterChangePayload,
    HvacVentilationStatusPayload,
    RelativeHumidityPayload,
)
from ramses_rf.payloads.opentherm import (
    OpenThermMsgPayload,
    OpenthermSetpointPayload,
    OpenthermStatusPayload,
)
from ramses_rf.payloads.registry import PAYLOAD_REGISTRY
from ramses_rf.payloads.system import (
    SystemClockPayload,
    SystemConfigPayload,
    SystemDatePayload,
    SystemFaultLogPayload,
)
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
    assert as_dict == {
        "domain_or_zone_idx": None,
        "demand_percent": 200,
        "raw_extra": None,
    }


def test_heat_demand_payload_3150_2byte_parity() -> None:
    # Arrange
    raw_hex = "01CA"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = HeatDemandPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.domain_or_zone_idx == 1
    assert payload.demand_percent == 202
    assert payload.raw_extra is None
    assert reencoded == raw_hex
    assert as_dict == {
        "domain_or_zone_idx": 1,
        "demand_percent": 202,
        "raw_extra": None,
    }


def test_heat_demand_payload_3150_multibyte_parity() -> None:
    # Arrange
    raw_hex = "01CA0011"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = HeatDemandPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.domain_or_zone_idx == 1
    assert payload.demand_percent == 202
    assert payload.raw_extra == bytes.fromhex("0011")
    assert reencoded == raw_hex
    assert as_dict == {
        "domain_or_zone_idx": 1,
        "demand_percent": 202,
        "raw_extra": bytes.fromhex("0011"),
    }


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
    assert isinstance(payload, ScheduleSwitchpointPayload)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.zone_idx == 1
    assert payload.day_of_week == 1
    assert payload.time_of_day_mins == 360
    assert payload.setpoint_value == 2000
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
    assert as_dict == {
        "sync_flag": 0,
        "max_flow_setpoint": None,
        "min_flow_setpoint": None,
        "valve_run_time": None,
        "pump_run_time": None,
        "raw_extra": None,
    }


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
    assert isinstance(payload, ZoneConfigPayload)
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


def test_hvac_fan_param_payload_2411_parity() -> None:
    # Arrange
    raw_hex = "00000A0010000000050000000000000064000000010001"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = HvacFanParamPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.param_id == 10
    assert payload.data_type == 16
    assert payload.value_scaled == 5
    assert payload.min_val_scaled == 0
    assert payload.max_val_scaled == 100
    assert payload.precision_scaled == 1
    assert payload.trailer_bytes == b"\x00\x01"
    assert reencoded == raw_hex
    assert as_dict == {
        "param_id": 10,
        "data_type": 16,
        "value_scaled": 5,
        "min_val_scaled": 0,
        "max_val_scaled": 100,
        "precision_scaled": 1,
        "trailer_bytes": b"\x00\x01",
    }


def test_co2_payload_1298_parity() -> None:
    # Arrange
    raw_hex = "02D0"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = Co2Payload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.co2_ppm == 720
    assert reencoded == raw_hex
    assert as_dict == {"co2_ppm": 720}


def test_relative_humidity_payload_12a0_parity() -> None:
    # Arrange
    raw_hex = "64"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = RelativeHumidityPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.humidity_percent == 50.0
    assert reencoded == raw_hex
    assert as_dict == {"humidity_percent": 50.0}


def test_opentherm_msg_payload_3220_parity() -> None:
    # Arrange
    raw_hex = "10001900"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = OpenThermMsgPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.msg_id == 0
    assert payload.msg_type == 1
    assert payload.raw_value == b"\x19\x00"
    assert reencoded == raw_hex
    assert as_dict == {"msg_id": 0, "msg_type": 1, "raw_value": b"\x19\x00"}


def test_dhw_mode_payload_1260_parity() -> None:
    # Arrange
    raw_hex = "000101"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = DhwModePayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.dhw_idx == 0
    assert payload.mode == 1
    assert payload.state == 1
    assert reencoded == raw_hex
    assert as_dict == {"dhw_idx": 0, "mode": 1, "state": 1}


def test_dhw_config_payload_12f0_parity() -> None:
    # Arrange
    raw_hex = "001388"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = DhwConfigPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.dhw_idx == 0
    assert payload.setpoint_temp == 50.0
    assert reencoded == raw_hex
    assert as_dict == {"dhw_idx": 0, "setpoint_temp": 50.0}


def test_dhw_state_payload_1f41_parity() -> None:
    # Arrange
    raw_hex = "0001"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = DhwStatePayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.dhw_idx == 0
    assert payload.active_flag == 1
    assert reencoded == raw_hex
    assert as_dict == {"dhw_idx": 0, "active_flag": 1}


def test_zone_setpoint_payload_0004_parity() -> None:
    # Arrange
    raw_hex = "0107D0"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = ZoneSetpointPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.zone_idx == 1
    assert payload.setpoint_temp == 20.0
    assert reencoded == raw_hex
    assert as_dict == {"zone_idx": 1, "setpoint_temp": 20.0}


def test_outdoor_temp_payload_12c0_parity() -> None:
    # Arrange
    raw_hex = "05DC"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = OutdoorTempPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.temperature == 15.0
    assert reencoded == raw_hex
    assert as_dict == {"temperature": 15.0}


def test_setpoint_info_payload_2309_parity() -> None:
    # Arrange
    raw_hex = "000834"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = SetPointInfoPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.zone_idx == 0
    assert payload.setpoint_temp == 21.0
    assert reencoded == raw_hex
    assert as_dict == {"zone_idx": 0, "setpoint_temp": 21.0}


def test_boiler_relay_demand_payload_3200_parity() -> None:
    # Arrange
    raw_hex = "00C800"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = BoilerRelayDemandPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.domain == 0
    assert payload.demand_percent == 200
    assert payload.flags == 0
    assert reencoded == raw_hex
    assert as_dict == {"domain": 0, "demand_percent": 200, "flags": 0}


def test_hvac_ventilation_status_payload_22e0_parity() -> None:
    # Arrange
    raw_hex = "0100"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = HvacVentilationStatusPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.flow_mode == 1
    assert payload.status_flags == 0
    assert reencoded == raw_hex
    assert as_dict == {"flow_mode": 1, "status_flags": 0}


def test_hvac_bypass_state_payload_31d9_parity() -> None:
    # Arrange
    raw_hex = "6400"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = HvacBypassStatePayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.bypass_position == 100
    assert payload.mode_flags == 0
    assert reencoded == raw_hex
    assert as_dict == {"bypass_position": 100, "mode_flags": 0}


def test_hvac_air_quality_payload_3110_parity() -> None:
    # Arrange
    raw_hex = "00C8"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = HvacAirQualityPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.air_quality_aqi == 200
    assert reencoded == raw_hex
    assert as_dict == {"air_quality_aqi": 200}


def test_hvac_fault_status_payload_4e01_parity() -> None:
    # Arrange
    raw_hex = "0000"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = HvacFaultStatusPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.fault_code == 0
    assert payload.flags == 0
    assert reencoded == raw_hex
    assert as_dict == {"fault_code": 0, "flags": 0}


def test_system_clock_payload_0001_parity() -> None:
    # Arrange
    raw_hex = "000C1E0001"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = SystemClockPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.hour == 12
    assert payload.minute == 30
    assert payload.second == 0
    assert payload.day_of_week == 1
    assert reencoded == raw_hex
    assert as_dict == {
        "hour": 12,
        "minute": 30,
        "second": 0,
        "day_of_week": 1,
    }


def test_system_date_payload_0002_parity() -> None:
    # Arrange
    raw_hex = "001A0807"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = SystemDatePayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.year == 26
    assert payload.month == 8
    assert payload.day == 7
    assert reencoded == raw_hex
    assert as_dict == {"year": 26, "month": 8, "day": 7}


def test_opentherm_status_payload_0150_parity() -> None:
    # Arrange
    raw_hex = "0100"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = OpenthermStatusPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.master_status == 1
    assert payload.slave_status == 0
    assert reencoded == raw_hex
    assert as_dict == {"master_status": 1, "slave_status": 0}


def test_opentherm_setpoint_payload_1098_parity() -> None:
    # Arrange
    raw_hex = "1388"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = OpenthermSetpointPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.setpoint_temp == 50.0
    assert reencoded == raw_hex
    assert as_dict == {"setpoint_temp": 50.0}


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


def test_relay_demand_payload_0008_parity() -> None:
    # Arrange
    raw_hex = "0064"
    raw_bytes = bytes.fromhex(raw_hex)
    from ramses_rf.payloads.heating import RelayDemandPayload

    # Act
    payload = RelayDemandPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.domain_or_zone_idx == 0
    assert payload.demand_percent == 0.5
    assert reencoded == raw_hex
    assert as_dict == {
        "domain_or_zone_idx": 0,
        "demand_percent": 0.5,
        "raw_extra": None,
    }


def test_relay_failsafe_payload_0009_parity() -> None:
    # Arrange
    raw_hex = "0001"
    raw_bytes = bytes.fromhex(raw_hex)
    from ramses_rf.payloads.system import RelayFailsafePayload

    # Act
    payload = RelayFailsafePayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.domain_or_zone_idx == 0
    assert payload.failsafe_enabled is True
    assert reencoded == raw_hex
    assert as_dict == {"domain_or_zone_idx": 0, "failsafe_enabled": True}


def test_window_state_payload_12b0_parity() -> None:
    # Arrange
    raw_hex = "000100"
    raw_bytes = bytes.fromhex(raw_hex)
    from ramses_rf.payloads.hvac import WindowStatePayload

    # Act
    payload = WindowStatePayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.zone_idx == 0
    assert payload.window_open is True
    assert reencoded == raw_hex
    assert as_dict == {"zone_idx": 0, "window_open": True}


def test_return_temp_payload_3210_parity() -> None:
    # Arrange
    raw_hex = "001388"
    raw_bytes = bytes.fromhex(raw_hex)
    from ramses_rf.payloads.opentherm import ReturnTempPayload

    # Act
    payload = ReturnTempPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.return_temp == 50.0
    assert reencoded == raw_hex
    assert as_dict == {"return_temp": 50.0}


def test_relay_demand_payload_0008_jasper_13byte_parity() -> None:
    # Arrange
    raw_hex = "00640102030405060708090A0B"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = RelayDemandPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.domain_or_zone_idx == 0
    assert payload.demand_percent == 0.5
    assert payload.raw_extra == bytes.fromhex("0102030405060708090A0B")
    assert reencoded == raw_hex
    assert as_dict["raw_extra"] == bytes.fromhex("0102030405060708090A0B")


def test_system_sync_payload_1030_mixvalve_parity() -> None:
    # Arrange
    raw_hex = "0AC80137C9010FCA0196CB0100"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = SystemSyncPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.sync_flag == 10
    assert payload.max_flow_setpoint == 55
    assert payload.min_flow_setpoint == 15
    assert payload.valve_run_time == 150
    assert payload.pump_run_time == 0
    assert reencoded == raw_hex
    assert as_dict["max_flow_setpoint"] == 55
    assert as_dict["min_flow_setpoint"] == 15
    assert as_dict["valve_run_time"] == 150
    assert as_dict["pump_run_time"] == 0


def test_spider_thermostat_payload_01ff_na_sentinel_parity() -> None:
    # Arrange
    raw_hex = "00807F8046"
    raw_bytes = bytes.fromhex(raw_hex)
    from ramses_rf.payloads.hvac import SpiderThermostatPayload

    # Act
    payload = SpiderThermostatPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.temp is None
    assert payload.setpoint_min is None
    assert payload.setpoint_max == 35.0
    assert reencoded == "00807F7F46"
    assert as_dict == {"temp": None, "setpoint_min": None, "setpoint_max": 35.0}


def test_system_fault_log_payload_0418_parity() -> None:
    # Arrange
    raw_hex = "0000010000"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = SystemFaultLogPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.log_idx == 0
    assert payload.log_data == bytes.fromhex("00010000")
    assert reencoded == raw_hex
    assert as_dict == {"log_idx": 0, "log_data": b"\x00\x01\x00\x00"}


def test_system_config_payload_2e04_parity() -> None:
    # Arrange
    raw_hex = "0000"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = SystemConfigPayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.config_idx == 0
    assert payload.config_val == 0
    assert reencoded == raw_hex
    assert as_dict == {"config_idx": 0, "config_val": 0}


def test_zone_config_payload_000a_array_parity() -> None:
    # Arrange
    raw_hex = "081001F409C4091001F409C40A1001F409C40B1001F409C4"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payloads = ZoneConfigPayload.from_bytes(raw_bytes)
    assert isinstance(payloads, list)
    reencoded = b"".join(p.to_bytes() for p in payloads).hex().upper()
    as_dicts = [payload_to_dict(p) for p in payloads]

    # Assert
    assert len(payloads) == 4
    assert reencoded == raw_hex
    assert as_dicts[0] == {
        "zone_idx": 8,
        "zone_flags": 16,
        "min_temp": 5.0,
        "max_temp": 25.0,
    }


def test_hvac_fan_param_payload_2411_22byte_parity() -> None:
    # Arrange
    raw_hex = "00000100000000003200000000000000FF0000000120"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = HvacFanParamPayload.from_bytes(raw_bytes)
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.param_id == 1
    assert payload.value_scaled == 50
    assert as_dict["param_id"] == 1
    assert as_dict["value_scaled"] == 50


def test_schedule_fragment_payload_0404_parity() -> None:
    # Arrange
    raw_hex = (
        "0120000829010368816DCCC91183301005D1D93428200E1C7D720C04402C0442640E8200"
        "0C851701ADD3AFAED1131151"
    )
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = ScheduleSwitchpointPayload.from_bytes(raw_bytes)
    assert isinstance(payload, ScheduleFragmentPayload)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.zone_idx == 1
    assert payload.frag_number == 1
    assert payload.total_frags == 3
    assert reencoded == raw_hex
    assert as_dict == {
        "zone_idx": 1,
        "frag_number": 1,
        "total_frags": 3,
        "fragment_bytes": bytes.fromhex(
            "68816DCCC91183301005D1D93428200E1C7D720C04402C0442640E82000C851701ADD3AFAED1131151"
        ),
    }


def test_hvac_filter_change_payload_10d0_reset_parity() -> None:
    # Arrange
    raw_hex = "00FF"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = HvacFilterChangePayload.from_bytes(raw_bytes)
    reencoded = payload.to_bytes().hex().upper()
    as_dict = payload_to_dict(payload)

    # Assert
    assert payload.reset_counter is True
    assert reencoded == raw_hex
    assert as_dict == {
        "remaining_days": None,
        "days_lifetime": None,
        "remaining_percent": None,
        "reset_counter": True,
    }


def test_complete_payload_registry_coverage() -> None:
    # Arrange & Act
    known_codes = [
        getattr(tx_const.Code, a)
        for a in dir(tx_const.Code)
        if a.startswith("_") and len(a) == 5
    ]
    aliases = ["2E10", "313E"]
    all_expected = known_codes + aliases

    # Assert
    for code in all_expected:
        assert code in PAYLOAD_REGISTRY, f"Opcode {code} missing from PAYLOAD_REGISTRY"
    assert len(PAYLOAD_REGISTRY._registry) == 108
