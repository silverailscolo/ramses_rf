"""Unit and parity tests for RAMSES RF command builders and PayloadBase.hex()."""

from ramses_rf.address import Address
from ramses_rf.commands.builders import dhw, heat, opentherm, schedules, zones
from ramses_rf.commands.core import Command
from ramses_rf.enums import Action
from ramses_rf.payloads.dhw import DhwParams6BPayload, DhwParamsPayload
from ramses_tx.const import I_, RQ, W_, Code


def test_build_set_dhw_params_parity() -> None:
    """Verify build_set_dhw_params generates correct hex payload via DhwParamsPayload."""
    # Arrange
    cmd = Command(
        src=Address("01:123456"),
        dst=Address("01:123456"),
        action=Action.SET_DHW_PARAMS,
        data={"dhw_idx": "00", "setpoint": 50.0, "overrun": 5, "differential": 1.0},
    )

    # Act
    dto = dhw.build_set_dhw_params(cmd)

    # Assert
    assert dto.verb == W_
    assert dto.code == Code._10A0
    assert dto.payload == "001388050064"


def test_dhw_params_payload_roundtrip() -> None:
    """Verify DhwParamsPayload binary serialization, deserialization, and hex parity."""

    # Arrange
    raw_hex = "001388050064"
    raw_bytes = bytes.fromhex(raw_hex)

    # Act
    payload = DhwParamsPayload.from_bytes(raw_bytes)

    # Assert
    assert isinstance(payload, DhwParams6BPayload)
    assert payload.dhw_index == 0
    assert payload.setpoint == 50.0
    assert payload.overrun == 5
    assert payload.differential == 1.0
    assert payload.to_bytes() == raw_bytes
    assert payload.hex() == raw_hex


def test_build_put_dhw_temp_parity() -> None:
    """Verify build_put_dhw_temp generates correct hex payload via DhwTempPayload."""
    # Arrange
    cmd = Command(
        src=Address("07:123456"),
        dst=Address("07:123456"),
        action=Action.PUT_DHW_TEMP,
        data={"dhw_idx": "00", "temperature": 45.0},
    )

    # Act
    dto = dhw.build_put_dhw_temp(cmd)

    # Assert
    assert dto.verb == I_
    assert dto.code == Code._1260
    assert dto.payload == "001194"


def test_build_put_outdoor_temp_parity() -> None:
    """Verify build_put_outdoor_temp generates correct hex payload via TemperaturePayload."""
    # Arrange
    cmd = Command(
        src=Address("18:123456"),
        dst=Address("01:654321"),
        action=Action.PUT_OUTDOOR_TEMP,
        data={"temperature": 15.5},
    )

    # Act
    dto = heat.build_put_outdoor_temp(cmd)

    # Assert
    assert dto.verb == I_
    assert dto.code == Code._0002
    assert dto.payload == "00060E"


def test_build_put_sensor_temp_parity() -> None:
    """Verify build_put_sensor_temp generates correct hex payload via TemperaturePayload."""
    # Arrange
    cmd = Command(
        src=Address("01:123456"),
        dst=Address("01:123456"),
        action=Action.PUT_SENSOR_TEMP,
        data={"zone_idx": "01", "temperature": 21.0},
    )

    # Act
    dto = heat.build_put_sensor_temp(cmd)

    # Assert
    assert dto.verb == I_
    assert dto.code == Code._30C9
    assert dto.payload == "010834"


def test_build_set_temperature_parity() -> None:
    """Verify build_set_temperature generates correct hex payload via ZoneSetpointPayload."""
    # Arrange
    cmd = Command(
        src=Address("01:123456"),
        dst=Address("01:123456"),
        action=Action.SET_TEMPERATURE,
        data={"zone_idx": "02", "setpoint": 20.0},
    )

    # Act
    dto = zones.build_set_temperature(cmd)

    # Assert
    assert dto.verb == W_
    assert dto.code == Code._2309
    assert dto.payload == "0207D0"


def test_build_get_opentherm_data_parity() -> None:
    """Verify build_get_opentherm_data generates correct OpenThermMsgPayload hex."""
    # Arrange
    cmd = Command(
        src=Address("18:123456"),
        dst=Address("10:654321"),
        action=Action.GET_OPENTHERM_DATA,
        data={"msg_id": 25},
    )

    # Act
    dto = opentherm.build_get_opentherm_data(cmd)

    # Assert
    assert dto.verb == RQ
    assert dto.code == Code._3220
    assert dto.payload.startswith("00")
    assert len(dto.payload) == 10


def test_build_get_schedule_fragment_parity() -> None:
    """Verify build_get_schedule_fragment generates correct ScheduleFragmentPayload hex."""
    # Arrange
    cmd = Command(
        src=Address("01:123456"),
        dst=Address("01:123456"),
        action=Action.GET_SCHEDULE_FRAGMENT,
        data={"zone_idx": "01", "frag_number": 1, "total_frags": 0},
    )

    # Act
    dto = schedules.build_get_schedule_fragment(cmd)

    # Assert
    assert dto.verb == RQ
    assert dto.code == Code._0404
    assert dto.payload == "01200008000100"


def test_build_set_mode_parity() -> None:
    """Verify build_set_mode generates correct ZoneModePayload hex."""
    # Arrange
    cmd = Command(
        src=Address("01:123456"),
        dst=Address("01:123456"),
        action=Action.SET_MODE,
        data={"zone_idx": "00", "mode": 0, "setpoint": 21.0},
    )

    # Act
    dto = zones.build_set_mode(cmd)

    # Assert
    assert dto.verb == W_
    assert dto.code == Code._2349
    assert dto.payload == "00083400FFFFFF"


def test_build_set_name_parity() -> None:
    """Verify build_set_name generates correct ZoneNamePayload hex."""
    # Arrange
    cmd = Command(
        src=Address("01:123456"),
        dst=Address("01:123456"),
        action=Action.SET_ZONE_NAME,
        data={"zone_idx": "00", "name": "Lounge"},
    )

    # Act
    dto = zones.build_set_name(cmd)

    # Assert
    assert dto.verb == W_
    assert dto.code == Code._0004
    assert dto.payload == "00004C6F756E67650000000000000000000000000000"


def test_build_set_config_parity() -> None:
    """Verify build_set_config generates correct ZoneConfigPayload hex."""
    # Arrange
    cmd = Command(
        src=Address("01:123456"),
        dst=Address("01:123456"),
        action=Action.SET_ZONE_CONFIG,
        data={
            "zone_idx": "00",
            "min_temp": 5.0,
            "max_temp": 35.0,
            "local_override": False,
            "openwindow_function": False,
            "multiroom_mode": False,
        },
    )

    # Act
    dto = zones.build_set_config(cmd)

    # Assert
    assert dto.verb == W_
    assert dto.code == Code._000A
    assert dto.payload == "001301F40DAC"
