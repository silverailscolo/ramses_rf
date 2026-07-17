from datetime import datetime as dt

from ramses_rf.address import Address
from ramses_rf.commands.builders import build_dto
from ramses_rf.commands.core import Command
from ramses_rf.enums import Action
from ramses_tx.command import Command as LegacyCommand


def test_build_set_temperature() -> None:
    # 1. Legacy builder
    legacy_cmd = LegacyCommand.set_zone_setpoint("01:111111", "00", 21.0)

    # 2. New intent
    intent = Command(
        src=Address("18:000730"),
        dst=Address("01:111111"),
        action=Action.SET_TEMPERATURE,
        data={"zone_idx": 0, "setpoint": 21.0},
    )

    # 3. Translate to DTO
    dto = build_dto(intent)

    # 4. Compare parity
    assert dto.verb == legacy_cmd.verb
    assert dto.code == legacy_cmd.code
    assert dto.payload == legacy_cmd.payload
    # legacy_cmd has `addr0`, `addr1`, `addr2`.
    # addr0 is from_id. addr1 is dest_id. addr2 is NON_DEV_ADDR if from != dest.
    # We compare addr1/addr2/addr3 of DTO with the legacy addressing.
    assert dto.addr1 == legacy_cmd._addrs[0].id
    assert dto.addr2 == legacy_cmd._addrs[1].id
    assert dto.addr3 == legacy_cmd._addrs[2].id


def test_build_set_mode() -> None:
    # 1. Legacy builder
    legacy_cmd = LegacyCommand.set_zone_mode("01:111111", "00", mode=4, setpoint=15.0)

    # 2. New intent
    intent = Command(
        src=Address("18:000730"),
        dst=Address("01:111111"),
        action=Action.SET_MODE,
        data={
            "zone_idx": 0,
            "mode": 4,
            "setpoint": 15.0,
            "until": None,
            "duration": None,
        },
    )

    # 3. Translate to DTO
    dto = build_dto(intent)

    # 4. Compare parity
    assert dto.verb == legacy_cmd.verb
    assert dto.code == legacy_cmd.code
    assert dto.payload == legacy_cmd.payload
    assert dto.addr1 == legacy_cmd._addrs[0].id
    assert dto.addr2 == legacy_cmd._addrs[1].id
    assert dto.addr3 == legacy_cmd._addrs[2].id


def test_build_get_dhw_params() -> None:
    legacy_cmd = LegacyCommand.get_dhw_params("01:111111", dhw_idx=0)
    intent = Command(
        src=Address("18:000730"),
        dst=Address("01:111111"),
        action=Action.GET_DHW_PARAMS,
        data={"dhw_idx": 0},
    )
    dto = build_dto(intent)
    assert dto.verb == legacy_cmd.verb
    assert dto.code == legacy_cmd.code
    assert dto.payload == legacy_cmd.payload
    assert dto.addr1 == legacy_cmd._addrs[0].id
    assert dto.addr2 == legacy_cmd._addrs[1].id
    assert dto.addr3 == legacy_cmd._addrs[2].id


def test_build_set_dhw_params() -> None:
    legacy_cmd = LegacyCommand.set_dhw_params(
        "01:111111", setpoint=55.0, overrun=8, differential=2, dhw_idx=0
    )
    intent = Command(
        src=Address("18:000730"),
        dst=Address("01:111111"),
        action=Action.SET_DHW_PARAMS,
        data={
            "dhw_idx": 0,
            "setpoint": 55.0,
            "overrun": 8,
            "differential": 2,
        },
    )
    dto = build_dto(intent)
    assert dto.verb == legacy_cmd.verb
    assert dto.code == legacy_cmd.code
    assert dto.payload == legacy_cmd.payload
    assert dto.addr1 == legacy_cmd._addrs[0].id
    assert dto.addr2 == legacy_cmd._addrs[1].id
    assert dto.addr3 == legacy_cmd._addrs[2].id


def test_build_get_dhw_temp() -> None:
    legacy_cmd = LegacyCommand.get_dhw_temp("01:111111", dhw_idx=0)
    intent = Command(
        src=Address("18:000730"),
        dst=Address("01:111111"),
        action=Action.GET_DHW_TEMP,
        data={"dhw_idx": 0},
    )
    dto = build_dto(intent)
    assert dto.verb == legacy_cmd.verb
    assert dto.code == legacy_cmd.code
    assert dto.payload == legacy_cmd.payload
    assert dto.addr1 == legacy_cmd._addrs[0].id
    assert dto.addr2 == legacy_cmd._addrs[1].id
    assert dto.addr3 == legacy_cmd._addrs[2].id


def test_build_put_dhw_temp() -> None:
    legacy_cmd = LegacyCommand.put_dhw_temp("07:111111", temperature=50.5, dhw_idx=0)
    intent = Command(
        src=Address("07:111111"),
        dst=Address("07:111111"),
        action=Action.PUT_DHW_TEMP,
        data={"dhw_idx": 0, "temperature": 50.5},
    )
    dto = build_dto(intent)
    assert dto.verb == legacy_cmd.verb
    assert dto.code == legacy_cmd.code
    assert dto.payload == legacy_cmd.payload
    assert dto.addr1 == legacy_cmd._addrs[0].id
    assert dto.addr2 == legacy_cmd._addrs[1].id
    assert dto.addr3 == legacy_cmd._addrs[2].id


