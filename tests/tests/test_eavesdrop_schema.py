#!/usr/bin/env python3
"""RAMSES RF - Test eavesdropping of a device class."""

import asyncio
import json
from pathlib import Path, PurePath

import pytest

from ramses_rf.config import GatewayConfig
from ramses_rf.gateway import Gateway
from ramses_tx.const import SZ_READER_TASK

from .helpers import TEST_DIR, assert_expected

WORK_DIR = f"{TEST_DIR}/eavesdrop_schema"


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
    """Generate the test cases for each folder in the work directory."""

    def id_fnc(param: Path) -> str:
        return PurePath(param).name

    folders = [f for f in Path(WORK_DIR).iterdir() if f.is_dir() and f.name[:1] != "_"]
    folders.sort()
    metafunc.parametrize("dir_name", folders, ids=id_fnc)


@pytest.mark.asyncio
async def test_eavesdrop_off(dir_name: Path) -> None:
    """Check discovery of schema and known_list without eavesdropping."""

    packet_log = dir_name / "packet.log"
    schema_path = dir_name / "schema_eavesdrop_off.json"
    list_path = dir_name / "known_list_eavesdrop_off.json"

    # Arrange
    config = GatewayConfig(enable_eavesdrop=False)
    config.disable_discovery = True
    config.engine.input_file = str(packet_log)

    gwy = Gateway(config=config)

    with open(schema_path) as f:
        expected_schema = json.load(f)

    # Act
    await gwy.start(start_discovery=False)

    try:
        # Wait for transport
        if gwy._engine._transport:
            reader_task = gwy._engine._transport.get_extra_info(SZ_READER_TASK)
            if reader_task:
                await reader_task

        await asyncio.sleep(0.1)
        await drain_cqrs_queues(gwy)

        actual_schema = await gwy.schema()
        assert_expected(actual_schema, expected_schema)

        if list_path.exists():
            with open(list_path) as f:
                expected_list = json.load(f).get("known_list")
            assert_expected(await gwy.device_registry.known_list(), expected_list)

    finally:
        await gwy.stop()


@pytest.mark.asyncio
async def test_eavesdrop_on_(dir_name: Path) -> None:
    """Check discovery of schema and known_list with eavesdropping."""

    packet_log = dir_name / "packet.log"
    schema_path = dir_name / "schema_eavesdrop_on.json"
    list_path = dir_name / "known_list_eavesdrop_on.json"

    # Arrange (Strictly relying on dynamic discovery!)
    config = GatewayConfig(enable_eavesdrop=True)
    config.disable_discovery = True
    config.engine.input_file = str(packet_log)

    gwy = Gateway(config=config)

    with open(schema_path) as f:
        expected_schema = json.load(f)

    # Act
    await gwy.start(start_discovery=False)

    try:
        if gwy._engine._transport:
            reader_task = gwy._engine._transport.get_extra_info(SZ_READER_TASK)
            if reader_task:
                await reader_task

        await asyncio.sleep(0.1)
        await drain_cqrs_queues(gwy)

        actual_schema = await gwy.schema()
        assert_expected(actual_schema, expected_schema)

        if list_path.exists():
            with open(list_path) as f:
                expected_list = json.load(f).get("known_list")
            assert_expected(await gwy.device_registry.known_list(), expected_list)

    finally:
        await gwy.stop()
