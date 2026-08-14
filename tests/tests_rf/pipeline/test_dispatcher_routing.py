"""RAMSES RF - Dispatcher parity and routing rules tests."""

import asyncio
from datetime import datetime as dt

import pytest

from ramses_rf.address import Address
from ramses_rf.enums import Topic
from ramses_rf.messages.core import Message
from ramses_rf.pipeline.dispatcher import CentralDispatcher
from ramses_rf.routing import StateHeader
from ramses_tx.dtos import PacketDTO


def _mock_message(
    src_id: str,
    dst_id: str,
    code: str,
    data: dict[str, str],
) -> Message:
    """Create a mock frozen L7 Message for routing tests."""
    dto = PacketDTO(
        timestamp=dt.now(),
        rssi="-70",
        verb=" I",
        seq="000",
        addr1=src_id,
        addr2=dst_id,
        addr3="--:------",
        code=code,
        length="000",
        payload="00",
    )
    mock_header = StateHeader.create(
        code=code, verb=" I", source_id=src_id, context_val=None
    )
    return Message(
        topic=Topic.RAW_EVENT,
        header=mock_header,
        src=Address(src_id),
        dst=Address(dst_id),
        data=data,
        packets=(dto,),
        timestamp=dto.timestamp,
    )


@pytest.mark.asyncio
async def test_dispatcher_standard_routing() -> None:
    """Prove standard 30C9 messages route only to SSOT and Discovery."""
    in_q: asyncio.Queue[Message] = asyncio.Queue()
    dispatcher = CentralDispatcher(in_q)
    await dispatcher.start()

    msg = _mock_message("01:123456", "01:123456", "30C9", {"temp": "21.0"})
    in_q.put_nowait(msg)
    await in_q.join()
    await dispatcher.stop()

    assert dispatcher.ssot_queue.qsize() == 1
    assert dispatcher.discovery_queue.qsize() == 1
    assert dispatcher.binding_queue.qsize() == 0
    assert dispatcher.faked_queue.qsize() == 0


@pytest.mark.asyncio
async def test_dispatcher_binding_offer_routing() -> None:
    """Prove 1FC9 binding offers correctly bypass standard faked routing."""
    in_q: asyncio.Queue[Message] = asyncio.Queue()
    dispatcher = CentralDispatcher(in_q)
    await dispatcher.start()

    msg = _mock_message("04:111111", "04:111111", "1FC9", {"phase": "offer"})
    in_q.put_nowait(msg)
    await in_q.join()
    await dispatcher.stop()

    assert dispatcher.ssot_queue.qsize() == 1
    assert dispatcher.discovery_queue.qsize() == 1
    assert dispatcher.binding_queue.qsize() == 1
    assert dispatcher.faked_queue.qsize() == 0


@pytest.mark.asyncio
async def test_dispatcher_global_broadcast_routing() -> None:
    """Prove 63:262142 global broadcasts are intercepted for virtualization."""
    in_q: asyncio.Queue[Message] = asyncio.Queue()
    dispatcher = CentralDispatcher(in_q)
    await dispatcher.start()

    msg = _mock_message("01:123456", "63:262142", "10E0", {})
    in_q.put_nowait(msg)
    await in_q.join()
    await dispatcher.stop()

    assert dispatcher.ssot_queue.qsize() == 1
    assert dispatcher.discovery_queue.qsize() == 1
    assert dispatcher.binding_queue.qsize() == 0
    assert dispatcher.faked_queue.qsize() == 1


@pytest.mark.asyncio
async def test_dispatcher_directed_faked_routing() -> None:
    """Prove directed commands (src != dst) are pushed to the faked queue."""
    in_q: asyncio.Queue[Message] = asyncio.Queue()
    dispatcher = CentralDispatcher(in_q)
    await dispatcher.start()

    msg = _mock_message("01:123456", "04:654321", "2309", {})
    in_q.put_nowait(msg)
    await in_q.join()
    await dispatcher.stop()

    assert dispatcher.ssot_queue.qsize() == 1
    assert dispatcher.discovery_queue.qsize() == 1
    assert dispatcher.binding_queue.qsize() == 0
    assert dispatcher.faked_queue.qsize() == 1
