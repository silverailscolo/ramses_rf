#!/usr/bin/env python3
"""RAMSES RF - Test the payload parsers."""

from pathlib import Path, PurePath
from typing import Any

import pytest

from ramses_rf.messages import Message
from ramses_tx.const import Code
from ramses_tx.exceptions import PacketInvalid
from ramses_tx.packet import Packet

from .helpers import TEST_DIR

WORK_DIR = f"{TEST_DIR}/parsers"

HAS_ARRAY = "has_array"
HAS_INDEX = "has_index"
HAS_PAYLOAD = "has_payload"
IS_FRAGMENT = "is_fragment"
META_KEYS = (HAS_ARRAY, HAS_INDEX, HAS_PAYLOAD, IS_FRAGMENT)


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

    packet = Packet.from_file(packet_line[:26], packet_line[27:])

    try:
        msg = Message(packet.to_dto())
    except PacketInvalid:
        # If the log line didn't expect a valid payload (wip logs), ignore it
        if not packet_eval:
            return

        # The new L7 strict decoding raises PacketInvalid instead of returning
        # a payload dictionary with a "_parse_error" key.
        if "_parse_error" in packet_eval:
            return

        raise

    # assert bool(msg._is_fragment) == packet._is_fragment
    # assert bool(msg._index): dict == packet._index: Optional[bool | str]
    # not useful

    if not packet_eval:
        return
    try:
        packet_dict = eval(packet_eval)
    except SyntaxError:
        if "{" in packet_eval:  # if so, there is an issue with the log line
            raise  # that should be addressed
        return

    if isinstance(packet_dict, list) or not any(
        k for k in packet_dict if k in META_KEYS
    ):
        payload = msg.payload

        keys_to_strip = (
            "zone_index",
            "domain_id",
            "domain_index",
            "dhw_index",
            "hvac_id",
            "ufh_index",
            "ufx_index",
            "log_index",
            "other_index",
        )

        # Safely align single-element lists with dicts
        if (
            isinstance(payload, dict)
            and isinstance(packet_dict, list)
            and len(packet_dict) == 1
            and isinstance(packet_dict[0], dict)
        ):
            packet_dict = packet_dict[0]
        elif (
            isinstance(payload, list)
            and len(payload) == 1
            and isinstance(payload[0], dict)
            and isinstance(packet_dict, dict)
        ):
            payload = payload[0]

        LEGACY_KEY_MAP = {
            "req_reason": "request_reason",
            "req_speed": "request_speed",
            "is_dst": "is_daylight_saving",
        }

        def _normalize_dict(d: dict[str, Any]) -> dict[str, Any]:
            return {
                LEGACY_KEY_MAP.get(k, k): v
                for k, v in d.items()
                if k not in keys_to_strip and not k.startswith("_")
            }

        # Safely align the payload for comparison against legacy logs
        if isinstance(payload, dict) and isinstance(packet_dict, dict):
            payload = _normalize_dict(payload)
            packet_dict = _normalize_dict(packet_dict)

        # Apply the same stripping logic if the payload is an array of dicts
        elif isinstance(payload, list) and isinstance(packet_dict, list):
            new_payload: list[Any] = []
            new_packet_dict: list[Any] = []
            for item, packet_item in zip(payload, packet_dict, strict=False):
                if isinstance(item, dict) and isinstance(packet_item, dict):
                    new_payload.append(_normalize_dict(item))
                    new_packet_dict.append(_normalize_dict(packet_item))
                else:
                    new_payload.append(item)
                    new_packet_dict.append(packet_item)
            payload = new_payload
            packet_dict = new_packet_dict

        # NOTE: For compatibility with legacy test logs where 1-byte "00"
        # was `{}`.
        if packet_dict == {} and payload == {"heartbeat": True}:
            return

        assert payload == packet_dict, packet_line
        return


def _proc_log_line_pair_4e15(
    log_line: str, prev_msg: Message | None
) -> Message | None:
    packet_line, *_ = list(
        map(str.strip, log_line.split("#", maxsplit=1) + [""])
    )

    if not packet_line:
        return None

    packet = Packet.from_file(packet_line[:26], packet_line[27:])

    try:
        this_msg = Message(packet.to_dto())
    except PacketInvalid:
        return None

    if not prev_msg or prev_msg.code != Code._4E15:
        return this_msg

    if this_msg.code != Code._3EF0:
        return None

    assert prev_msg.payload["is_cooling"] == this_msg.payload["cool_active"]
    assert prev_msg.payload["is_heating"] == this_msg.payload["ch_active"]
    assert prev_msg.payload["is_dhw_ing"] == this_msg.payload["dhw_active"]

    return this_msg


def test_parsers_from_log_files(f_name: Path) -> None:
    with open(f_name) as f:
        while line := (f.readline()):
            _proc_log_line(line)


def _test_parser_31da(f_name: Path) -> None:
    # assert _31DA_FAN_INFO[int(payload[36:38], 16) & 0x1F] in (
    #     speed_capabilities(payload[30:34])["speed_capabilities"]
    # ) or (
    #     int(payload[36:38], 16) & 0x1F in (1, 2, 3) and int(
    #         payload[30:34], 16
    #     ) & 2**14
    # ) or (
    #     int(payload[36:38], 16) & 0x1F in (11, 12, 13) and int(
    #         payload[30:34], 16
    #     ) & 2**14 and int(payload[30:34], 16) & 2**13
    # ) or (
    #     int(payload[36:38], 16) & 0x1F in (0x00, 0x18, 0x15)
    # ), {
    #     _31DA_FAN_INFO[
    #         int(payload[36:38], 16) & 0x1F
    #     ]: speed_capabilities(payload[30:34])
    # }

    # assert payload[36:38] not in ("0B", "0C", "0D") or payload[
    #     42:46
    # ] == "0000", (
    #     payload[36:38], payload[42:46]
    # )

    pass


def _test_parser_pairs_31d9_31da(f_name: Path) -> None:
    pass


def _test_parser_pairs_4e15_3ef0(f_name: Path) -> None:
    if "4e15" in str(f_name):
        with open(f_name) as f:
            msg = None
            while this_line := (f.readline()):
                msg = _proc_log_line_pair_4e15(this_line, msg)

    # elif "01ff" in str(f_name):
    #     with open(f_name) as f:
    #         msg = None
    #         while this_line := (f.readline()):
    #             msg = _proc_log_line_pair_01ff(this_line, msg)
