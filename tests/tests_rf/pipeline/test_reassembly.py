"""Tests for the asynchronous packet reassembly buffer."""

import asyncio
from datetime import UTC, datetime as dt, timedelta as td

import pytest

from ramses_rf.pipeline.reassembly import ReassemblyBuffer
from ramses_tx.dtos import PacketDTO


@pytest.fixture
def base_time() -> dt:
    """Provide a stable base timestamp for tests."""
    return dt(2026, 5, 15, 12, 0, 0, tzinfo=UTC)


def create_dto(verb: str, code: str, payload: str, timestamp: dt) -> PacketDTO:
    """Helper to generate mock PacketDTOs for testing."""
    return PacketDTO(
        timestamp=timestamp,
        rssi="-70",
        verb=verb,
        seq="000",
        addr1="01:158182",
        addr2="--:------",
        addr3="01:158182",
        code=code,
        length=f"{len(payload) // 2:03d}",
        payload=payload,
    )


@pytest.mark.asyncio
async def test_passthrough_normal_packet(base_time: dt) -> None:
    """Test that a non-array packet passes through immediately."""
    in_q: asyncio.Queue[PacketDTO] = asyncio.Queue()
    out_q: asyncio.Queue[PacketDTO] = asyncio.Queue()
    buffer = ReassemblyBuffer(in_q, out_q)

    await buffer.start()

    # Send a normal temperature packet (30C9)
    normal_pkt = create_dto(" I", "30C9", "0001C8", base_time)
    await in_q.put(normal_pkt)

    # It should appear in the output queue immediately
    out_pkt = await asyncio.wait_for(out_q.get(), timeout=1.0)
    assert out_pkt.code == "30C9"
    assert out_pkt.payload == "0001C8"

    await buffer.stop()


@pytest.mark.asyncio
async def test_successful_stitching(base_time: dt) -> None:
    """Test that two valid fragments are stitched into one."""
    in_q: asyncio.Queue[PacketDTO] = asyncio.Queue()
    out_q: asyncio.Queue[PacketDTO] = asyncio.Queue()
    buffer = ReassemblyBuffer(in_q, out_q)

    await buffer.start()

    # Send the first fragment (000A)
    frag1 = create_dto(" I", "000A", "001201F409C4", base_time)
    await in_q.put(frag1)

    # Assert it is buffered (queue remains empty)
    assert out_q.empty()

    # Send the second fragment 1 second later
    time_2 = base_time + td(seconds=1)
    frag2 = create_dto(" I", "000A", "081001F409C4", time_2)
    await in_q.put(frag2)

    # Receive the stitched packet
    out_pkt = await asyncio.wait_for(out_q.get(), timeout=1.0)
    assert out_pkt.code == "000A"
    assert out_pkt.payload == "001201F409C4081001F409C4"
    assert out_pkt.length == "012"
    assert out_pkt.timestamp == time_2

    await buffer.stop()


@pytest.mark.asyncio
async def test_timeout_flush(base_time: dt) -> None:
    """Test that a buffered packet is flushed if no fragment arrives."""
    in_q: asyncio.Queue[PacketDTO] = asyncio.Queue()
    out_q: asyncio.Queue[PacketDTO] = asyncio.Queue()

    # Inject a tiny 0.1s timeout for testing speed
    buffer = ReassemblyBuffer(in_q, out_q, array_timeout=0.1)

    await buffer.start()

    # Send the first fragment
    frag1 = create_dto(" I", "000A", "001201F4", base_time)
    await in_q.put(frag1)

    # Wait just past our injected 0.1s timeout for the flush to happen
    out_pkt = await asyncio.wait_for(out_q.get(), timeout=0.2)

    # We should get the unmodified original packet back
    assert out_pkt.payload == "001201F4"

    await buffer.stop()


@pytest.mark.asyncio
async def test_interruption_flush(base_time: dt) -> None:
    """Test that an unrelated packet flushes the buffer."""
    in_q: asyncio.Queue[PacketDTO] = asyncio.Queue()
    out_q: asyncio.Queue[PacketDTO] = asyncio.Queue()
    buffer = ReassemblyBuffer(in_q, out_q)

    await buffer.start()

    # Send the first fragment
    frag1 = create_dto(" I", "000A", "001201F4", base_time)
    await in_q.put(frag1)

    # Send an unrelated packet immediately
    unrelated = create_dto(" I", "30C9", "0001C8", base_time)
    await in_q.put(unrelated)

    # First, we should receive the flushed fragment
    out_pkt_1 = await asyncio.wait_for(out_q.get(), timeout=1.0)
    assert out_pkt_1.code == "000A"
    assert out_pkt_1.payload == "001201F4"

    # Next, we should receive the unrelated packet
    out_pkt_2 = await asyncio.wait_for(out_q.get(), timeout=1.0)
    assert out_pkt_2.code == "30C9"
    assert out_pkt_2.payload == "0001C8"

    await buffer.stop()
