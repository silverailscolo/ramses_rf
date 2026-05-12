#!/usr/bin/env python3
"""RAMSES RF - Test the payload parsers and corresponding output.

Includes gwy dicts (schema, traits, params, status).
"""

import asyncio
import datetime as dt_module
from collections.abc import Generator
from dataclasses import asdict, is_dataclass
from datetime import datetime as dt
from pathlib import Path, PurePath
from typing import Any
from unittest.mock import patch

import pytest

from ramses_rf import Gateway
from ramses_rf.helpers import shrink
from ramses_rf.messages import Message
from ramses_rf.state import MessageStore
from ramses_tx import exceptions as exc
from ramses_tx.packet import Packet

from .helpers import (
    TEST_DIR,
    assert_expected_set,
    load_expected_results,
    load_test_gwy,
    shuffle_dict,
)

WORK_DIR = f"{TEST_DIR}/systems"


class AwareDatetime(dt):
    @classmethod
    def now(cls, tz: dt_module.tzinfo | None = None) -> "AwareDatetime":
        _now = dt.now(tz=tz or dt_module.UTC)
        return cls(
            _now.year,
            _now.month,
            _now.day,
            _now.hour,
            _now.minute,
            _now.second,
            _now.microsecond,
            tzinfo=_now.tzinfo,
        )

    @classmethod
    def fromisoformat(cls, date_string: str) -> "AwareDatetime":
        _dt = super().fromisoformat(date_string)
        if _dt.tzinfo is None:
            _dt = _dt.replace(tzinfo=dt_module.UTC)
        return cls(
            _dt.year,
            _dt.month,
            _dt.day,
            _dt.hour,
            _dt.minute,
            _dt.second,
            _dt.microsecond,
            tzinfo=_dt.tzinfo,
        )


class PacketShim:
    def __init__(self, dto: Any) -> None:
        self._dto = dto
        self._hdr = getattr(dto, "code", "0000")
        self._frame = getattr(dto, "payload", "")

    @property
    def _ctx(self) -> Any:
        """Mock the native L3 context extraction."""
        code = getattr(self._dto, "code", "")
        payload = getattr(self._dto, "payload", "")
        if code == "3220" and len(payload) >= 6:
            return payload[4:6]
        return None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._dto, name)


def mocked_pkt_prop(self: Any) -> Any:
    return PacketShim(self._dto)


@pytest.fixture(autouse=True)
def global_test_patches() -> Generator[None, None, None]:
    original_async_send_cmd = Gateway.async_send_cmd

    async def patched_async_send_cmd(*args: Any, **kwargs: Any) -> Any:
        try:
            return await original_async_send_cmd(*args, **kwargs)
        except NotImplementedError as err:
            if "this Protocol is Read-Only" in str(err):
                return None
            raise

    with (
        patch("ramses_rf.gateway.dt", AwareDatetime),
        patch("ramses_tx.engine.dt", AwareDatetime),
        patch("ramses_tx.packet.dt", AwareDatetime),
        patch("ramses_rf.messages.Message._pkt", property(mocked_pkt_prop)),
        patch(
            "ramses_rf.gateway.Gateway.async_send_cmd",
            patched_async_send_cmd,
        ),
    ):
        yield


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    def id_fnc(param: Path) -> str:
        return PurePath(param).name

    folders = [f for f in Path(WORK_DIR).iterdir() if f.is_dir() and f.name[:1] != "_"]
    metafunc.parametrize("dir_name", folders, ids=id_fnc)


def test_payload_from_log_file(dir_name: Path) -> None:
    """Assert that each message payload is as expected."""
    # RP --- 02:044328 18:200214 --:------ 2309 003 0007D0
    # {'ufh_idx': '00', 'setpoint': 20.0}

    def safe_shrink(obj: Any) -> Any:
        if isinstance(obj, dict):
            return shrink(obj, keep_falsys=True)
        if isinstance(obj, list):
            return [safe_shrink(x) for x in obj]
        return obj

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

        expected_shrunk = safe_shrink(expected)

        actual_payload = msg.payload
        if is_dataclass(actual_payload):
            actual_payload = asdict(actual_payload)
        elif isinstance(actual_payload, list):
            actual_payload = [
                asdict(x) if is_dataclass(x) else x for x in actual_payload
            ]

        actual_shrunk = safe_shrink(actual_payload)

        if isinstance(actual_shrunk, dict) and isinstance(expected_shrunk, dict):
            for key in ("zone_idx", "domain_id", "dhw_idx", "msg_id"):
                if key not in expected_shrunk:
                    actual_shrunk.pop(key, None)

        assert actual_shrunk == expected_shrunk

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

    with (
        patch(
            "ramses_rf.gateway.MessageStore",
            side_effect=lambda *args, **kwargs: MessageStore(
                *args, **{**kwargs, "disk_path": None}
            ),
        ),
    ):
        gwy: Gateway = await load_test_gwy(dir_name)

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

    with (
        patch(
            "ramses_rf.gateway.MessageStore",
            side_effect=lambda *args, **kwargs: MessageStore(
                *args, **{**kwargs, "disk_path": None}
            ),
        ),
    ):
        gwy: Gateway = await load_test_gwy(dir_name)

    schema, packets = await gwy.get_state(include_expired=True)
    packets = shuffle_dict(packets)

    await gwy._restore_cached_packets(packets)
    if gwy.message_store:
        gwy.message_store.flush()
    await asyncio.sleep(0)  # Yield to allow flush callbacks to fire

    await assert_expected_set(gwy, expected)

    await gwy.stop()


async def test_fuzz_from_log_file(dir_name: Path) -> None:
    """Compare the system built from a fuzzed log file with results."""

    expected: dict = load_expected_results(dir_name) or {}
    gwy: Gateway = await load_test_gwy(dir_name)

    schema, packets = await gwy.get_state(include_expired=True)

    # This loop is non-deterministic, but should be stable (fails rarely)
    # The logic is that the system state should be consistent regardless
    # of the order of the packets (within reason)
    for _ in range(3):
        packets = shuffle_dict(packets)
        await gwy._restore_cached_packets(packets)
        await assert_expected_set(gwy, expected)

    await gwy.stop()


async def test_fuzz_from_log_file_sql(dir_name: Path) -> None:
    """Compare system built from fuzzed log file, using SQLite msg_db."""

    expected: dict = load_expected_results(dir_name) or {}

    with (
        patch(
            "ramses_rf.gateway.MessageStore",
            side_effect=lambda *args, **kwargs: MessageStore(
                *args, **{**kwargs, "disk_path": None}
            ),
        ),
    ):
        gwy: Gateway = await load_test_gwy(dir_name)

    schema, packets = await gwy.get_state(include_expired=True)

    # This loop is non-deterministic, but should be stable (fails rarely)
    # The logic is that the system state should be consistent regardless
    # of the order of the packets (within reason)
    for _ in range(3):
        packets = shuffle_dict(packets)
        await gwy._restore_cached_packets(packets)
        if gwy.message_store:
            gwy.message_store.flush()
        await asyncio.sleep(0)  # Yield to allow flush callbacks to fire

        await assert_expected_set(gwy, expected)

    await gwy.stop()
