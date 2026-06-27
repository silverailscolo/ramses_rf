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


def create_dto(
    verb: str,
    code: str,
    payload: str,
    timestamp: dt,
    *,
    addr1: str = "01:158182",
) -> PacketDTO:
    """Helper to generate mock PacketDTOs for testing."""
    return PacketDTO(
        timestamp=timestamp,
        rssi="-70",
        verb=verb,
        seq="000",
        addr1=addr1,
        addr2="--:------",
        addr3=addr1,
        code=code,
        length=f"{len(payload) // 2:03d}",
        payload=payload,
    )


@pytest.mark.asyncio
async def test_passthrough_normal_packet(base_time: dt) -> None:
    """Test that a non-array packet passes through immediately."""
    # Arrange
    in_q: asyncio.Queue[PacketDTO] = asyncio.Queue()
    out_q: asyncio.Queue[PacketDTO] = asyncio.Queue()
    buffer = ReassemblyBuffer(in_q, out_q)
    await buffer.start()
    # Send a normal temperature packet (30C9)
    normal_pkt = create_dto(" I", "30C9", "0001C8", base_time)

    # Act
    await in_q.put(normal_pkt)
    out_pkt = await asyncio.wait_for(out_q.get(), timeout=1.0)

    # Assert
    # It should appear in the output queue immediately
    assert out_pkt.code == "30C9"
    assert out_pkt.payload == "0001C8"

    await buffer.stop()


@pytest.mark.asyncio
async def test_successful_stitching(base_time: dt) -> None:
    """Test that two valid fragments are stitched into one."""
    # Arrange
    in_q: asyncio.Queue[PacketDTO] = asyncio.Queue()
    out_q: asyncio.Queue[PacketDTO] = asyncio.Queue()
    buffer = ReassemblyBuffer(in_q, out_q)
    await buffer.start()

    # Send the first fragment (000A)
    frag1 = create_dto(" I", "000A", "001201F409C4", base_time)
    # Send the second fragment 1 second later
    time_2 = base_time + td(seconds=1)
    frag2 = create_dto(" I", "000A", "081001F409C4", time_2)

    # Act
    await in_q.put(frag1)
    # Assert it is buffered (queue remains empty)
    is_empty_after_frag1 = out_q.empty()

    await in_q.put(frag2)
    # Receive the stitched packet
    out_pkt = await asyncio.wait_for(out_q.get(), timeout=1.0)

    # Assert
    assert is_empty_after_frag1 is True
    assert out_pkt.code == "000A"
    assert out_pkt.payload == "001201F409C4081001F409C4"
    assert out_pkt.length == "012"
    assert out_pkt.timestamp == time_2

    await buffer.stop()


@pytest.mark.asyncio
async def test_timeout_flush(base_time: dt) -> None:
    """Test that a buffered packet is flushed if no fragment arrives."""
    # Arrange
    in_q: asyncio.Queue[PacketDTO] = asyncio.Queue()
    out_q: asyncio.Queue[PacketDTO] = asyncio.Queue()
    # Inject a tiny 0.1s timeout for testing speed
    buffer = ReassemblyBuffer(in_q, out_q, array_timeout=0.1)
    await buffer.start()
    # Send the first fragment
    frag1 = create_dto(" I", "000A", "001201F4", base_time)

    # Act
    await in_q.put(frag1)
    # Wait just past our injected 0.1s timeout for the flush to happen
    out_pkt = await asyncio.wait_for(out_q.get(), timeout=0.2)

    # Assert
    # We should get the unmodified original packet back
    assert out_pkt.payload == "001201F4"

    await buffer.stop()


