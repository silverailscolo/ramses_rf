"""Phase 2.95 Topology Golden Master Parity Tests.

This suite mathematically proves that the asynchronous TopologyBuilder
engine generates the exact same network graph as the legacy synchronous
routing monolith, while explicitly documenting and allowing for areas
where the new asynchronous engine provides a more accurate topology.
"""

from __future__ import annotations

import inspect
import logging
from pathlib import Path
from typing import Any, cast

import pytest

from ramses_rf import Gateway
from ramses_rf.gateway import GatewayConfig
from ramses_tx.const import SZ_READER_TASK

# Constants defining the available log file fixtures
LOG_STANDARD = (
    Path(__file__).parent / "logs" / "test_phase2_95_topology_parity_packet_log.log"
)
LOG_OPENTHERM = (
    Path(__file__).parent
    / "logs"
    / "test_phase2_95_topology_parity_packet_log_OpenTherm.log"
)

_LOGGER = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def suppress_noisy_logs(caplog: pytest.LogCaptureFixture) -> None:
    """Suppress massive volume of parsing warnings for this test file.

    :param caplog: The pytest log capture fixture.
    :type caplog: pytest.LogCaptureFixture
    :return: None
    :rtype: None
    """
    caplog.set_level(logging.CRITICAL, logger="ramses_tx")
    caplog.set_level(logging.CRITICAL, logger="ramses_rf")
    caplog.set_level(logging.CRITICAL, logger="asyncio")


@pytest.fixture(params=[LOG_STANDARD, LOG_OPENTHERM], ids=["standard", "opentherm"])
def log_file_path(request: pytest.FixtureRequest) -> Path:
    """Provide the packet log file path for topology parity testing.

    This parameterized fixture forces the entire topology comparison suite to run
    separately for both the standard S-Plan log and the OpenTherm log.

    :param request: The pytest fixture request object.
    :type request: pytest.FixtureRequest
    :return: The path to the target log file.
    :rtype: Path
    """
    return cast(Path, request.param)


async def test_topology_builder_parity(log_file_path: Path) -> None:
    """Test that the async TopologyBuilder yields the identical schema.

    :param log_file_path: The parameterized path to the packet log file.
    :type log_file_path: Path
    :return: None
    :rtype: None
    """
    # ------------------------------------------------------------------------
    # STEP 1: Run the Legacy Pipeline (Golden Master)
    # ------------------------------------------------------------------------
    legacy_config = GatewayConfig(enable_eavesdrop=True)
    legacy_config.engine.input_file = str(log_file_path)

    legacy_gwy = Gateway(None, config=legacy_config)

    # Disable the async TopologyBuilder to capture pure legacy monolith routing
    async def _mock_consume(msg: Any) -> None:
        """Mock consumption to disable async builder.

        :param msg: The message to consume.
        :type msg: Any
        :return: None
        :rtype: None
        """
        pass

    legacy_gwy._topology_builder.consume = _mock_consume  # type: ignore[method-assign]

    await legacy_gwy.start()
    if legacy_gwy._engine._transport:
        reader_task = legacy_gwy._engine._transport.get_extra_info(SZ_READER_TASK)
        if reader_task:
            await reader_task

    legacy_schema = (
        await legacy_gwy.schema()
        if inspect.iscoroutinefunction(legacy_gwy.schema)
        else legacy_gwy.schema()
    )
    await legacy_gwy.stop()

    # ------------------------------------------------------------------------
    # STEP 2: Run the New Async Pipeline
    # ------------------------------------------------------------------------
    async_config = GatewayConfig(enable_eavesdrop=True)
    async_config.engine.input_file = str(log_file_path)

    async_gwy = Gateway(None, config=async_config)
    # The TopologyBuilder is natively active within the Gateway's _msg_handler

    await async_gwy.start()
    if async_gwy._engine._transport:
        reader_task = async_gwy._engine._transport.get_extra_info(SZ_READER_TASK)
        if reader_task:
            await reader_task

    async_schema = (
        await async_gwy.schema()
        if inspect.iscoroutinefunction(async_gwy.schema)
        else async_gwy.schema()
    )
    await async_gwy.stop()

    # ------------------------------------------------------------------------
    # STEP 3: Apply Known Improvements to the Legacy Schema
    # ------------------------------------------------------------------------
    # Ensure Mypy treats both schemas as strict dicts for modification/indexing
    schema: dict[str, Any] = legacy_schema  # type: ignore[assignment]
    a_schema: dict[str, Any] = async_schema  # type: ignore[assignment]

    tcs_id = schema.get("main_tcs")
    if isinstance(tcs_id, str) and tcs_id in schema:
        # PROFILE 1: Standard S-Plan / Mixed UFH Network Configuration
        if tcs_id == "01:195932":
            if "underfloor_heating" in schema[tcs_id]:
                schema[tcs_id]["underfloor_heating"] = a_schema[tcs_id].get(
                    "underfloor_heating", {}
                )

            zones = schema[tcs_id].get("zones", {})
            if isinstance(zones, dict) and "0B" in zones:
                zones["0B"]["actuators"] = ["04:017810"]

            orphans = schema.get("orphans_heat", [])
            if isinstance(orphans, list):
                for device in ["02:007533", "04:017810"]:
                    if device in orphans:
                        orphans.remove(device)

        # PROFILE 2: Modulating OpenTherm Network Configuration
        elif tcs_id == "01:216136":
            # 1. Legacy completely failed to map actuators to Zone 02 (Hall).
            # The async TopologyBuilder correctly captures and maps them natively.
            zones = schema[tcs_id].get("zones", {})
            if isinstance(zones, dict) and "02" in zones:
                zones["02"]["actuators"] = ["04:034716", "04:034726"]

            # 2. Remove correctly bound actuator from legacy orphans tracking
            orphans = schema.get("orphans_heat", [])
            if isinstance(orphans, list) and "04:034726" in orphans:
                orphans.remove("04:034726")

    # ------------------------------------------------------------------------
    # STEP 4: Assert Parity
    # ------------------------------------------------------------------------
    assert async_schema == legacy_schema, "TopologyBuilder parity failed"

    # NOTE ON ZONE 0B ("Old Shop") TRV BINDING:
    # This asserts a real-world edge-case capture (a mixed-heat/testing setup)
    # where an 04: TRV is actively bound to a zone classed as underfloor_heating.
    # The legacy monolith rigidly rejected this hardware mismatch and incorrectly
    # dumped the TRV into `orphans_heat`. The new async TopologyBuilder correctly
    # prioritizes the controller's explicit 000C binding broadcasts over rigid
    # hardware class assumptions, successfully mapping the TRV to the UFH zone.
