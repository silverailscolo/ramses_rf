"""Unit tests for MessageStore and entity state management in ramses_rf.state."""

import asyncio
from datetime import datetime as dt, timedelta as td
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from ramses_rf.messages import Message
from ramses_rf.routing import RoutingContext, StateHeader
from ramses_rf.state import EntityState, MessageStore
from ramses_tx import Code, Packet
from ramses_tx.const import I_


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
    mock_dev.id = "04:123456_00"

    mock_gwy = MagicMock()
    mock_gwy.message_store = MagicMock()
    mock_gwy.message_store.log_by_dtm = []

    entity = EntityState(mock_dev, mock_gwy)
    entity._current_state = {}
    return entity


def test_message_store_initialization() -> None:
    """Verify MessageStore initializes cleanly with memory state_cache."""
    store = MessageStore(maintain=False)
    assert store.state_cache == {}


def test_message_store_state_cache_indexing() -> None:
    """Verify header indexing and lookups in MessageStore state_cache."""
    store = MessageStore(maintain=False)
    hdr = StateHeader.create("1F09", " I", "01:123456", "00")
    mock_msg = MagicMock()
    mock_msg.dtm.isoformat.return_value = "2023-01-01T12:00:00.000000"

    store._state_cache[hdr] = mock_msg

    assert hdr in store.state_cache
    assert store.state_cache[hdr] == mock_msg


@pytest.mark.asyncio
async def test_o1_push_model_ingest(zone_entity: EntityState) -> None:
    """Verify the O(1) push model correctly caches on ingest."""
    msg = DummyMsg(
        "04:123456",
        Code._30C9,
        {"temperature": 21.0, "zone_idx": "00"},
    )

    zone_entity.update_state(msg)

    expected_hdr = StateHeader.create(Code._30C9, I_, "04:123456", False)
    assert expected_hdr in zone_entity._current_state
    assert zone_entity._current_state[expected_hdr] == msg


@pytest.mark.asyncio
async def test_o1_get_value_eliminates_cpu_thrashing(
    zone_entity: EntityState,
) -> None:
    """Proving the O(N^2) CPU bug is eradicated."""
    packet_count = 5000

    for _ in range(packet_count - 1):
        noise_msg = DummyMsg(
            "04:123456",
            Code._30C9,
            {"temperature": 19.0, "zone_idx": "00"},
        )
        zone_entity.update_state(noise_msg)

    final_msg = DummyMsg(
        "04:123456",
        Code._30C9,
        {"temperature": 21.0, "zone_idx": "00"},
    )
    zone_entity.update_state(final_msg)
    final_msg.payload_access_count = 0

    result = await zone_entity.get_value(Code._30C9)

    assert result == {"temperature": 21.0}
    assert final_msg.payload_access_count == 1


@pytest.mark.asyncio
async def test_expired_message_deletion_queued_once(
    zone_entity: EntityState,
) -> None:
    """Verify that an expired message only queues a DB deletion task once."""
    msg = DummyMsg(
        "04:123456",
        Code._30C9,
        {"temperature": 21.0, "zone_idx": "00"},
    )
    msg._expired = True

    zone_entity.update_state(msg)

    mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
    mock_loop.create_task = MagicMock(side_effect=lambda coro: coro.close())
    cast(Any, zone_entity._gateway)._loop = mock_loop

    await zone_entity.get_value(Code._30C9)
    await zone_entity.get_value(Code._30C9)
    await zone_entity.get_value(Code._30C9)

    assert msg.state_header in zone_entity._pending_deletes
    mock_loop.create_task.assert_called_once()


