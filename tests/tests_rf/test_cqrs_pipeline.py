"""
Automated execution tracer for the NEW ramses_rf CQRS/Event-Driven architecture.

This script instantiates the new asynchronous queue pipeline in total isolation
from the legacy Gateway God Object. It injects PacketDTOs and monitors the
SSOT and Discovery Queues to verify the new L7 domain logic.
"""

import asyncio
from datetime import datetime as dt
from typing import Any, Final

import pytest

from ramses_rf.models import TopologyChangedEvent
from ramses_rf.pipeline.decoder import DecoderEngine
from ramses_rf.pipeline.dispatcher import CentralDispatcher
from ramses_rf.pipeline.topology_builder import TopologyBuilder
from ramses_tx.dtos import PacketDTO

# 1. 3150 Heat Demand
PKT_3150: Final = PacketDTO(
    timestamp=dt.now(),
    rssi="-64",
    verb=" I",
    seq="---",
    addr1="01:145038",
    addr2="--:------",
    addr3="01:145038",
    code="3150",
    length="002",
    payload="FCC8",
)

# 2. 30C9 Orphan TRV
PKT_30C9_TRV: Final = PacketDTO(
    timestamp=dt.now(),
    rssi="-64",
    verb=" I",
    seq="---",
    addr1="04:023226",
    addr2="--:------",
    addr3="04:023226",
    code="30C9",
    length="003",
    payload="000834",
)

# 3. 3220 OpenTherm RP
PKT_3220_RP: Final = PacketDTO(
    timestamp=dt.now(),
    rssi="-65",
    verb="RP",
    seq="---",
    addr1="10:067219",
    addr2="01:078710",
    addr3="--:------",
    code="3220",
    length="005",
    payload="00C00500FF",
)


@pytest.mark.asyncio
async def test_new_async_pipeline() -> None:
    """Test the standalone Async L7 Pipeline."""

    # 1. Instantiate the Queue boundaries
    raw_rx_queue: asyncio.Queue[PacketDTO] = asyncio.Queue()
    decoded_queue: asyncio.Queue[Any] = asyncio.Queue()

    # 2. Instantiate the Pipeline Engines
    decoder = DecoderEngine(raw_rx_queue, decoded_queue)
    dispatcher = CentralDispatcher(decoded_queue)

    # 3. Hook the TopologyBuilder to intercept its events
    emitted_events: list[TopologyChangedEvent] = []

    def _mock_emit(event: TopologyChangedEvent) -> None:
        emitted_events.append(event)
        target = event.device_id or event.child_id
        print(
            f"    -> [TOPOLOGY BUILDER] Action: {event.action} | Target: {target} | Rule: {event.causation}"
        )

    topology = TopologyBuilder(emit_event_cb=_mock_emit, enable_eavesdrop=True)

    # 4. Start the background tasks
    await decoder.start()
    await dispatcher.start()

    # 5. Create Mock Consumers for the Dispatcher Output Queues
    async def _consume_ssot() -> None:
        while True:
            msg = await dispatcher.ssot_queue.get()
            # Safely extract the L3 code from the underlying packet tuple
            l3_code = msg.packets[0].code if msg.packets else "UNKNOWN"
            print(
                f"    -> [SSOT QUEUE] Fact Logged -> Code: {l3_code} | Src: {msg.src.id} | DataKeys: {list(msg.data.keys())}"
            )
            dispatcher.ssot_queue.task_done()

    async def _consume_discovery() -> None:
        while True:
            msg = await dispatcher.discovery_queue.get()
            await topology.consume(msg)
            dispatcher.discovery_queue.task_done()

    ssot_task = asyncio.create_task(_consume_ssot())
    disc_task = asyncio.create_task(_consume_discovery())

    try:
        print("\n\n=== NEW PIPELINE: INJECTING 3150 HEAT DEMAND ===")
        raw_rx_queue.put_nowait(PKT_3150)
        await asyncio.sleep(0.1)  # Allow queues to drain

        print("\n=== NEW PIPELINE: INJECTING 30C9 ORPHAN TRV ===")
        raw_rx_queue.put_nowait(PKT_30C9_TRV)
        await asyncio.sleep(0.1)

        print("\n=== NEW PIPELINE: INJECTING 3220 OPENTHERM ===")
        raw_rx_queue.put_nowait(PKT_3220_RP)
        await asyncio.sleep(0.1)

    finally:
        # Clean shutdown
        await decoder.stop()
        await dispatcher.stop()
        ssot_task.cancel()
        disc_task.cancel()
