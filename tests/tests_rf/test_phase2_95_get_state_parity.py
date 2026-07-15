#!/usr/bin/env python3
"""Test warm restart state extraction parity for Phase 2.95."""

from datetime import datetime as dt
from unittest.mock import MagicMock

import pytest

from ramses_rf.gateway import Gateway
from ramses_tx import I_, RP, RQ


def _mock_addr(addr_id: str) -> MagicMock:
    """Helper to create a mocked Address object."""
    mock = MagicMock()
    mock.id = addr_id
    return mock


@pytest.mark.asyncio
async def test_get_state_parity() -> None:
    """Test get_state returns expected structure and filters verbs."""
    gwy = Gateway(port_name="/dev/null")
    gwy.message_store = MagicMock()

    # Mocking messages with the raw _addrs tuple
    msg_i = MagicMock()
    msg_i.verb = I_
    msg_i.dtm = dt(2023, 1, 1, 12, 0, 0)
    msg_i.src.id = "01:123456"
    msg_i.dst.id = "01:123456"
    msg_i._addrs = (
        _mock_addr("01:123456"),
        _mock_addr("--:------"),
        _mock_addr("01:123456"),
    )
    msg_i.code = "1F09"
    msg_i.payload = {"temp": 21.0}
    msg_i._pkt._frame = " I --- 01:123456 --:------ 01:123456 1F09 003 0004B5"

    msg_rp = MagicMock()
    msg_rp.verb = RP
    msg_rp.dtm = dt(2023, 1, 1, 12, 1, 0)
    msg_rp.src.id = "04:111111"
    msg_rp.dst.id = "01:123456"
    msg_rp._addrs = (
        _mock_addr("04:111111"),
        _mock_addr("01:123456"),
        _mock_addr("01:123456"),
    )
    msg_rp.code = "2309"
    msg_rp.payload = {"sync": True}
    msg_rp._pkt._frame = "RP --- 04:111111 01:123456 04:111111 2309 003 0004B5"

    msg_rq = MagicMock()
    msg_rq.verb = RQ
    msg_rq.dtm = dt(2023, 1, 1, 12, 2, 0)
    msg_rq.src.id = "01:123456"
    msg_rq.dst.id = "04:111111"
    msg_rq._addrs = (
        _mock_addr("01:123456"),
        _mock_addr("04:111111"),
        _mock_addr("04:111111"),
    )
    msg_rq.code = "2309"
    msg_rq.payload = {}

    # Set up the cache mock
    gwy.message_store.state_cache = {
        "h1": msg_i,
        "h2": msg_rp,
        "h3": msg_rq,
    }

    schema, state = await gwy.get_state()

    # Check filter
    assert len(state) == 2, "Should only include I_ and RP verbs"

    dtm_i = msg_i.dtm.isoformat(timespec="microseconds")
    dtm_rp = msg_rp.dtm.isoformat(timespec="microseconds")

    assert dtm_i in state
    assert dtm_rp in state

    # Check structure including the newly added raw packet addresses
    assert state[dtm_i] == {
        "verb": I_,
        "src": "01:123456",
        "dst": "01:123456",
        "addr1": "01:123456",
        "addr2": "--:------",
        "addr3": "01:123456",
        "code": "1F09",
        "payload": {"temp": 21.0},
        "frame": " I --- 01:123456 --:------ 01:123456 1F09 003 0004B5",
    }

    assert state[dtm_rp] == {
        "verb": RP,
        "src": "04:111111",
        "dst": "01:123456",
        "addr1": "04:111111",
        "addr2": "01:123456",
        "addr3": "01:123456",
        "code": "2309",
        "payload": {"sync": True},
        "frame": "RP --- 04:111111 01:123456 04:111111 2309 003 0004B5",
    }


@pytest.mark.asyncio
async def test_get_state_frame_key_enables_restore() -> None:
    """Regression test for issue 812: get_state() must include a 'frame' key
    so that Packet.from_dict can reconstruct the packet on warm restart.

    Without the frame key, _restore_cached_packets gets an empty frame body
    and raises "Bad frame: Invalid structure: >>><<<".
    """
    import json

    from ramses_tx.packet import Packet

    gwy = Gateway(port_name="/dev/null")
    gwy.message_store = MagicMock()

    msg = MagicMock()
    msg.verb = I_
    msg.dtm = dt(2023, 1, 1, 12, 0, 0)
    msg.src.id = "01:123456"
    msg.dst.id = "01:123456"
    msg._addrs = (
        _mock_addr("01:123456"),
        _mock_addr("--:------"),
        _mock_addr("01:123456"),
    )
    msg.code = "1F09"
    msg.payload = {"temp": 21.0}
    msg._pkt._frame = " I --- 01:123456 --:------ 01:123456 1F09 003 0004B5"

    gwy.message_store.state_cache = {"h1": msg}

    _schema, state = await gwy.get_state()

    dtm_str = msg.dtm.isoformat(timespec="microseconds")
    assert "frame" in state[dtm_str], "get_state() must include 'frame' key"

    # Simulate HA storage: JSON round-trip then Packet.from_dict
    json_roundtrip = json.loads(json.dumps(state))
    pkt = Packet.from_dict(dtm_str, json_roundtrip[dtm_str])
    assert pkt.code == "1F09"
    assert pkt._frame == " I --- 01:123456 --:------ 01:123456 1F09 003 0004B5"
