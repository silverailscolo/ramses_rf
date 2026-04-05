#!/usr/bin/env python3
"""RAMSES RF - Test the payload parsers and corresponding output.

Includes gwy dicts (schema, traits, params, status).
"""

import asyncio
from pathlib import Path, PurePath
from unittest.mock import patch

import pytest

from ramses_rf import Gateway
from ramses_rf.message_store import MessageStore
from ramses_tx import exceptions as exc
from ramses_tx.message import Message
from ramses_tx.packet import Packet

from .helpers import (
    TEST_DIR,
    assert_expected_set,
    load_expected_results,
    load_test_gwy,
    shuffle_dict,
)

WORK_DIR = f"{TEST_DIR}/systems"


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    def id_fnc(param: Path) -> str:
        return PurePath(param).name

    folders = [f for f in Path(WORK_DIR).iterdir() if f.is_dir() and f.name[:1] != "_"]
    metafunc.parametrize("dir_name", folders, ids=id_fnc)


def test_payload_from_log_file(dir_name: Path) -> None:
    """Assert that each message payload is as expected."""
    # RP --- 02:044328 18:200214 --:------ 2309 003 0007D0
    # {'ufh_idx': '00', 'setpoint': 20.0}

    def proc_log_line(log_line: str) -> None:
        if "#" not in log_line:
            return
        pkt_line, dict_str = log_line.split("#", maxsplit=1)

        if not dict_str.strip():
            return

        try:
            expected = eval(dict_str)
        except SyntaxError:
            return

        if isinstance(expected, tuple):  # TODO: deprecate tuple
            expected = expected[0]

        try:
            msg = Message._from_pkt(Packet.from_file(pkt_line[:26], pkt_line[27:]))
        except exc.PacketInvalid:
            return

        assert msg.payload == expected

    with open(f"{dir_name}/packet.log") as f:
        while line := (f.readline()):
            proc_log_line(line)


async def test_restore_from_log_file(dir_name: Path) -> None:
    """Compare the system built from a log file with the expected results."""

    expected: dict = load_expected_results(dir_name) or {}
    gwy: Gateway = await load_test_gwy(dir_name)

    await assert_expected_set(gwy, expected)

    await gwy.stop()


async def test_restore_from_log_file_sql(dir_name: Path) -> None:
    """Compare the system built from a log file with the expected results."""

    expected: dict = load_expected_results(dir_name) or {}

    with patch(
        "ramses_rf.gateway.MessageStore",
        side_effect=lambda *args, **kwargs: MessageStore(
            *args, **{**kwargs, "disk_path": None}
        ),
    ):
        gwy: Gateway = await load_test_gwy(dir_name, _sqlite_index=True)

    await assert_expected_set(gwy, expected)

    await gwy.stop()


async def test_shuffle_from_log_file(dir_name: Path) -> None:
    """Compare the system built from a shuffled log file with results."""

    expected: dict = load_expected_results(dir_name) or {}
    gwy: Gateway = await load_test_gwy(dir_name)

    schema, packets = await gwy.get_state(include_expired=True)
    packets = shuffle_dict(packets)

    await gwy._restore_cached_packets(packets)

    await assert_expected_set(gwy, expected)

    await gwy.stop()


async def test_shuffle_from_log_file_sql(dir_name: Path) -> None:
    """Compare the system built from a shuffled log file with results."""

    expected: dict = load_expected_results(dir_name) or {}

    with patch(
        "ramses_rf.gateway.MessageStore",
        side_effect=lambda *args, **kwargs: MessageStore(
            *args, **{**kwargs, "disk_path": None}
        ),
    ):
        gwy: Gateway = await load_test_gwy(dir_name, _sqlite_index=True)

    schema, packets = await gwy.get_state(include_expired=True)
    packets = shuffle_dict(packets)

    await gwy._restore_cached_packets(packets)
    if gwy.msg_db:
        gwy.msg_db.flush()
    await asyncio.sleep(0)  # Yield to allow flush callbacks to fire

    await assert_expected_set(gwy, expected)

    await gwy.stop()


async def test_fuzz_from_log_file(dir_name: Path) -> None:
    """Compare the system built from a fuzzed log file with results."""

    expected: dict = load_expected_results(dir_name) or {}
    gwy: Gateway = await load_test_gwy(dir_name)

    # for dev in gwy.device_registry.devices:
    #     if dev._msgs:
    #         assert dev._msgs == gwy.msg_db.get(
    #             src=dev.id, dtms=list(dev._msgs.keys())
    #         ), f"Assert 0: {dev} qry != _msgs_"

    schema, packets = await gwy.get_state(include_expired=True)

    # This loop is non-deterministic, but should be stable (fails rarely)
    # The logic is that the system state should be consistent regardless
    # of the order of the packets (within reason)
    for _ in range(3):
        packets = shuffle_dict(packets)
        await gwy._restore_cached_packets(packets)
        await assert_expected_set(gwy, expected)

    # for dev in gwy.device_registry.devices:
    #     if dev._msgs:
    #         assert dev._msgs == gwy.msg_db.get(
    #             src=dev.id, dtms=list(dev._msgs.keys())
    #         ), f"Assert 2: {dev} qry != _msgs_"

    await gwy.stop()


async def test_fuzz_from_log_file_sql(dir_name: Path) -> None:
    """Compare system built from fuzzed log file, using SQLite msg_db."""

    expected: dict = load_expected_results(dir_name) or {}

    with patch(
        "ramses_rf.gateway.MessageStore",
        side_effect=lambda *args, **kwargs: MessageStore(
            *args, **{**kwargs, "disk_path": None}
        ),
    ):
        gwy: Gateway = await load_test_gwy(dir_name, _sqlite_index=True)

    # for dev in gwy.device_registry.devices:
    #     if dev._msgs:
    #         assert dev._msgs == gwy.msg_db.get(
    #             src=dev.id, dtms=list(dev._msgs.keys())
    #         ), f"Assert 1: {dev} qry != _msgs_"

    schema, packets = await gwy.get_state(include_expired=True)

    # This loop is non-deterministic, but should be stable (fails rarely)
    # The logic is that the system state should be consistent regardless
    # of the order of the packets (within reason)
    for _ in range(3):
        packets = shuffle_dict(packets)
        await gwy._restore_cached_packets(packets)
        if gwy.msg_db:
            gwy.msg_db.flush()
        await asyncio.sleep(0)  # Yield to allow flush callbacks to fire

        await assert_expected_set(gwy, expected)

    # for dev in gwy.device_registry.devices:
    #     if dev._msgs:
    #         assert dev._msgs == gwy.msg_db.get(
    #             src=dev.id, dtms=list(dev._msgs.keys())
    #         ), f"Assert 3: {dev} qry != _msgs_"

    await gwy.stop()
