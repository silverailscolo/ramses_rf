"""RAMSES RF - Unit Tests for DhwTopologyHandler."""

from unittest.mock import MagicMock

from ramses_rf.const import Code, DevType
from ramses_rf.enums import TopologyAction
from ramses_rf.messages.core import Message
from ramses_rf.models import TopologyChangedEvent
from ramses_rf.pipeline.topology_handlers.dhw import DhwTopologyHandler
from ramses_tx import Address


def test_dhw_handler_promotes_device_class_on_1260() -> None:
    # Arrange
    events: list[TopologyChangedEvent] = []
    handler = DhwTopologyHandler(emit_event_cb=events.append, enable_eavesdrop=True)

    mock_header = MagicMock()
    mock_header.code = Code._1260

    msg = MagicMock(spec=Message)
    msg.header = mock_header
    msg.src = Address("07:012345")

    # Act
    handler.consume(msg)

    # Assert
    assert len(events) == 1
    assert events[0].action == TopologyAction.UPDATE_DEVICE_CLASS
    assert events[0].device_id == "07:012345"
    assert events[0].metadata["device_class"] == DevType.DHW
    assert events[0].causation == "Rule_DHW_Signature"
