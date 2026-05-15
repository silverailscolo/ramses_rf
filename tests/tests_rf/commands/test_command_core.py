"""Tests for the Phase 2.75 immutable Command domain model."""

from uuid import UUID

from ramses_rf.address import Address
from ramses_rf.commands.core import Command
from ramses_rf.enums import Action


def test_command_initialization_and_uuid() -> None:
    """Verify Command assigns a native UUID and stores data."""
    src = Address("01:111111")
    dst = Address("04:222222")

    cmd = Command(
        src=src,
        dst=dst,
        action=Action.SET_TEMPERATURE,
        data={"setpoint": 21.5},
    )

    # Assert native UUID generation
    assert isinstance(cmd.correlation_id, UUID)
    # Assert default QoS parameters
    assert cmd.needs_reply is False
    assert cmd.timeout == 3.0


def test_command_get_safety_and_with_data() -> None:
    """Verify Command safe dictionary access and immutability."""
    cmd = Command(
        src=Address("01:111111"),
        dst=Address("04:222222"),
        action=Action.SET_MODE,
        data={"mode": "auto"},
    )

    # Verify safe .get() access
    assert cmd.get("mode") == "auto"
    assert cmd.get("missing_key", "default_val") == "default_val"

    # Verify .with_data() spawns a new instance
    new_cmd = cmd.with_data(mode="off", duration=60)

    assert new_cmd is not cmd
    assert new_cmd.data["mode"] == "off"
    assert new_cmd.data["duration"] == 60
    # Original should be untouched
    assert cmd.data["mode"] == "auto"
