#!/usr/bin/env python3
"""RAMSES RF - a RAMSES-II protocol decoder & analyser."""

import inspect
import json
import re
import warnings
from collections.abc import AsyncGenerator, Callable
from dataclasses import fields
from pathlib import Path
from random import shuffle
from typing import Any

import pytest
import voluptuous as vol

from ramses_rf import Gateway
from ramses_rf.database import MessageIndex
from ramses_rf.gateway import GatewayConfig
from ramses_rf.helpers import shrink
from ramses_rf.schemas import SCH_GLOBAL_CONFIG, SCH_GLOBAL_SCHEMAS
from ramses_tx.schemas import SCH_GLOBAL_TRAITS_DICT

SCH_GLOBAL_TRAITS = vol.Schema(SCH_GLOBAL_TRAITS_DICT, extra=vol.PREVENT_EXTRA)

# import tracemalloc
# tracemalloc.start()

warnings.filterwarnings("ignore", category=DeprecationWarning)

# logging.disable(logging.WARNING)  # usu. WARNING  # TODO: Verify original intent. Commented out as it breaks isolated logging logic in PR #413.


TEST_DIR = Path(__file__).resolve().parent  # TEST_DIR = f"{os.path.dirname(__file__)}"


def shuffle_dict(old_dict: dict) -> dict:
    """Return a dictionary with its keys shuffled.

    :param old_dict: The dictionary to shuffle.
    :type old_dict: dict
    :return: A new dictionary with shuffled keys.
    :rtype: dict
    """
    keys = list(old_dict.keys())
    shuffle(keys)
    new_dict = dict()
    for key in keys:
        new_dict.update({key: old_dict[key]})
    return new_dict


@pytest.fixture
async def gwy() -> AsyncGenerator[Gateway, None]:  # NOTE: async to get running loop
    """Return a vanilla system (with a known, minimal state)."""
    gwy = Gateway("/dev/null", config=GatewayConfig())
    gwy._disable_sending = True
    gwy.msg_db = MessageIndex()  # required to add heat dummy 3220 msg
    try:
        yield gwy
    finally:
        await gwy.stop()  # close sqlite3 connection


def assert_expected(
    actual: dict[str, Any], expected: dict[str, Any] | None = None
) -> None:
    """Compare an actual system state dict against the corresponding expected state.

    :param actual: The actual state dictionary.
    :type actual: dict[str, Any]
    :param expected: The expected state dictionary, defaults to None.
    :type expected: dict[str, Any] | None, optional
    :return: None
    :rtype: None
    """

    def assert_expected(actual_: dict[str, Any], expect_: dict[str, Any]) -> None:
        assert actual_ == expect_

    if expected:
        assert_expected(shrink(actual), shrink(expected))


def assert_expected_set(gwy: Gateway, expected: dict) -> None:
    """Compare the actual system state against the expected system state.

    :param gwy: The gateway instance to check.
    :type gwy: Gateway
    :param expected: The expected state dictionary.
    :type expected: dict
    :return: None
    :rtype: None
    """

    assert_expected(gwy.schema, expected.get("schema"))
    assert_expected(gwy.params, expected.get("params"))
    assert_expected(gwy.status, expected.get("status"))
    assert_expected(gwy.known_list, expected.get("known_list"))


def assert_raises(
    exception: type[Exception], fnc: Callable[..., Any], *args: Any
) -> None:
    """Assert that a function raises a specific exception.

    :param exception: The exception class expected to be raised.
    :type exception: type[Exception]
    :param fnc: The function to call.
    :type fnc: Callable[..., Any]
    :param args: Arguments to pass to the function.
    :type args: Any
    :return: None
    :rtype: None
    """
    try:
        fnc(*args)
    except exception:  # as err:
        pass  # or: assert True
    else:
        assert False


