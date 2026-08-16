#!/usr/bin/env python3
"""RAMSES RF - Test the Command.put_*, Command.set_* APIs."""

from datetime import datetime as dt

from ramses_rf.helpers import shrink
from ramses_rf.messages import Message
from ramses_tx.packet import Packet

from .mocked_devices.command import MockCommand as Command


def _test_api_good(api, packets):  # NOTE: incl. addr_set check
    """Test a verb|code pair that has a Command constructor."""

    for packet_line in packets:
        packet = _assert_packet_from_frame(packet_line.split("#")[0].rstrip())
        msg = Message(packet)

        _assert_cmd_from_msg(api, msg)

        if isinstance(packets, dict) and (payload := packets[packet_line]):
            assert shrink(msg.payload, keep_falsys=True) == eval(payload)


def _assert_packet_from_frame(packet_line: str) -> Packet:
    """Create a packet from a packet_line and assert their frames match."""

    packet = Packet.from_port(dt.now(), packet_line)
    assert str(packet) == packet_line[4:]
    return packet


def _assert_cmd_from_msg(api, msg) -> None:
    cmd = api(
        msg.src.id,
        **{k: v for k, v in msg.payload.items() if k[:1] != "_"},
        dst_id=msg.dst.id,
    )

    assert cmd == msg._packet  # assert str(cmd) == str(packet)
    assert cmd.dst.id == msg._packet.dst.id
    assert cmd.verb == msg._packet.verb
    assert cmd.code == msg._packet.code
    assert cmd.payload == msg._packet.payload

    return cmd


def test_pet_0005():
    _test_api_good(Command.put_system_zones, PUT_0005_GOOD)


PUT_0005_GOOD = (
    # "...  I --- 01:145038 --:------ 01:145038 0005 004 00087B0F",
    "... RP --- 01:145038 18:000730 --:------ 0005 004 00087B0F",
)
