"""Unit tests for Command intents and builders in ramses_rf.commands."""

import pytest

from ramses_rf.address import Address
from ramses_rf.commands.builders.dhw import build_get_dhw_params, build_set_dhw_params
from ramses_rf.commands.core import Command
from ramses_rf.enums import Action
from ramses_tx.const import RQ, Code


def test_command_dataclass_creation() -> None:
    """Verify Command initialization, getters, and immutability with with_data."""
    # Arrange
    src = Address("01:123456")
    dst = Address("04:111111")
    cmd = Command(
        src=src,
        dst=dst,
        action=Action.GET_DHW_PARAMS,
        data={"dhw_idx": "00"},
    )

    # Act & Assert
    assert cmd.src == src
    assert cmd.dst == dst
    assert cmd.get("dhw_idx") == "00"
    assert cmd.get("missing_key", "default") == "default"

    new_cmd = cmd.with_data(setpoint=55.0)
    assert new_cmd is not cmd
    assert new_cmd.get("setpoint") == 55.0
    assert new_cmd.get("dhw_idx") == "00"


def test_build_get_dhw_params_builder() -> None:
    """Verify build_get_dhw_params produces valid CommandDTO."""
    # Arrange
    cmd = Command(
        src=Address("01:123456"),
        dst=Address("01:123456"),
        action=Action.GET_DHW_PARAMS,
        data={"dhw_idx": "00"},
    )

    # Act
    dto = build_get_dhw_params(cmd)

    # Assert
    assert dto.verb == RQ
    assert dto.code == Code._10A0
    assert dto.payload == "00"


def test_build_set_dhw_params_range_validation() -> None:
    """Verify setpoint, overrun, and differential range checks in set_dhw_params."""
    # Arrange
    cmd_invalid = Command(
        src=Address("01:123456"),
        dst=Address("01:123456"),
        action=Action.SET_DHW_PARAMS,
        data={"setpoint": 100.0},  # Invalid > 85.0
    )

    # Act & Assert
    with pytest.raises(ValueError, match="Out of range, setpoint"):
        build_set_dhw_params(cmd_invalid)
