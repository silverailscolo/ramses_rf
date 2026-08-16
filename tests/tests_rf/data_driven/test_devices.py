#!/usr/bin/env python3
"""RAMSES RF - Test the payload parsers on a per-device basis."""

from pathlib import Path, PurePath

import pytest

from ramses_rf.messages import Message
from ramses_tx import exceptions as exc
from ramses_tx.packet import Packet

from .helpers import TEST_DIR

WORK_DIR = f"{TEST_DIR}/devices"


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    def id_fnc(param: Path) -> str:
        return PurePath(param).name

    metafunc.parametrize(
        "f_name", sorted(Path(WORK_DIR).glob("*.log")), ids=id_fnc
    )


def _proc_log_line(log_line: str) -> None:
    packet_line, packet_eval, *_ = list(
        map(str.strip, log_line.split("#", maxsplit=1) + [""])
    )

    if not packet_line:
        return

    try:
        packet = Packet.from_file(packet_line[:26], packet_line[27:])
    except exc.PacketInvalid as err:
        assert False, f"{packet_line[27:]} < {err}"

    try:
        _ = Message(packet.to_dto())
    except exc.PacketPayloadInvalid as err:
        assert False, f"{packet} < {err}"
    except exc.PacketInvalid as err:
        # The new L7 strict decoding may raise PacketInvalid
        if not packet_eval or "_parse_error" in packet_eval:
            return
        assert False, f"{packet} < {err}"

    # assert bool(msg._is_fragment) == packet._is_fragment
    # assert bool(msg._index): dict == packet._index: Optional[bool | str]
    # not useful

    if not packet_eval:
        return
    try:
        _ = eval(packet_eval)
    except SyntaxError:
        if "{" in packet_eval:
            raise
        return


def test_parsers_from_log_files(f_name: Path) -> None:
    with open(f_name) as f:
        while line := (f.readline()):
            _proc_log_line(line)
