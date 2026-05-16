"""RAMSES RF - Golden Master parity test for async decoder engine."""

import asyncio
import re
from datetime import datetime as dt
from pathlib import Path
from typing import Any

import pytest

from ramses_rf.messages.base import Message as LegacyMessage
from ramses_rf.messages.core import Message as NewMessage
from ramses_rf.pipeline.decoder import DecoderEngine
from ramses_tx import exceptions as exc
from ramses_tx.dtos import PacketDTO

# Resolves to: tests/fixtures/regression_packets_sorted.txt
FIXTURE_PATH = (
    Path(__file__).parent.parent.parent / "fixtures" / "regression_packets_sorted.txt"
)

_PACKET_REGEX = re.compile(
    r"^(\S+)\s+(\S+)\s+(..)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)"
)


def _parse_line_to_dto(line: str) -> PacketDTO | None:
    """Parse a raw text line into a strict PacketDTO."""
    if "#" in line:
        line = line.split("#")[0]
    line = line.strip()
    if not line:
        return None

    match = _PACKET_REGEX.match(line)
    if not match:
        return None

    (
        dtm_str,
        rssi,
        verb,
        seq,
        addr1,
        addr2,
        addr3,
        code,
        length,
        payload,
    ) = match.groups()

    try:
        timestamp = dt.fromisoformat(dtm_str)
    except ValueError:
        timestamp = dt.now()

    return PacketDTO(
        timestamp=timestamp,
        rssi=rssi,
        verb=verb,
        seq=seq,
        addr1=addr1,
        addr2=addr2,
        addr3=addr3,
        code=code,
        length=length,
        payload=payload,
    )


@pytest.mark.asyncio
async def test_decoder_engine_parity() -> None:
    """Prove DecoderEngine matches legacy Message dictionary outputs."""
    if not FIXTURE_PATH.exists():
        pytest.skip(f"Fixture not found: {FIXTURE_PATH}")

    mid_q: asyncio.Queue[PacketDTO] = asyncio.Queue()
    out_q: asyncio.Queue[NewMessage] = asyncio.Queue()

    decoder = DecoderEngine(mid_q, out_q)
    await decoder.start()

    lines = FIXTURE_PATH.read_text().splitlines()
    expected_payloads: list[Any] = []

    for line in lines:
        dto = _parse_line_to_dto(line)
        if not dto:
            continue

        # 1. Capture the exact legacy payload
        try:
            legacy_msg = LegacyMessage(dto)
            expected_payloads.append(legacy_msg.payload)
        except exc.PacketInvalid:
            # The legacy system rejected it.
            # We skip adding it, expecting the new engine to perfectly drop it too.
            pass

        # 2. Push ALL DTOs into the new async engine
        mid_q.put_nowait(dto)

    # Allow the pipeline to finish processing
    await mid_q.join()
    await decoder.stop()

    actual_messages: list[NewMessage] = []
    while not out_q.empty():
        actual_messages.append(out_q.get_nowait())

    # This asserts that the new engine mathematically drops the exact
    # same number of invalid packets as the legacy engine did.
    assert len(actual_messages) == len(expected_payloads), (
        f"Mismatch: Expected {len(expected_payloads)}, got {len(actual_messages)}"
    )

    for i, (new_msg, old_payload) in enumerate(
        zip(actual_messages, expected_payloads, strict=True)
    ):
        # Normalize legacy array lists to the new strict L7 dict constraint
        expected_data = (
            {"_array": old_payload}
            if isinstance(old_payload, list)
            else dict(old_payload)
        )

        assert new_msg.data == expected_data, (
            f"Parity mismatch at valid line {i}: {new_msg.data} != {expected_data}"
        )