def test_build_get_dhw_mode() -> None:
    legacy_cmd = LegacyCommand.get_dhw_mode("01:111111", dhw_idx=0)
    intent = Command(
        src=Address("18:000730"),
        dst=Address("01:111111"),
        action=Action.GET_DHW_MODE,
        data={"dhw_idx": 0},
    )
    dto = build_dto(intent)
    assert dto.verb == legacy_cmd.verb
    assert dto.code == legacy_cmd.code
    assert dto.payload == legacy_cmd.payload
    assert dto.addr1 == legacy_cmd._addrs[0].id
    assert dto.addr2 == legacy_cmd._addrs[1].id
    assert dto.addr3 == legacy_cmd._addrs[2].id


def test_build_set_dhw_mode() -> None:
    now = dt.now()
    legacy_cmd = LegacyCommand.set_dhw_mode(
        "01:111111", mode=4, active=True, until=now, dhw_idx=0
    )
    intent = Command(
        src=Address("18:000730"),
        dst=Address("01:111111"),
        action=Action.SET_DHW_MODE,
        data={
            "dhw_idx": 0,
            "mode": 4,
            "active": True,
            "until": now,
            "duration": None,
        },
    )
    dto = build_dto(intent)
    assert dto.verb == legacy_cmd.verb
    assert dto.code == legacy_cmd.code
    assert dto.payload == legacy_cmd.payload
    assert dto.addr1 == legacy_cmd._addrs[0].id
    assert dto.addr2 == legacy_cmd._addrs[1].id
    assert dto.addr3 == legacy_cmd._addrs[2].id


def test_build_put_co2_level() -> None:
    legacy_cmd = LegacyCommand.put_co2_level("32:111111", 400.0)
    intent = Command(
        src=Address("32:111111"),
        dst=Address("32:111111"),
        action=Action.PUT_CO2_LEVEL,
        data={"co2_level": 400.0},
    )
    dto = build_dto(intent)
    assert dto.verb == legacy_cmd.verb
    assert dto.code == legacy_cmd.code
    assert dto.payload == legacy_cmd.payload
    assert dto.addr1 == legacy_cmd._addrs[0].id
    assert dto.addr2 == legacy_cmd._addrs[1].id
    assert dto.addr3 == legacy_cmd._addrs[2].id


def test_build_put_indoor_humidity() -> None:
    legacy_cmd = LegacyCommand.put_indoor_humidity("32:111111", 0.5)
    intent = Command(
        src=Address("32:111111"),
        dst=Address("32:111111"),
        action=Action.PUT_INDOOR_HUMIDITY,
        data={"indoor_humidity": 0.5},
    )
    dto = build_dto(intent)
    assert dto.verb == legacy_cmd.verb
    assert dto.code == legacy_cmd.code
    assert dto.payload == legacy_cmd.payload
    assert dto.addr1 == legacy_cmd._addrs[0].id
    assert dto.addr2 == legacy_cmd._addrs[1].id
    assert dto.addr3 == legacy_cmd._addrs[2].id


def test_build_set_fan_mode() -> None:
    legacy_cmd = LegacyCommand.set_fan_mode(
        "32:111111", fan_mode="low", scheme="itho", src_id="18:000730"
    )
    intent = Command(
        src=Address("18:000730"),
        dst=Address("32:111111"),
        action=Action.SET_FAN_MODE,
        data={"fan_mode": "low", "scheme": "itho"},
    )
    dto = build_dto(intent)
    assert dto.verb == legacy_cmd.verb
    assert dto.code == legacy_cmd.code
    assert dto.payload == legacy_cmd.payload
    assert dto.addr1 == legacy_cmd._addrs[0].id
    assert dto.addr2 == legacy_cmd._addrs[1].id
    assert dto.addr3 == legacy_cmd._addrs[2].id


def test_build_set_bypass_position() -> None:
    legacy_cmd = LegacyCommand.set_bypass_position(
        "32:111111", bypass_mode="auto", src_id="18:000730"
    )
    intent = Command(
        src=Address("18:000730"),
        dst=Address("32:111111"),
        action=Action.SET_BYPASS_POSITION,
        data={"bypass_mode": "auto"},
    )
    dto = build_dto(intent)
    assert dto.verb == legacy_cmd.verb
    assert dto.code == legacy_cmd.code
    assert dto.payload == legacy_cmd.payload
    assert dto.addr1 == legacy_cmd._addrs[0].id
    assert dto.addr2 == legacy_cmd._addrs[1].id
    assert dto.addr3 == legacy_cmd._addrs[2].id


def test_build_get_fan_param() -> None:
    legacy_cmd = LegacyCommand.get_fan_param("32:111111", "31", src_id="18:000730")
    intent = Command(
        src=Address("18:000730"),
        dst=Address("32:111111"),
        action=Action.GET_FAN_PARAM,
        data={"param_id": "31"},
    )
    dto = build_dto(intent)
    assert dto.verb == legacy_cmd.verb
    assert dto.code == legacy_cmd.code
    assert dto.payload == legacy_cmd.payload
    assert dto.addr1 == legacy_cmd._addrs[0].id
    assert dto.addr2 == legacy_cmd._addrs[1].id
    assert dto.addr3 == legacy_cmd._addrs[2].id


def test_build_set_fan_param() -> None:
    legacy_cmd = LegacyCommand.set_fan_param("32:111111", "31", 30, src_id="18:000730")
    intent = Command(
        src=Address("18:000730"),
        dst=Address("32:111111"),
        action=Action.SET_FAN_PARAM,
        data={"param_id": "31", "value": 30},
    )
    dto = build_dto(intent)
    assert dto.verb == legacy_cmd.verb
    assert dto.code == legacy_cmd.code
    assert dto.payload == legacy_cmd.payload
    assert dto.addr1 == legacy_cmd._addrs[0].id
    assert dto.addr2 == legacy_cmd._addrs[1].id
    assert dto.addr3 == legacy_cmd._addrs[2].id
