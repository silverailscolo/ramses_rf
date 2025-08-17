#!/usr/bin/env python3
"""RAMSES RF - Test the Command.put_*, Command.set_* APIs."""

from collections.abc import Callable
from datetime import datetime as dt
from typing import Any

from ramses_tx.command import CODE_API_MAP, Command
from ramses_tx.message import Message
from ramses_tx.packet import Packet


def _test_api(api: Callable, packets: dict[str]) -> None:  # NOTE: incl. addr_set check
    """Test a verb|code pair that has a Command constructor, src and dst."""

    for pkt_line, kwargs in packets.items():
        pkt = _create_pkt_from_frame(pkt_line)

        msg = Message(pkt)

        _test_api_from_kwargs(api, pkt, **kwargs)
        _test_api_from_msg(api, msg)


def _test_api_one(
    api: Callable, packets: dict[str]
) -> None:  # NOTE: incl. addr_set check
    """Test a verb|code pair that has a Command constructor and src, but no dst."""

    for pkt_line, kwargs in packets.items():
        pkt = _create_pkt_from_frame(pkt_line)

        msg = Message(pkt)

        _test_api_one_from_kwargs(api, pkt, **kwargs)
        _test_api_one_from_msg(api, msg)


def _create_pkt_from_frame(pkt_line: str) -> Packet:
    """Create a pkt from a pkt_line and assert their frames match."""

    pkt = Packet.from_port(dt.now(), pkt_line)
    assert str(pkt) == pkt_line[4:]
    return pkt


def _test_api_from_msg(api: Callable, msg: Message) -> Command:
    """Create a cmd from a msg with a src_id, and assert they're equal
    (*also* asserts payload)."""

    cmd: Command = api(
        msg.dst.id,
        src_id=msg.src.id,
        **{k: v for k, v in msg.payload.items() if k[:1] != "_"},
    )

    assert cmd == msg._pkt  # must have exact same addr set

    return cmd


def _test_api_one_from_msg(api: Callable, msg: Message) -> Command:
    """Create a cmd from a msg and assert they're equal (*also* asserts payload)."""

    cmd: Command = api(
        msg.dst.id,
        **{k: v for k, v in msg.payload.items()},  # if k[:1] != "_"},
        # requirement turned off as it skips required item like _unknown_fan_info_flags
    )

    assert cmd == msg._pkt  # must have exact same addr set

    return cmd


def _test_api_from_kwargs(api: Callable, pkt: Packet, **kwargs: Any) -> None:
    """
    Test comparing a created packet to an expected result.

    :param api: Command lookup by Verb|Code
    :param pkt: expected result to match
    :param kwargs: arguments for the Command
    """
    cmd = api(HRU, src_id=REM, **kwargs)

    assert str(cmd) == str(pkt)


def _test_api_one_from_kwargs(api: Callable, pkt: Packet, **kwargs: Any) -> None:
    cmd = api(HRU, **kwargs)

    assert str(cmd) == str(pkt)


def test_set() -> None:
    for test_pkts in (SET_22F1_KWARGS, SET_22F7_KWARGS):
        pkt = list(test_pkts)[0]
        api = CODE_API_MAP[f"{pkt[4:6]}|{pkt[41:45]}"]
        _test_api(api, test_pkts)


HRU = "32:155617"  # also used as a FAN
REM = "37:171871"
NUL = "--:------"

