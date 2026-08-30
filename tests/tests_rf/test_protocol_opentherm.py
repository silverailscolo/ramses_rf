"""Unit tests for OpenTherm protocol mapping models and dictionaries."""

from ramses_rf.protocol.opentherm import (
    OPENTHERM_TO_RAMSES_MAP,
    RAMSES_TO_OPENTHERM_MAP,
    OtDataId,
)
from ramses_tx.const import Code


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
