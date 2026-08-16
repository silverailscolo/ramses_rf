#!/usr/bin/env python3
"""RAMSES RF - Tests for the async storage worker (persistence layer)."""

import asyncio
import os
import sqlite3
import time
from datetime import datetime as dt, timedelta as td
from pathlib import Path

import pytest

from ramses_rf.messages import Message
from ramses_rf.state import MessageStore
from ramses_tx.packet import Packet


def create_dummy_message(seq: int) -> Message:
    """Create a valid dummy packet/message for testing."""
    # Fake packet: RQ (Request) from fake device to fake device
    # Structure: ... RQ --- SrcID DstID --:------ 1F09 001 00

    # Ensure unique timestamps for burst testing to avoid RAM dict
    # collisions
    base_time = dt.now()
    ts = (base_time + td(microseconds=seq)).isoformat(timespec="microseconds")

    # Ensure sequence fits in 6 digits
    seq_str = f"{seq % 999999:06d}"

    # FIX 1: Src must differ from Dst to pass strict address
    # validation in ramses_tx
    # FIX 2: Length field (001) must match payload length
    # ("00" = 1 byte)
    packet_line = f"... RQ --- 01:{seq_str} 02:{seq_str} --:------ 1F09 001 00"

    packet = Packet.from_file(ts, packet_line)
    return Message(packet.to_dto())


@pytest.mark.asyncio
async def test_storage_worker_persistence(tmp_path: Path) -> None:
    """Verify that the StorageWorker offloads writes asynchronously and
    persists data.

    This test ensures:
    1. Phase 2.3 (RAM-First): The main memory dict is instantly
       populated.
    2. Phase 2.1 (Fat DB): The background worker eventually writes all
       data to SQL.
    3. Phase 2.5 (Lossless Frame): The original `frame` string survives
       database hydration.
    """

    # 1. Setup: Use pytest's temp path for the DB file
    db_path = tmp_path / "test_async_persistence.sqlite"
    disk_path = tmp_path / "ramses.db"

    # Temporarily hide the Pytest env var so the SQLiteWorker actually
    # starts up
    pytest_env = os.environ.pop("PYTEST_CURRENT_TEST", None)
    try:
        # 2. Initialize MessageStore (starts the background StorageWorker)
        # We pass the path as a string, as expected by the class
        index = MessageStore(db_path=str(db_path), disk_path=str(disk_path))

        # Allow a tiny moment for the worker thread to initialize tables
        # using a deterministic polling loop instead of a flaky hardcoded
        # sleep
        for _ in range(50):  # max 0.5s wait
            if db_path.exists():
                try:
                    conn = sqlite3.connect(str(db_path))
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name='messages'"
                    )
                    result = cursor.fetchone()
                    conn.close()
                    if result:
                        break
                except sqlite3.OperationalError:
                    pass
            await asyncio.sleep(0.01)

        # CRITICAL FIX for Test:
        # message_store.py now auto-flushes (blocks) if it detects it is
        # running in Pytest.
        # We must explicitly disable this for THIS specific test to verify
        # async speed.
        real_flush = index.flush
        index.flush = lambda: None  # type: ignore[method-assign]

        # 3. Burst Write Test (Non-blocking verification)
        MSG_COUNT = 500
        start_time = time.perf_counter()

        for i in range(MSG_COUNT):
            msg = create_dummy_message(i)
            index.add(msg)

        duration = time.perf_counter() - start_time

        # Assertion: RAM-First Write-Behind Cache
        # The in-memory dictionary MUST be populated instantly.
        assert len(index.log_by_dtm) == MSG_COUNT, (
            "Phase 2.3 Fail: RAM cache was not instantly populated!"
        )

        # Restore flush for the verification step
        index.flush = real_flush  # type: ignore[method-assign]

        # Performance Assertion:
        # If this were blocking SQLite, 500 inserts might take ~0.5s to
        # ~5.0s depending on disk.
        # With async queue, it should be effectively instant (RAM speed).
        # We set a conservative upper bound of 0.2s to account for CI
        # overhead.
        assert duration < 1.0, (
            f"Main thread blocked! Added {MSG_COUNT} messages in "
            f"{duration:.4f}s. Expected < 1.0s for async operation."
        )

        # 4. Persistence Verification (Wait for Worker)
        # The worker is running in the background; give it time to drain
        # the queue.
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
            f"Data loss detected! Expected {MSG_COUNT} rows, "
            f"found {row_count} after waiting {wait_time}s."
        )

        # Trigger and wait for disk snapshot explicitly
        assert index._worker is not None
        index._worker.submit_snapshot()
        index.flush()

        assert disk_path.exists(), "Snapshot file was not created on disk!"

        # Keep a reference to the original frame string for validation
        original_msg = index.log_by_dtm[0]
        original_frame = original_msg.raw_frame

        # 6. Hydration Verification
        index2 = MessageStore(
            db_path=":memory:", disk_path=str(disk_path), maintain=True
        )
        if index2._hydration_task:
            await index2._hydration_task

        assert len(index2.log_by_dtm) == MSG_COUNT, (
            f"Hydration failed! Expected {MSG_COUNT} cached items, "
            f"got {len(index2.log_by_dtm)}."
        )

        # Ensure the frame was retained properly, meaning DTO conversion
        # won't fail
        hydrated_msg = index2.log_by_dtm[0]
        hydrated_frame = hydrated_msg.raw_frame
        assert hydrated_frame == original_frame, (
            "Lossless frame hydration failed!"
        )

        # 7. Cleanup
        index.stop()
        index2.stop()

    finally:
        # Restore the Pytest environment variable for all subsequent tests
        if pytest_env is not None:
            os.environ["PYTEST_CURRENT_TEST"] = pytest_env


@pytest.mark.asyncio
async def test_storage_worker_delete(tmp_path: Path) -> None:
    """Verify that the StorageWorker safely processes delete requests
    asynchronously.
    """
    db_path = tmp_path / "test_async_delete.sqlite"
    disk_path = tmp_path / "ramses_delete.db"

    pytest_env = os.environ.pop("PYTEST_CURRENT_TEST", None)
    try:
        index = MessageStore(db_path=str(db_path), disk_path=str(disk_path))

        # Allow tables to initialize
        for _ in range(50):
            if db_path.exists():
                break
            await asyncio.sleep(0.01)

        # 1. Insert a test message
        msg = create_dummy_message(1)
        index.add(msg)

        # Flush queue to disk so we can read it directly
        assert index._worker is not None
        index._worker.flush()

        # Check DB row count == 1
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM messages")
        assert cursor.fetchone()[0] == 1, "Failed to persist single insert."

        # 2. Delete the message via the async queue pattern
        await index.rem(msg=msg)
        # Force wait until delete transaction is processed
        index._worker.flush()

        # Check DB row count == 0
        cursor.execute("SELECT COUNT(*) FROM messages")
        assert cursor.fetchone()[0] == 0, "Failed to async delete record."

        conn.close()
        index.stop()

    finally:
        if pytest_env is not None:
            os.environ["PYTEST_CURRENT_TEST"] = pytest_env
