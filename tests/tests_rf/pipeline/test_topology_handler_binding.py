"""RAMSES RF - Unit Tests for BindTopologyHandler."""

from unittest.mock import MagicMock

from ramses_rf.const import I_, Code
from ramses_rf.enums import TopologyAction
from ramses_rf.messages.core import Message
from ramses_rf.models import TopologyChangedEvent
from ramses_rf.pipeline.topology_handlers.binding import BindTopologyHandler
from ramses_tx import Address


def test_bind_handler_evohome_controller_broadcast() -> None:
    # Arrange
    events: list[TopologyChangedEvent] = []
    handler = BindTopologyHandler(emit_event_cb=events.append, enable_eavesdrop=True)

    mock_header = MagicMock()
    mock_header.code = Code._1F09
    mock_header.verb = I_

    msg = MagicMock(spec=Message)
    msg.header = mock_header
    msg.src = Address("01:123456")

    # Act
    handler.consume(msg)

    # Assert
    assert len(events) == 1
    assert events[0].action == TopologyAction.CREATE_CONTROLLER
    assert events[0].device_id == "01:123456"
    assert events[0].causation == "Rule_Evohome_Controller_Broadcast"


def test_bind_handler_000c_zone_binding() -> None:
    # Arrange
    events: list[TopologyChangedEvent] = []
    handler = BindTopologyHandler(emit_event_cb=events.append, enable_eavesdrop=False)

    mock_header = MagicMock()
    mock_header.code = Code._000C
    mock_header.verb = I_

    payload = [
        {
            "zone_idx": "00",
            "device_role": "04",
            "zone_type": "00",
            "devices": ["04:111111"],
        }
    ]

    msg = MagicMock(spec=Message)
    msg.header = mock_header
    msg.src = Address("01:123456")
    msg.data = payload

    # Act
    handler.consume(msg)

    # Assert
    assert len(events) == 1
    assert events[0].action == TopologyAction.BIND_DEVICE
    assert events[0].parent_id == "01:123456"
    assert events[0].child_id == "04:111111"
    assert events[0].metadata["zone_idx"] == "00"
    assert events[0].causation == "Rule_000C_Zone_Binding"
