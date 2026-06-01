"""Tests for the Phase 2.75 cross-domain enumerations."""

from ramses_rf.enums import Action, Topic


def test_topic_enum_values() -> None:
    """Verify Topic enum has correct string values for routing."""
    assert Topic.RAW_EVENT.value == "raw_event"
    assert Topic.STATE_UPDATE.value == "state_update"
    assert Topic.TOPOLOGY_DISCOVERY.value == "topology_discovery"


def test_action_enum_values() -> None:
    """Verify Action enum has correct string values for intents."""
    assert Action.SET_TEMPERATURE.value == "set_temperature"
    assert Action.SET_MODE.value == "set_mode"