@pytest.mark.asyncio
async def test_unrelated_packet_does_not_abort_reassembly(
    base_time: dt,
) -> None:
    """An unrelated packet passes through without flushing a pending array.

    This is the core sliding-window behaviour from issue #669: an
    intervening packet (RF noise, or a broadcast from a different
    device/code) must NOT abort an in-flight array reassembly. The
    unrelated packet is emitted immediately and the pending fragment is
    preserved for its matching peer.
    """
    # Arrange
    in_q: asyncio.Queue[PacketDTO] = asyncio.Queue()
    out_q: asyncio.Queue[PacketDTO] = asyncio.Queue()
    buffer = ReassemblyBuffer(in_q, out_q)
    await buffer.start()

    # Send the first fragment of a 000A array
    frag1 = create_dto(" I", "000A", "001201F4", base_time)
    # An unrelated 30C9 packet arrives between the two fragments
    unrelated = create_dto(" I", "30C9", "0001C8", base_time + td(seconds=1))
    # The second 000A fragment now arrives and completes the array
    frag2 = create_dto(" I", "000A", "081001F409C4", base_time + td(seconds=2))

    # Act
    await in_q.put(frag1)
    # The pending fragment is buffered, nothing emitted yet
    is_empty_after_frag1 = out_q.empty()

    await in_q.put(unrelated)
    # The unrelated packet passes straight through immediately...
    out_pkt_unrelated = await asyncio.wait_for(out_q.get(), timeout=1.0)
    # ...and the 000A fragment is STILL buffered (not flushed)
    is_empty_after_unrelated = out_q.empty()

    await in_q.put(frag2)
    out_pkt_stitched = await asyncio.wait_for(out_q.get(), timeout=1.0)

    # Assert
    assert is_empty_after_frag1 is True

    assert out_pkt_unrelated.code == "30C9"
    assert out_pkt_unrelated.payload == "0001C8"
    assert is_empty_after_unrelated is True

    assert out_pkt_stitched.code == "000A"
    assert out_pkt_stitched.payload == "001201F4081001F409C4"
    assert out_pkt_stitched.length == "010"

    await buffer.stop()


@pytest.mark.asyncio
async def test_concurrent_arrays_from_different_sources(base_time: dt) -> None:
    """Two arrays from different sources reassemble in parallel.

    The sliding window keys pending arrays by (src_id, code), so
    fragments from two distinct devices interleaved over the radio must
    each stitch with their own peer rather than aborting one another.
    """
    # Arrange
    in_q: asyncio.Queue[PacketDTO] = asyncio.Queue()
    out_q: asyncio.Queue[PacketDTO] = asyncio.Queue()
    buffer = ReassemblyBuffer(in_q, out_q)
    await buffer.start()

    # Device A starts an array
    frag_a1 = create_dto(" I", "000A", "001201F4", base_time, addr1="01:158182")
    # Device B starts an array (same code, different src) before A completes
    frag_b1 = create_dto(
        " I", "000A", "00AA00BB", base_time + td(seconds=1), addr1="01:223036"
    )
    # Device A's second fragment arrives
    frag_a2 = create_dto(
        " I", "000A", "081001F409C4", base_time + td(seconds=2), addr1="01:158182"
    )
    # Device B's second fragment arrives
    frag_b2 = create_dto(
        " I", "000A", "0810AABBCC", base_time + td(seconds=3), addr1="01:223036"
    )

    # Act
    await in_q.put(frag_a1)
    await in_q.put(frag_b1)
    # Neither is emitted yet: both are buffered concurrently
    is_empty_after_first_frags = out_q.empty()

    await in_q.put(frag_a2)
    out_a = await asyncio.wait_for(out_q.get(), timeout=1.0)

    await in_q.put(frag_b2)
    out_b = await asyncio.wait_for(out_q.get(), timeout=1.0)

    # Assert
    assert is_empty_after_first_frags is True

    assert out_a.addr1 == "01:158182"
    assert out_a.payload == "001201F4081001F409C4"

    assert out_b.addr1 == "01:223036"
    assert out_b.payload == "00AA00BB0810AABBCC"

    await buffer.stop()


@pytest.mark.asyncio
async def test_timeout_flushes_all_pending(base_time: dt) -> None:
    """A timeout flushes every pending array, not just a single slot."""
    # Arrange
    in_q: asyncio.Queue[PacketDTO] = asyncio.Queue()
    out_q: asyncio.Queue[PacketDTO] = asyncio.Queue()
    buffer = ReassemblyBuffer(in_q, out_q, array_timeout=0.1)
    await buffer.start()

    # Two unrelated pending arrays from different sources
    frag_a = create_dto(" I", "000A", "001201F4", base_time, addr1="01:158182")
    frag_b = create_dto(" I", "000A", "00AA00BB", base_time, addr1="01:223036")

    # Act
    await in_q.put(frag_a)
    await in_q.put(frag_b)

    # Both should be flushed after the timeout
    flushed: list[PacketDTO] = []
    for _ in range(2):
        flushed.append(await asyncio.wait_for(out_q.get(), timeout=0.5))

    # Assert
    flushed_codes = sorted(p.addr1 for p in flushed)
    assert flushed_codes == ["01:158182", "01:223036"]
    for p in flushed:
        assert p.code == "000A"

    await buffer.stop()
