"""Pytest configuration to aggregate and summarize test failure types."""

import collections
import re
from collections.abc import Generator
from typing import Any

import pytest
from _pytest.config import Config
from _pytest.nodes import Item
from _pytest.reports import TestReport
from _pytest.runner import CallInfo
from _pytest.terminal import TerminalReporter

# Constants
FRAME_STRIP_REGEX: re.Pattern[str] = re.compile(r"frame: .*")


def pytest_configure(config: Config) -> None:
    """Initialize a counter for failure types on the pytest config.

    :param config: The pytest configuration object.
    """
    config.failure_types = collections.Counter()  # type: ignore[attr-defined]


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(
    item: Item, call: CallInfo[Any]
) -> Generator[None, Any, None]:
    """Capture test failures and categorize them by their cleaned exception message.

    :param item: The pytest item representing the test being run.
    :param call: Information about the test execution call.
    :yield: Control back to the hook caller.
    :return: None.
    """
    outcome = yield
    report: TestReport = outcome.get_result()

    if report.when == "call" and report.failed and call.excinfo:
        exc_value: str = str(call.excinfo.value)

        # Strip the highly variable frame data so identical payload diffs group together
        category: str = FRAME_STRIP_REGEX.sub("frame: <REDACTED>", exc_value)

        config: Config = item.config
        config.failure_types[category] += 1  # type: ignore[attr-defined]


def pytest_terminal_summary(
    terminalreporter: TerminalReporter, exitstatus: int, config: Config
) -> None:
    """Output the aggregated summary of failure types to the terminal.

    :param terminalreporter: The terminal reporter for writing to the console.
    :param exitstatus: The exit status code of the test session.
    :param config: The pytest configuration object.
    """
    failures: collections.Counter[str] | None = getattr(config, "failure_types", None)

    if failures:
        terminalreporter.section("Aggregated Failure Types Summary")
        for failure_type, count in failures.most_common():
            terminalreporter.write_line(f"--- {count} occurrences ---")
            terminalreporter.write_line(f"{failure_type}\n")
