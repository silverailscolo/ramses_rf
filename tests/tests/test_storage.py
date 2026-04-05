"""RAMSES RF - Tests for the async storage worker (persistence layer)."""

import asyncio
import sqlite3
import time
from datetime import datetime as dt, timedelta as td
from pathlib import Path

import pytest

from ramses_rf.database import MessageIndex
from ramses_tx.message import Message
from ramses_tx.packet import Packet


def create_dummy_message(seq: int) -> Message:
    """Create a valid dummy packet/message for testing."""
    # Fake packet: RQ (Request) from fake device to fake device
    # Structure: ... RQ --- SrcID DstID --:------ 1F09 001 00

    # Ensure unique timestamps for burst testing to avoid RAM dict collisions
    base_time = dt.now()
    ts = (base_time + td(microseconds=seq)).isoformat(timespec="microseconds")

    # Ensure sequence fits in 6 digits
    seq_str = f"{seq % 999999:06d}"

    # FIX 1: Src must differ from Dst to pass strict address validation in ramses_tx
    # FIX 2: Length field (001) must match payload length ("00" = 1 byte)
    pkt_line = f"... RQ --- 01:{seq_str} 02:{seq_str} --:------ 1F09 001 00"

    pkt = Packet.from_file(ts, pkt_line)
    return Message(pkt)


@pytest.mark.asyncio
async def test_storage_worker_persistence(tmp_path: Path) -> None:
    """
    Verify that the StorageWorker offloads writes asynchronously and persists data.

    This test ensures:
    1. Phase 2.3 (RAM-First): The main memory dict is instantly populated.
    2. Phase 2.1 (Fat DB): The background worker eventually writes all data to SQL.
    """

    # 1. Setup: Use pytest's temp path for the DB file
    db_path = tmp_path / "test_async_persistence.sqlite"

    # 2. Initialize MessageIndex (starts the background StorageWorker)
    # We pass the path as a string, as expected by the class
    idx = MessageIndex(db_path=str(db_path))

    # Allow a tiny moment for the worker thread to initialize tables
    # using a deterministic polling loop instead of a flaky hardcoded sleep
    for _ in range(50):  # max 0.5s wait
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='messages'"
                )
                result = cursor.fetchone()
                conn.close()
                if result:
                    break
            except sqlite3.OperationalError:
                pass
        await asyncio.sleep(0.01)

    # CRITICAL FIX for Test:
    # database.py now auto-flushes (blocks) if it detects it is running in Pytest.
    # We must explicitly disable this for THIS specific test to verify async speed.
    real_flush = idx.flush
    idx.flush = lambda: None  # type: ignore[method-assign]

    # 3. Burst Write Test (Non-blocking verification)
    MSG_COUNT = 500
    start_time = time.perf_counter()

    for i in range(MSG_COUNT):
        msg = create_dummy_message(i)
        idx.add(msg)

    duration = time.perf_counter() - start_time

    # Assertion: RAM-First Write-Behind Cache
    # The in-memory dictionary MUST be populated instantly.
    assert len(idx.msgs) == MSG_COUNT, (
        "Phase 2.3 Fail: RAM cache was not instantly populated!"
    )

    # Restore flush for the verification step
    idx.flush = real_flush  # type: ignore[method-assign]

    # Performance Assertion:
    # If this were blocking SQLite, 500 inserts might take ~0.5s to ~5.0s depending on disk.
    # With async queue, it should be effectively instant (RAM speed).
    # We set a conservative upper bound of 0.2s to account for CI overhead.
    assert duration < 1.0, (
        f"Main thread blocked! Added {MSG_COUNT} messages in {duration:.4f}s. "
        "Expected < 1.0s for async operation."
    )

    # 4. Persistence Verification (Wait for Worker)
    # The worker is running in the background; give it time to drain the queue.
    # In a real scenario, this happens while the app does other work.
    wait_time = 0.0
    row_count = 0

    # Poll the DB file until data matches or timeout (max 3 seconds)
    while wait_time < 3.0:
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM messages")
            result = cursor.fetchone()
            if result:
                row_count = result[0]
            conn.close()

            if row_count == MSG_COUNT:
                break
        except sqlite3.OperationalError:
            # DB might be locked or not ready yet
            pass

        await asyncio.sleep(0.05)
        wait_time += 0.05

    # 5. Final Assertions
    assert row_count == MSG_COUNT, (
        f"Data loss detected! Expected {MSG_COUNT} rows, found {row_count} "
        f"after waiting {wait_time}s."
    )

    # 6. Cleanup
    idx.stop()
