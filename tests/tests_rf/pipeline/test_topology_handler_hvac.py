"""RAMSES RF - Unit Tests for HvacTopologyHandler."""

from unittest.mock import MagicMock

from ramses_rf.const import I_, Code, DevType
from ramses_rf.enums import TopologyAction
from ramses_rf.messages.core import Message
from ramses_rf.models import TopologyChangedEvent
from ramses_rf.pipeline.topology_handlers.hvac import HvacTopologyHandler
from ramses_tx import Address


def test_hvac_handler_promotes_source_device_class() -> None:
    # Arrange
    events: list[TopologyChangedEvent] = []
    handler = HvacTopologyHandler(
        emit_event_cb=events.append, enable_eavesdrop=True
    )

    mock_header = MagicMock()
    mock_header.verb = I_
    mock_header.code = Code._31D9

    msg = MagicMock(spec=Message)
    msg.header = mock_header
    msg.src = Address("32:123456")
    msg.dst = Address("--:------")

    # Act
    handler.consume(msg)

    # Assert
    assert len(events) >= 1
    assert events[0].action == TopologyAction.UPDATE_DEVICE_CLASS
    assert events[0].device_id == "32:123456"
    assert events[0].metadata["device_class"] == DevType.FAN
    assert events[0].causation == "Rule_HVAC_Signature_Source"
