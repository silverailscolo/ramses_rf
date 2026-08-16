"""RAMSES RF - Unit Tests for UfhTopologyHandler."""

from unittest.mock import MagicMock

from ramses_rf.const import SZ_UFH_INDEX, SZ_ZONE_INDEX
from ramses_rf.enums import TopologyAction
from ramses_rf.messages.core import Message
from ramses_rf.models import TopologyChangedEvent
from ramses_rf.pipeline.topology_handlers.ufh import UfhTopologyHandler
from ramses_tx import Address
from ramses_tx.const import Code


def test_ufh_handler_creates_circuit_event_on_000c() -> None:
    # Arrange
    events: list[TopologyChangedEvent] = []
    handler = UfhTopologyHandler(
        emit_event_cb=events.append, enable_eavesdrop=False
    )

    mock_header = MagicMock()
    mock_header.code = Code._000C

    payload = [{SZ_UFH_INDEX: "01", SZ_ZONE_INDEX: "02"}]

    msg = MagicMock(spec=Message)
    msg.header = mock_header
    msg.src = Address("02:048122")
    msg.data = payload

    # Act
    handler.consume(msg)

    # Assert
    assert len(events) == 1
    assert events[0].action == TopologyAction.CREATE_CIRCUIT
    assert events[0].device_id == "02:048122"
    assert events[0].metadata["ufh_index"] == "01"
    assert events[0].metadata["zone_index"] == "02"
    assert events[0].causation == "Rule_UFH_000C_Circuit"


def test_ufh_handler_conversational_binding() -> None:
    # Arrange
    events: list[TopologyChangedEvent] = []
    handler = UfhTopologyHandler(
        emit_event_cb=events.append, enable_eavesdrop=True
    )

    mock_header = MagicMock()
    mock_header.code = Code._3150

    msg = MagicMock(spec=Message)
    msg.header = mock_header
    msg.src = Address("01:123456")
    msg.dst = Address("02:048122")
    msg.addr3 = Address("--:------")

    # Act
    handler.consume(msg)

    # Assert
    assert len(events) == 2
    assert events[0].action == TopologyAction.UPDATE_DEVICE_CLASS
    assert events[0].device_id == "02:048122"
    assert events[1].action == TopologyAction.BIND_DEVICE
    assert events[1].parent_id == "01:123456"
    assert events[1].child_id == "02:048122"
