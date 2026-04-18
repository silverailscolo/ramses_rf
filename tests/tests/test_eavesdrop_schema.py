#!/usr/bin/env python3
"""RAMSES RF - Test eavesdropping of a device class."""

import json
from pathlib import Path, PurePath
from typing import Any

import pytest

from ramses_rf import Gateway
from ramses_rf.gateway import GatewayConfig
from ramses_rf.helpers import shrink
from ramses_tx.config import EngineConfig

from .helpers import TEST_DIR, assert_expected

WORK_DIR = f"{TEST_DIR}/eavesdrop_schema"


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Generate the test cases for each folder in the work directory.

    :param metafunc: The pytest metafunc object.
    :type metafunc: pytest.Metafunc
    :rtype: None
    """

    def id_fnc(param: Path) -> str:
        """Return the name of the folder.

        :param param: The path to the folder.
        :type param: Path
        :return: The folder name as a string.
        :rtype: str
        """
        return PurePath(param).name

    folders = [f for f in Path(WORK_DIR).iterdir() if f.is_dir() and f.name[:1] != "_"]
    folders.sort()
    metafunc.parametrize("dir_name", folders, ids=id_fnc)


async def assert_schemas_equal(gwy: Gateway, expected_schema: dict[str, Any]) -> None:
    """Check the gwy schema, then shuffle and test again.

    :param gwy: The gateway instance to check.
    :type gwy: Gateway
    :param expected_schema: The schema dictionary expected to match.
    :type expected_schema: dict[str, Any]
    :raises AssertionError: If the actual schema does not match the
        expected schema.
    :rtype: None
    """
    schema, packets = await gwy.get_state(include_expired=True)
    assert_expected(schema, expected_schema)

    # Bypass the shuffle to force a chronological pass
    # packets = shuffle_dict(packets)
    await gwy._restore_cached_packets(packets)

    actual_shuffled = await gwy.schema()
    try:
        assert_expected(actual_shuffled, expected_schema)
    except AssertionError:
        with open("mismatch_shuffled_actual.json", "w", encoding="utf-8") as f:
            json.dump(shrink(actual_shuffled), f, indent=4)
        with open("mismatch_shuffled_expected.json", "w", encoding="utf-8") as f:
            json.dump(shrink(expected_schema), f, indent=4)
        raise


# duplicate in test_eavesdrop_dev_class
async def test_eavesdrop_off(dir_name: Path) -> None:
    """Check discovery of schema and known_list *without*
    eavesdropping.

    :param dir_name: The directory containing the test packet log and
        schemas.
    :type dir_name: Path
    :rtype: None
    """

    path = f"{dir_name}/packet.log"
    gwy = Gateway(
        None,
        config=GatewayConfig(
            enable_eavesdrop=False,
            engine=EngineConfig(input_file=path),
        ),
    )
    await gwy.start()

    with open(f"{dir_name}/schema_eavesdrop_off.json") as f:
        await assert_schemas_equal(gwy, json.load(f))

    try:
        with open(f"{dir_name}/known_list_eavesdrop_off.json") as f:
            assert_expected(
                await gwy.device_registry.known_list(),
                json.load(f).get("known_list"),
            )
    except FileNotFoundError:
        pass

    await gwy.stop()


# duplicate in test_eavesdrop_dev_class
async def test_eavesdrop_on_(dir_name: Path) -> None:
    """Check discovery of schema and known_list *with* eavesdropping.

    :param dir_name: The directory containing the test packet log and
        schemas.
    :type dir_name: Path
    :rtype: None
    """

    path = f"{dir_name}/packet.log"
    gwy = Gateway(
        None,
        config=GatewayConfig(
            enable_eavesdrop=True,
            engine=EngineConfig(input_file=path),
        ),
    )
    await gwy.start()

    with open(f"{dir_name}/schema_eavesdrop_on.json") as f:
        await assert_schemas_equal(gwy, json.load(f))

    try:
        with open(f"{dir_name}/known_list_eavesdrop_on.json") as f:
            assert_expected(
                await gwy.device_registry.known_list(),
                json.load(f).get("known_list"),
            )
    except FileNotFoundError:
        pass

    await gwy.stop()
