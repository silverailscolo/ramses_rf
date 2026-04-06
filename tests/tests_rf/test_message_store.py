#!/usr/bin/env python3
"""RAMSES RF - Unit test for MessageIndex."""

from datetime import datetime as dt, timedelta as td

from ramses_rf.message_store import MessageIndex
from ramses_tx import Code, Message, Packet


class TestMessageIndex:
    """Test  MessageIndex class."""

    _SRC1 = "32:166025"
    _SRC2 = "01:087939"  # (CTR)
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
            "...  I --- 32:166025 --:------ 32:166025 1298 003 001230",  # co2_level
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
            "...  I --- 04:189078 --:------ 01:145038 3150 002 0100",  # heat_demand
        )
    )

    msg6: Message = Message._from_pkt(
        Packet(
            _NOW + td(seconds=50),
            "061 RP --- 10:078099 01:087939 --:------ 3220 005 00C0110000",  # OTB
        )
    )

    msg7: Message = Message._from_pkt(
        Packet(
            _NOW + td(seconds=60),
            "...  I --- 04:189078 --:------ 01:145038 12B0 003 040000",
        )
    )

    async def test_add_msg(self) -> None:
        """Add a message to the MessageIndex."""
        msg_db = MessageIndex(disk_path=None)
        ret: Message | None

        # add a message
        assert self.msg1.payload == {
            "co2_level": None,
        }, "unexpected parsed payload"

        ret = msg_db.add(self.msg1)  # replaced message

        assert ret is None
        assert await msg_db.contains(code="1298")
        assert len(await msg_db.all()) == 1

        # add another message with same code (different dtm adds to log, updates cache)
        ret = msg_db.add(self.msg2)

        assert ret is None  # Async add returns None, not the old msg
        assert len(await msg_db.all()) == 2

        # add another message with different code
        ret = msg_db.add(self.msg3)  # new code

        assert ret is None
        assert len(await msg_db.all()) == 3

        ret = msg_db.add(self.msg5)  # new code
        assert ret is None
        assert len(await msg_db.all()) == 4

        ret = msg_db.add(self.msg5)  # exact same dtm overwrites existing entry
        assert ret is None
        assert len(await msg_db.all()) == 4

        # test clear index
        await msg_db.clr()
        assert len(await msg_db.all()) == 0

        msg_db.stop()  # close sqlite3 connection

    async def test_qry_msg(self) -> None:
        """Query the MessageIndex."""
        msg_db = MessageIndex(disk_path=None)
        msg_db.add(self.msg1)
        msg_db.add(self.msg2)
        msg_db.add(self.msg3)
        msg_db.add(self.msg4)
        msg_db.add(self.msg5)
        msg_db.add(self.msg6)

        # qry by code
        assert await msg_db.contains(code="2309"), "code 2309 missing"
        assert await msg_db.contains(code="3150"), "code 3150 missing"
        assert await msg_db.contains(src="01:087939", dst="01:087939", code="2309"), (
            "src, dst missing"
        )
        assert not await msg_db.contains(src="01:12345", code="2309"), (
            "random src should return False"
        )
        assert not await msg_db.contains(code="1234"), (
            "a random code should return False"
        )
        assert await msg_db.contains(dst="01:087939"), "dst missing"

        # Verify RAM queries operate correctly without SQL string parsing
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

        msg_db.stop()  # close sqlite3 connection

    async def test_fat_database_payload_serialization(self) -> None:
        """Phase 2.5: Verify large payloads decode properly from the RAM cache."""
        msg_db = MessageIndex(maintain=False, disk_path=None)
        msg_db.add(self.msg4)  # Contains a highly complex dictionary payload

        # Query the message directly out of the RAM index
        res = await msg_db.get(code="31DA")
        assert len(res) == 1

        # Assert it matches the payload without SQL query translation errors
        assert res[0].payload == self.msg4.payload, "payload retrieval failed"

        msg_db.stop()
