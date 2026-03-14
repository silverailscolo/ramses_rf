#!/usr/bin/env python3
"""RAMSES RF - Test the Schema processor."""

import json
from pathlib import Path

import pytest

from ramses_rf import Gateway
from ramses_rf.gateway import GatewayConfig
from ramses_rf.helpers import shrink

from .helpers import (
    TEST_DIR,
    gwy,  # noqa: F401
    shuffle_dict,
)

WORK_DIR = f"{TEST_DIR}/schemas"


@pytest.mark.parametrize(
    "f_name", [f.stem for f in Path(f"{WORK_DIR}/log_files").glob("*.log")]
)
async def test_schema_discover_from_log(f_name: str) -> None:
    """Test the discovery of a schema from a log file.

    :param f_name: The stem of the log file to be tested
    """
    path = f"{WORK_DIR}/log_files/{f_name}.log"
    gwy = Gateway(None, config=GatewayConfig(input_file=path))  # noqa: F811
    await gwy.start()  # this is what we're testing

    with open(f"{WORK_DIR}/log_files/{f_name}.json") as f:
        schema = json.load(f)

        assert shrink(await gwy.schema()) == shrink(schema)

        gwy._engine.ser_name = "/dev/null"  # HACK: needed to pause engine
        schema, packets = await gwy.get_state(include_expired=True)
        packets = shuffle_dict(packets)
        await gwy._restore_cached_packets(packets)

        assert shrink(await gwy.schema()) == shrink(schema)

    await gwy.stop()


# def test_schema_load_from_json(f_name: str) -> None:
#     """Test the loading of a schema from a JSON file.
#
#     :param f_name: The stem of the JSON file to be tested
#     """
#     path = f"{WORK_DIR}/jsn_files/{f_name}.json"
#     gwy = Gateway(None, config=GatewayConfig(input_file=path))  # noqa: F811
#
#     with open(f"{WORK_DIR}/jsn_files/{f_name}.json") as f:
#         schema = json.load(f)
#
#     load_schema(gwy, schema)