class TestMessageStore:
    """Test MessageStore class."""

    _SRC1 = "32:166025"
    _SRC2 = "01:087939"
    _NONA = "--:------"
    _NOW = dt.now().replace(microsecond=0)

    msg1: Message = Message._from_pkt(
        Packet(
            _NOW,
            "...  I --- 32:166025 --:------ 32:166025 1298 003 007FFF",
        )
    )
    msg2: Message = Message._from_pkt(
        Packet(
            _NOW + td(seconds=10),
            "...  I --- 32:166025 --:------ 32:166025 1298 003 001230",
        )
    )
    msg3: Message = Message._from_pkt(
        Packet(
            _NOW + td(seconds=20),
            "060  I --- 01:087939 --:------ 01:087939 2309 021 "
            "0007D00106400201F40301F40401F40501F40601F4",
        )
    )
    msg4: Message = Message._from_pkt(
        Packet(
            _NOW + td(seconds=30),
            "060  I --- 32:166025 --:------ 32:166025 31DA 030 "
            "00EF00019E00EF06E17FFF08020766BE09001F000000000000"
            "8500850000",
        )
    )
    msg5: Message = Message._from_pkt(
        Packet(
            _NOW + td(seconds=40),
            "...  I --- 04:189078 --:------ 01:145038 3150 002 0100",
        )
    )
    msg6: Message = Message._from_pkt(
        Packet(
            _NOW + td(seconds=50),
            "061 RP --- 10:078099 01:087939 --:------ 3220 005 00C0110000",
        )
    )
    msg7: Message = Message._from_pkt(
        Packet(
            _NOW + td(seconds=60),
            "...  I --- 04:189078 --:------ 01:145038 12B0 003 040000",
        )
    )

    async def test_add_msg(self) -> None:
        """Add a message to the MessageStore."""
        msg_db = MessageStore(disk_path=None)

        assert self.msg1.payload == {"co2_level": None}

        ret = msg_db.add(self.msg1)
        assert ret is None
        assert await msg_db.contains(code="1298")
        assert len(await msg_db.all()) == 1

        ret = msg_db.add(self.msg2)
        assert ret is None
        assert len(await msg_db.all()) == 2

        ret = msg_db.add(self.msg3)
        assert ret is None
        assert len(await msg_db.all()) == 3

        ret = msg_db.add(self.msg5)
        assert ret is None
        assert len(await msg_db.all()) == 4

        ret = msg_db.add(self.msg5)
        assert ret is None
        assert len(await msg_db.all()) == 4

        await msg_db.clr()
        assert len(await msg_db.all()) == 0
        msg_db.stop()

    async def test_qry_msg(self) -> None:
        """Query the MessageStore."""
        msg_db = MessageStore(disk_path=None)
        msg_db.add(self.msg1)
        msg_db.add(self.msg2)
        msg_db.add(self.msg3)
        msg_db.add(self.msg4)
        msg_db.add(self.msg5)
        msg_db.add(self.msg6)

        assert await msg_db.contains(code="2309")
        assert await msg_db.contains(code="3150")
        assert await msg_db.contains(src="01:087939", dst="01:087939", code="2309")
        assert not await msg_db.contains(src="01:12345", code="2309")
        assert not await msg_db.contains(code="1234")
        assert await msg_db.contains(dst="01:087939")

        res = await msg_db.get(src=self._SRC2)
        assert len(res) == 1
        assert res[0].code == Code._2309

        res = await msg_db.get(dst=self._SRC2)
        assert len(res) == 2
        assert res[0].code == Code._2309
        assert res[1].code == Code._3220

        res = await msg_db.get(src=self._SRC1)
        assert len(res) == 3
        assert res[0].code == Code._1298
        assert res[1].code == Code._1298
        assert res[2].code == Code._31DA

        res = await msg_db.get(src="04:189078")
        assert len(res) == 1
        assert res[0].code == Code._3150

        assert len(await msg_db.all()) == 6

        msg_db.add(self.msg7)
        res = await msg_db.get(src="04:189078")
        assert len(res) == 2

        msg_db.stop()

    async def test_rem_msg(self) -> None:
        """Remove a message from the MessageStore."""
        msg_db = MessageStore(disk_path=None)
        msg_db.add(self.msg1)
        msg_db.add(self.msg2)
        msg_db.add(self.msg3)

        assert len(await msg_db.all()) == 3

        await msg_db.rem(msg=self.msg1)
        assert len(await msg_db.all()) == 2
        assert not await msg_db.contains(dtm=self.msg1.dtm)

        await msg_db.rem(code="2309")
        assert len(await msg_db.all()) == 1
        assert not await msg_db.contains(code="2309")

        msg_db.stop()

    async def test_fat_database_payload_serialization(self) -> None:
        """Verify large payloads decode properly from the RAM cache."""
        msg_db = MessageStore(maintain=False, disk_path=None)
        msg_db.add(self.msg4)

        res = await msg_db.get(code="31DA")
        assert len(res) == 1
        assert res[0].payload == self.msg4.payload

        msg_db.stop()
