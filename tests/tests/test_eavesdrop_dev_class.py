#!/usr/bin/env python3
"""RAMSES RF - Test eavesdropping of a device class."""

import asyncio
import json
from pathlib import Path, PurePath

import pytest

from ramses_rf import Gateway, Message
from ramses_rf.gateway import GatewayConfig
from ramses_tx.config import EngineConfig
from ramses_tx.const import SZ_READER_TASK

from .helpers import TEST_DIR, assert_expected

WORK_DIR = f"{TEST_DIR}/eavesdrop_dev_class"


async def drain_cqrs_queues(gwy_cqrs: Gateway) -> None:
    """Ensure all CQRS event bus queues are fully drained before proceeding."""
    dispatcher = getattr(gwy_cqrs, "dispatcher", None)

    if dispatcher:
        if hasattr(dispatcher, "discovery_queue"):
            await dispatcher.discovery_queue.join()
        if hasattr(dispatcher, "ssot_queue"):
            await dispatcher.ssot_queue.join()
        if hasattr(dispatcher, "binding_fsm_queue"):
            await dispatcher.binding_fsm_queue.join()

    await asyncio.sleep(0)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Generate tests for each folder in the work directory."""

    def id_fnc(param: Path) -> str:
        return PurePath(param).name

    folders = [f for f in Path(WORK_DIR).iterdir() if f.is_dir()]
    metafunc.parametrize("dir_name", folders, ids=id_fnc)


async def test_packets_from_log_file(dir_name: Path) -> None:
    """Check eavesdropping of a src device _SLUG (from each packet line)."""

    def proc_log_line(msg: Message) -> None:
        assert msg.src._SLUG in eval(msg._pkt.comment)

    path = f"{dir_name}/packet.log"

    gwy = Gateway(
        None,
        config=GatewayConfig(
            enable_eavesdrop=False,
            engine=EngineConfig(input_file=path),
        ),
    )
    gwy.config.enable_eavesdrop = True

    gwy.add_msg_handler(proc_log_line)

    try:
        await gwy.start()
        if gwy._engine._transport:
            reader_task = gwy._engine._transport.get_extra_info(SZ_READER_TASK)
            if reader_task:
                await reader_task
    finally:
        await gwy.stop()


@pytest.mark.asyncio
async def test_dev_eavesdrop_on_(dir_name: Path) -> None:
    """Check discovery of schema and known_list *with* eavesdropping."""

    path = f"{dir_name}/packet.log"
    gwy = Gateway(
        None,
        config=GatewayConfig(
            enable_eavesdrop=True,
            engine=EngineConfig(input_file=path),
        ),
    )
    await gwy.start()

    if gwy._engine._transport:
        reader_task = gwy._engine._transport.get_extra_info(SZ_READER_TASK)
        if reader_task:
            await reader_task

    await asyncio.sleep(0.1)
    await drain_cqrs_queues(gwy)

    with open(f"{dir_name}/known_list_eavesdrop_on.json") as f:
        assert_expected(
            await gwy.device_registry.known_list(),
            json.load(f).get("known_list"),
        )

    try:
        with open(f"{dir_name}/schema_eavesdrop_on.json") as f:
            assert_expected(await gwy.schema(), json.load(f))
    except FileNotFoundError:
        pass

    await gwy.stop()


@pytest.mark.asyncio
async def test_dev_eavesdrop_off(dir_name: Path) -> None:
    """Check discovery of schema and known_list *without* eavesdropping."""

    path = f"{dir_name}/packet.log"
    gwy = Gateway(
        None,
        config=GatewayConfig(
            enable_eavesdrop=False,
            engine=EngineConfig(input_file=path),
        ),
    )
    await gwy.start()

    if gwy._engine._transport:
        reader_task = gwy._engine._transport.get_extra_info(SZ_READER_TASK)
        if reader_task:
            await reader_task

    await asyncio.sleep(0.1)
    await drain_cqrs_queues(gwy)

    try:
        with open(f"{dir_name}/known_list_eavesdrop_off.json") as f:
            assert_expected(
                await gwy.device_registry.known_list(),
                json.load(f).get("known_list"),
            )
    except FileNotFoundError:
        pass

    try:
        with open(f"{dir_name}/schema_eavesdrop_off.json") as f:
            assert_expected(await gwy.schema(), json.load(f))
    except FileNotFoundError:
        pass

    await gwy.stop()