SET_22F1_KWARGS = {
    f"000  I --- {REM} {HRU} {NUL} 22F1 002 0000": {"fan_mode": None},
    #
    f"001  I --- {REM} {HRU} {NUL} 22F1 002 0000": {"fan_mode": 0},
    f"001  I --- {REM} {HRU} {NUL} 22F1 002 0001": {"fan_mode": 1},
    f"001  I --- {REM} {HRU} {NUL} 22F1 002 0002": {"fan_mode": 2},
    f"001  I --- {REM} {HRU} {NUL} 22F1 002 0003": {"fan_mode": 3},
    f"001  I --- {REM} {HRU} {NUL} 22F1 002 0004": {"fan_mode": 4},
    f"001  I --- {REM} {HRU} {NUL} 22F1 002 0005": {"fan_mode": 5},
    f"001  I --- {REM} {HRU} {NUL} 22F1 002 0006": {"fan_mode": 6},
    f"001  I --- {REM} {HRU} {NUL} 22F1 002 0007": {"fan_mode": 7},
    #
    f"002  I --- {REM} {HRU} {NUL} 22F1 002 0000": {"fan_mode": "00"},
    f"002  I --- {REM} {HRU} {NUL} 22F1 002 0001": {"fan_mode": "01"},
    f"002  I --- {REM} {HRU} {NUL} 22F1 002 0002": {"fan_mode": "02"},
    f"002  I --- {REM} {HRU} {NUL} 22F1 002 0003": {"fan_mode": "03"},
    f"002  I --- {REM} {HRU} {NUL} 22F1 002 0004": {"fan_mode": "04"},
    f"002  I --- {REM} {HRU} {NUL} 22F1 002 0005": {"fan_mode": "05"},
    f"002  I --- {REM} {HRU} {NUL} 22F1 002 0006": {"fan_mode": "06"},
    f"002  I --- {REM} {HRU} {NUL} 22F1 002 0007": {"fan_mode": "07"},
    #
    f"003  I --- {REM} {HRU} {NUL} 22F1 002 0000": {"fan_mode": "away"},
    f"003  I --- {REM} {HRU} {NUL} 22F1 002 0001": {"fan_mode": "low"},
    f"003  I --- {REM} {HRU} {NUL} 22F1 002 0002": {"fan_mode": "medium"},
    f"003  I --- {REM} {HRU} {NUL} 22F1 002 0003": {"fan_mode": "high"},
    f"003  I --- {REM} {HRU} {NUL} 22F1 002 0004": {"fan_mode": "auto"},
    f"003  I --- {REM} {HRU} {NUL} 22F1 002 0005": {"fan_mode": "auto_alt"},
    f"003  I --- {REM} {HRU} {NUL} 22F1 002 0006": {"fan_mode": "boost"},
    f"003  I --- {REM} {HRU} {NUL} 22F1 002 0007": {"fan_mode": "off"},
}


SET_22F7_KWARGS = {
    f"000  W --- {REM} {HRU} {NUL} 22F7 002 00FF": {},  # shouldn't be OK
    #
    f"001  W --- {REM} {HRU} {NUL} 22F7 002 00FF": {
        "bypass_position": None
    },  # is auto?
    f"001  W --- {REM} {HRU} {NUL} 22F7 002 0000": {"bypass_position": 0.0},
    # 001  W --- {REM} {HRU} {NUL} 22F7 002 0064": {"bypass_position": 0.5},
    f"001  W --- {REM} {HRU} {NUL} 22F7 002 00C8": {"bypass_position": 1.0},
    f"002  W --- {REM} {HRU} {NUL} 22F7 002 00FF": {
        "bypass_mode": "auto"
    },  # is auto, or None?
    f"002  W --- {REM} {HRU} {NUL} 22F7 002 0000": {"bypass_mode": "off"},
    f"002  W --- {REM} {HRU} {NUL} 22F7 002 00C8": {"bypass_mode": "on"},
}


# new tests
def test_get() -> None:
    for test_pkts in (GET_12A0_KWARGS, GET_1298_KWARGS):
        pkt = list(test_pkts)[0]
        api = CODE_API_MAP[f"{pkt[4:6]}|{pkt[41:45]}"]
        _test_api_one(api, test_pkts)


GET_12A0_KWARGS = {
    f"000  I --- {HRU} {NUL} {HRU} 12A0 002 00EF": {
        "indoor_humidity": None
    },  # shouldn't be OK
    #
    f"082  I --- {HRU} {NUL} {HRU} 12A0 002 0037": {"indoor_humidity": 0.55},
}

GET_1298_KWARGS = {
    f"064  I --- {HRU} {NUL} {HRU} 1298 003 000322": {"co2_level": 802},
}

# TODO Add tests to get states from 31DA
# (verifies SQLite refactoring)
# set up HVAC system first from messages
#
# Example: current_temperature(self) in ramses_cc.climate.py
# simulates requesting Climate self._device.indoor_temp from a system
