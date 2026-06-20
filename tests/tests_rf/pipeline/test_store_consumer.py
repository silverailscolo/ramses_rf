"""RAMSES RF - Dispatcher to MessageStore consumer parity tests."""

import asyncio
from datetime import datetime as dt

import pytest

from ramses_rf.address import Address
from ramses_rf.enums import Topic
from ramses_rf.messages.base import Message as LegacyMessage
from ramses_rf.messages.core import Message as CoreMessage
from ramses_rf.routing import StateHeader
from ramses_rf.state.store import MessageStore
from ramses_tx.dtos import PacketDTO


def _mock_message(
    src_id: str,
    dst_id: str,
    code: str,
    data: dict[str, str],
) -> CoreMessage:
    """Create a mock frozen L7 Message for consumer ingestion tests."""
    dto = PacketDTO(
        timestamp=dt.now(),
        rssi="-70",
        verb=" I",
        seq="000",
        addr1=src_id,
        addr2=dst_id,
        addr3="--:------",
        code=code,
        length="003",
        payload="0001C8",  # A realistic hex string to pass validation checks
    )
    mock_header = StateHeader.create(
        code=code, verb=" I", source_id=src_id, context_val=None
    )
    return CoreMessage(
        topic=Topic.RAW_EVENT,
        header=mock_header,
        src=Address(src_id),
        dst=Address(dst_id),
        data=data,
        packets=(dto,),
        timestamp=dto.timestamp,
    )


@pytest.mark.asyncio
async def test_store_queue_consumer() -> None:
    """Prove MessageStore natively ingests Messages from an asyncio.Queue."""
    # Initialize the SSOT store with background loops enabled
    store = MessageStore(maintain=True, db_path=":memory:")

    # Create the simulated CentralDispatcher ssot_queue
    ssot_queue: asyncio.Queue[CoreMessage] = asyncio.Queue()

    # Wire the SSOT to listen to the queue
    store.start_consumer(ssot_queue)

    # Drop a new state event onto the queue (e.g. from the Dispatcher)
    test_msg = _mock_message("01:123456", "01:123456", "30C9", {"temp": "21.0"})
    ssot_queue.put_nowait(test_msg)

    # Wait for the consumer task to empty the queue and process it
    await ssot_queue.join()

    # Stop the store cleanly to finalize DB queries and cancel async tasks
    store.stop()

    # Bridge the test validation back to the legacy state_header expectations
    legacy_msg = LegacyMessage(test_msg.packets[0])

    # Assert the message was successfully intercepted and added to the SSOT RAM Cache
    assert legacy_msg.state_header in store.state_cache
    cached_msg = store.state_cache[legacy_msg.state_header]
    assert cached_msg.payload == {"temp": "21.0"}
