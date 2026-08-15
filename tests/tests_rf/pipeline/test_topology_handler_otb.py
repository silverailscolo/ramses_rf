"""RAMSES RF - Unit Tests for OtbTopologyHandler."""

from unittest.mock import MagicMock

from ramses_rf.const import Code, DevType
from ramses_rf.enums import TopologyAction
from ramses_rf.messages.core import Message
from ramses_rf.models import TopologyChangedEvent
from ramses_rf.pipeline.topology_handlers.otb import OtbTopologyHandler
from ramses_tx import Address


def test_otb_handler_promotes_device_class_on_3220() -> None:
    # Arrange
    events: list[TopologyChangedEvent] = []
    handler = OtbTopologyHandler(
        emit_event_cb=events.append, enable_eavesdrop=True
    )

    mock_header = MagicMock()
    mock_header.code = Code._3220

    msg = MagicMock(spec=Message)
    msg.header = mock_header
    msg.src = Address("10:067219")

    # Act
    handler.consume(msg)

    # Assert
    assert len(events) == 1
    assert events[0].action == TopologyAction.UPDATE_DEVICE_CLASS
    assert events[0].device_id == "10:067219"
    assert events[0].metadata["device_class"] == DevType.OTB
    assert events[0].causation == "Rule_OTB_3220_Signature"
