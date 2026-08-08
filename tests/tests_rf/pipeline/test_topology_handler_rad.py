"""RAMSES RF - Unit Tests for RadTopologyHandler."""

from unittest.mock import MagicMock

from ramses_rf.const import Code, DevType
from ramses_rf.enums import TopologyAction
from ramses_rf.messages.core import Message
from ramses_rf.models import TopologyChangedEvent
from ramses_rf.pipeline.topology_handlers.rad import RadTopologyHandler
from ramses_tx import Address


def test_rad_handler_heating_prefix_rules() -> None:
    # Arrange
    events: list[TopologyChangedEvent] = []
    handler = RadTopologyHandler(emit_event_cb=events.append, enable_eavesdrop=True)

    mock_header = MagicMock()
    mock_header.code = Code._30C9

    msg = MagicMock(spec=Message)
    msg.header = mock_header
    msg.src = Address("04:034726")
    msg.dst = Address("--:------")

    # Act
    handler.consume(msg)

    # Assert
    assert len(events) >= 1
    assert events[0].action == TopologyAction.UPDATE_DEVICE_CLASS
    assert events[0].device_id == "04:034726"
    assert events[0].metadata["device_class"] == DevType.TRV
    assert events[0].causation == "Rule_Heating_Prefix_Heuristic"