async def load_test_gwy(dir_name: Path, **kwargs: Any) -> Gateway:
    """Create a system state from a packet log (using an optional configuration).

    :param dir_name: The directory containing config.json and packet.log.
    :type dir_name: Path
    :param kwargs: Additional configuration overrides.
    :type kwargs: Any
    :return: The initialized gateway instance.
    :rtype: Gateway
    """
    # TODO(eb): default sqlite_index to True Q1 2026
    _sqlite_index = kwargs.pop("_sqlite_index", False)
    kwargs = SCH_GLOBAL_CONFIG({k: v for k, v in kwargs.items() if k[:1] != "_"})

    try:
        with open(f"{dir_name}/config.json") as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {}

    if config:
        kwargs.update(config)

    config_dict = kwargs.pop("config", {})
    gwy_config_args = {}

    # Extract known GatewayConfig fields
    for field_ in fields(GatewayConfig):
        if field_.name in config_dict:
            gwy_config_args[field_.name] = config_dict.pop(field_.name)

    # Move any leftover legacy config items (e.g. enforce_known_list)
    # to kwargs for Gateway.__init__
    for k, v in config_dict.items():
        kwargs[k] = v

    # Filter kwargs to only those explicitly accepted by Gateway.__init__
    valid_kwargs = inspect.signature(Gateway.__init__).parameters
    gateway_kwargs = {}
    schema_kwargs = kwargs.pop("schema", {})

    # Route valid parameters directly, and selectively lump allowed schema properties
    for k, v in kwargs.items():
        if k.startswith("_"):
            continue
        if k in valid_kwargs:
            gateway_kwargs[k] = v
        elif k in (
            "main_tcs",
            "orphans",
            "orphans_heat",
            "orphans_hvac",
            "system",
        ) or re.match(r"^[0-9]{2}:[0-9]{6}$", k):
            schema_kwargs[k] = v

    if schema_kwargs:
        gateway_kwargs["schema"] = schema_kwargs

    path = f"{dir_name}/packet.log"
    gwy = Gateway(
        None, input_file=path, config=GatewayConfig(**gwy_config_args), **gateway_kwargs
    )
    gwy._sqlite_index = _sqlite_index  # TODO(eb): remove legacy Q2 2026
    await gwy.start()

    # The Gateway with input_file uses a Transport that processes the file automatically.
    # We simply need to wait for the transport to finish reading the file.
    # We pause discovery/sending during replay to avoid side effects.
    await gwy._protocol.wait_for_connection_lost()  # until packet log is EOF

    # Ensure all packets from the log are written to the DB before returning
    # This is critical for tests using the StorageWorker
    if gwy.msg_db:
        gwy.msg_db.flush()

    # if hasattr(
    #     gwy.pkt_transport.serial, "mock_devices"
    # ):  # needs ser instance, so after gwy.start()
    #     gwy.pkt_transport.serial.mock_devices = [MockDeviceCtl(gwy, CTL_ID)]

    return gwy


def load_expected_results(dir_name: Path) -> dict[str, Any]:
    """Return the expected (global) schema/params/status & traits (aka known_list).

    :param dir_name: The directory containing the JSON result files.
    :type dir_name: Path
    :return: A dictionary containing the expected schema, known_list, params, and status.
    :rtype: dict[str, Any]
    """

    try:
        with open(f"{dir_name}/schema.json") as f:
            schema = json.load(f)
    except FileNotFoundError:
        schema = {}
    schema = SCH_GLOBAL_SCHEMAS(schema)

    try:
        with open(f"{dir_name}/known_list.json") as f:
            known_list = json.load(f)["known_list"]
    except FileNotFoundError:
        known_list = {}
    known_list = SCH_GLOBAL_TRAITS({"known_list": shrink(known_list)})["known_list"]

    try:
        with open(f"{dir_name}/params.json") as f:
            params = json.load(f)["params"]
    except FileNotFoundError:
        params = {}

    try:
        with open(f"{dir_name}/status.json") as f:
            status = json.load(f)["status"]
    except FileNotFoundError:
        status = {}

    # TODO: do known_list, status
    return {
        "schema": schema,
        "known_list": known_list,
        "params": params,
        "status": status,
    }
