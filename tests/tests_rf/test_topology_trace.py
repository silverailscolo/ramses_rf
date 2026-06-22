"""RAMSES RF - Isolated trace testing for the Topology Builder."""

from datetime import datetime as dt

import pytest

from ramses_rf.address import Address
from ramses_rf.enums import Topic
from ramses_rf.messages.core import Message
from ramses_rf.models import TopologyChangedEvent
from ramses_rf.pipeline.topology_builder import TopologyBuilder
from ramses_rf.routing import StateHeader
from ramses_tx.const import Code


@pytest.mark.asyncio
async def test_trace_ufh_000C_binding() -> None:
    """Trace UFC 02:007533 broadcasting its circuit map."""
    events: list[TopologyChangedEvent] = []

    def mock_emit(event: TopologyChangedEvent) -> None:
        events.append(event)

    builder = TopologyBuilder(emit_event_cb=mock_emit, enable_eavesdrop=True)

    # Simulate UFC 000C payload (List of dicts)
    payload = [{"ufh_idx": "00", "zone_idx": "0B"}]
    hdr = StateHeader.create(Code._000C, " I", "02:007533", "00")

    msg = Message(
        topic=Topic.RAW_EVENT,
        header=hdr,
        src=Address("02:007533"),
        dst=Address("01:195932"),
        data={"_array": payload},
        packets=(),
        timestamp=dt.now(),
    )

    await builder.consume(msg)

    print("\n\n=== TRACE: UFH BINDING ===")
    for e in events:
        print(f"Action:   {e.action}")
        print(f"Parent:   {e.parent_id}")
        print(f"Child:    {e.child_id}")
        print(f"Metadata: {e.metadata}")
        print(f"Rule:     {e.causation}\n")

    assert len(events) > 0, "UFC Rule failed to emit any events!"


@pytest.mark.asyncio
async def test_trace_trv_3150_directed_telemetry() -> None:
    """Trace TRV 04:034726 sending heat demand to the OpenTherm controller."""
    events: list[TopologyChangedEvent] = []

    def mock_emit(event: TopologyChangedEvent) -> None:
        events.append(event)

    builder = TopologyBuilder(emit_event_cb=mock_emit, enable_eavesdrop=True)

    # Simulate TRV 3150 directed telemetry payload
    payload = {"domain_id": "02", "heat_demand": 0.0}
    hdr = StateHeader.create(Code._3150, " I", "04:034726", "02")

    msg = Message(
        topic=Topic.RAW_EVENT,
        header=hdr,
        src=Address("04:034726"),
        dst=Address("01:216136"),
        data=payload,
        packets=(),
        timestamp=dt.now(),
    )

    await builder.consume(msg)

    print("\n\n=== TRACE: DIRECTED TELEMETRY (TRV) ===")
    for e in events:
        print(f"Action:   {e.action}")
        print(f"Parent:   {e.parent_id}")
        print(f"Child:    {e.child_id}")
        print(f"Metadata: {e.metadata}")
        print(f"Rule:     {e.causation}\n")

    assert len(events) > 0, "Directed Telemetry Rule failed to emit any events!"
