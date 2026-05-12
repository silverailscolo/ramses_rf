from __future__ import annotations

from datetime import datetime as dt
from typing import Any
from unittest.mock import MagicMock

import pytest

from ramses_rf.routing import RoutingContext, StateHeader
from ramses_rf.state import EntityState
from ramses_tx.const import I_, Code


class DummyMsg:
    """A lightweight mock message to accurately track property accesses."""

    def __init__(self, src_id: str, code: Code, payload_dict: dict[str, Any]) -> None:
        self.src = MagicMock()
        self.src.id = src_id
        self.dst = MagicMock()
        self.dst.id = "01:000000"
        self.verb = I_
        self.code = code
        self.dtm = dt.now()

        self._pkt = MagicMock()
        self._pkt._ctx = False
        self._expired = False

        self._payload_dict = payload_dict
        self.payload_access_count = 0

        # NEW: Native L7 properties to satisfy the O(1) StateCache
        self.context = RoutingContext(False)
        self.state_header = StateHeader.create(
            self.code, self.verb, self.src.id, self.context.value
        )

    @property
    def payload(self) -> dict[str, Any]:
        """Track how many times the payload is evaluated."""
        self.payload_access_count += 1
        return self._payload_dict


@pytest.fixture
def zone_entity() -> EntityState:
    """Fixture to provide a standard mocked Zone EntityState."""
    mock_dev = MagicMock()
    mock_dev.id = "04:123456_00"  # _00 makes it a Zone

    mock_gwy = MagicMock()
    mock_gwy.message_store = MagicMock()
    mock_gwy.message_store.log_by_dtm = []

    # Inject our new O(1) state dictionary
    entity = EntityState(mock_dev, mock_gwy)
    entity._current_state = {}
    return entity


@pytest.mark.asyncio
async def test_o1_push_model_ingest(zone_entity: EntityState) -> None:
    """Step 1: Verify the O(1) push model correctly caches on ingest."""
    msg = DummyMsg(
        "04:123456",
        Code._30C9,
        {"temperature": 21.0, "zone_idx": "00"},
    )

    # Action: Simulate the Dispatcher pushing a newly arrived packet
    zone_entity.update_state(msg)

    # Assert: The dictionary holds the message under the new DTO
    expected_hdr = StateHeader.create(Code._30C9, I_, "04:123456", False)
    assert expected_hdr in zone_entity._current_state
    assert zone_entity._current_state[expected_hdr] == msg


@pytest.mark.asyncio
async def test_o1_get_value_eliminates_cpu_thrashing(
    zone_entity: EntityState,
) -> None:
    """Step 2: Proving the O(N^2) CPU bug is eradicated."""
    packet_count = 5000

    # Simulate a system that has ingested 5000 packets over time
    for _ in range(packet_count - 1):
        noise_msg = DummyMsg(
            "04:123456",
            Code._30C9,
            {"temperature": 19.0, "zone_idx": "00"},
        )
        zone_entity.update_state(noise_msg)

    # Ingest the final, most recent message
    final_msg = DummyMsg(
        "04:123456",
        Code._30C9,
        {"temperature": 21.0, "zone_idx": "00"},
    )
    zone_entity.update_state(final_msg)

    # Reset the access counter so we only measure the cost of the QUERY
    final_msg.payload_access_count = 0

    # Action: Query the state
    result = await zone_entity.get_value(Code._30C9)

    assert result == {"temperature": 21.0}

    # ASSERT THE BUG IS FIXED:
    # Instead of iterating 5000 times and accessing the payload 15,000 times,
    # the dictionary lookup ensures the payload is accessed strictly ONCE
    # (just to extract the final value to return to Home Assistant).
    assert final_msg.payload_access_count == 1


@pytest.mark.asyncio
async def test_expired_message_deletion_queued_once(zone_entity: EntityState) -> None:
    """Step 3: Verify that an expired message only queues a DB deletion task once.

    This ensures we do not flood the SQLite worker queue when Home Assistant
    repeatedly polls an entity that has an expired packet in its cache.
    """
    # 1. Setup an expired message
    msg = DummyMsg(
        "04:123456",
        Code._30C9,
        {"temperature": 21.0, "zone_idx": "00"},
    )
    msg._expired = True  # Flag it as expired (legacy mechanics)

    # Push it into the O(1) state cache
    zone_entity.update_state(msg)

    # 2. Mock the async event loop to intercept the database queueing
    mock_loop = MagicMock()
    zone_entity._gwy._loop = mock_loop  # type: ignore[attr-defined]

    # 3. Simulate Home Assistant polling the state multiple times (e.g., 3 state polls)
    await zone_entity.get_value(Code._30C9)
    await zone_entity.get_value(Code._30C9)
    await zone_entity.get_value(Code._30C9)

    # 4. Assertions
    # The boolean flag must be applied securely to the object
    assert getattr(msg, "_delete_task_queued", False) is True

    # CRITICAL: Even though HA polled 3 times, it should only create 1 deletion task!
    mock_loop.create_task.assert_called_once()

    # 5. Cleanup: Close the trapped coroutine to prevent Pytest RuntimeWarning
    coro = mock_loop.create_task.call_args[0][0]
    coro.close()
