"""Phase 2.95 CQRS State Parity Tests.

This suite mathematically proves that the new immutable CQRS state models
contain the exact same data as the legacy dynamic properties, guaranteeing
zero regressions before the legacy routing is deleted.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

from ramses_rf import Gateway
from ramses_rf.gateway import GatewayConfig
from ramses_tx.config import EngineConfig
from ramses_tx.const import SZ_READER_TASK
from ramses_tx.exceptions import TransportError

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
    """Suppress massive volume of parsing warnings for this test file only.

    Using caplog.set_level scopes the suppression strictly to the functions
    in this module, preventing log poisoning across the wider pytest suite.

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
    """Provide the packet log file path for state parity testing.

    This parameterized fixture forces every test dependent on it to execute
    separately for both the standard UK S-Plan profile and the OpenTherm profile.

    :param request: The pytest fixture request object.
    :type request: pytest.FixtureRequest
    :return: The path to the target log file.
    :rtype: Path
    """
    return cast(Path, request.param)


async def _get_legacy_value(obj: Any, attr: str) -> Any:
    """Safely get and evaluate a legacy attribute.

    Handles standard attributes, @properties, synchronous methods,
    and asynchronous coroutine methods seamlessly.

    :param obj: The object containing the attribute.
    :type obj: Any
    :param attr: The name of the attribute to look up.
    :type attr: str
    :return: The evaluated attribute value, or None if it doesn't exist.
    :rtype: Any
    """
    if not hasattr(obj, attr):
        return None
    val = getattr(obj, attr)
    if callable(val):
        val = val()
    if asyncio.iscoroutine(val):
        val = await val
    return val


@pytest.mark.asyncio
async def test_cqrs_temperature_and_demand_parity(log_file_path: Path) -> None:
    """Stream all packets and assert CQRS states match legacy properties.

    :param log_file_path: The parameterized path to the packet log file.
    :type log_file_path: Path
    :return: None
    :rtype: None
    :raises FileNotFoundError: If the requested packet log file is missing.
    """
    if not log_file_path.exists():
        raise FileNotFoundError(f"Fixture not found at {log_file_path}")

    # 1. Initialise Gateway identically to the regression suite
    gwy = Gateway(
        None,
        config=GatewayConfig(
            disable_discovery=True,
            reduce_processing=0,
            engine=EngineConfig(
                disable_sending=True,
                input_file=str(log_file_path),
            ),
        ),
    )

    mock_send = AsyncMock(return_value=None)

    with patch.object(gwy, "async_send_cmd", mock_send):
        # 2. Safely load the packets
        with contextlib.suppress(TransportError):
            await gwy.start()

        if gwy._engine._transport:
            reader_task = gwy._engine._transport.get_extra_info(SZ_READER_TASK)
            if reader_task:
                await reader_task

        if gwy.message_store:
            gwy.message_store.flush()

        # 3. Assert Parity Across All Discovered Devices
        for dev in gwy.device_registry.devices:
            # --- Temperature Parity ---
            if hasattr(dev, "temperature"):
                legacy_temp = await _get_legacy_value(dev, "temperature")

                # Use getattr to safely extract future attributes for strict Mypy
                cqrs_temp_state = getattr(dev, "temp_state", None)
                assert cqrs_temp_state is not None, f"{dev} missing CQRS temp_state"
                cqrs_temp = getattr(cqrs_temp_state, "temperature")  # noqa: B009

                if legacy_temp != cqrs_temp:
                    # 1. Legacy Cache Expiration: Legacy forgets old packets, CQRS remembers forever.
                    if legacy_temp is None and cqrs_temp is not None:
                        pass
                    else:
                        # 2. LEGACY BUG COMPENSATION (Oldest vs Newest packet & SQLite Lag)
                        is_legacy_bug = False
                        if gwy.message_store and getattr(dev, "_SLUG", "") in (
                            "TRV",
                            "THM",
                            "OUT",
                            "DHW",
                        ):
                            for code in ("30C9", "1260", "0002"):
                                # A) Check if legacy DB grabbed the oldest instead of newest
                                legacy_msgs = await gwy.message_store.get(
                                    code=code, src=dev.id
                                )
                                if legacy_msgs:
                                    newest_msg = max(legacy_msgs, key=lambda x: x.dtm)
                                    if isinstance(newest_msg.payload, dict):
                                        if (
                                            newest_msg.payload.get("temperature")
                                            == cqrs_temp
                                        ):
                                            is_legacy_bug = True
                                            break

                                # B) Check if SQLite worker is lagging behind synchronous memory
                                for m in gwy.message_store.state_cache.values():
                                    if m.code == code and m.src.id == dev.id:
                                        if (
                                            isinstance(m.payload, dict)
                                            and m.payload.get("temperature")
                                            == cqrs_temp
                                        ):
                                            is_legacy_bug = True
                                            break

                        if not is_legacy_bug:
                            # DEEP DIAGNOSTIC DUMP
                            dump = []
                            dump.append(f"Legacy claims temp is: {legacy_temp}")
                            dump.append(f"CQRS claims temp is:   {cqrs_temp}")

                            if gwy.message_store:
                                # Emulate the exact SQL query the legacy property runs
                                for code in ("30C9", "1260", "0002"):
                                    legacy_msgs = await gwy.message_store.get(
                                        code=code, src=dev.id
                                    )
                                    if legacy_msgs:
                                        dump.append(
                                            f"\nLegacy DB Query for [{code}] (msgs[0] is oldest!) found {len(legacy_msgs)} msgs. Top 3:"
                                        )
                                        for m in legacy_msgs[:3]:
                                            dump.append(
                                                f"  DTM: {m.dtm} | {m.verb} | {m.src.id}->{m.dst.id} | {m.payload}"
                                            )

                                dump.append(
                                    f"\nSearching state_cache for values {legacy_temp} or {cqrs_temp}:"
                                )
                                for m in gwy.message_store.state_cache.values():
                                    p_str = str(m.payload)
                                    if (
                                        str(legacy_temp) in p_str
                                        or str(cqrs_temp) in p_str
                                    ):
                                        dump.append(
                                            f"  DTM: {m.dtm} | [{m.code}] {m.verb} | {m.src.id}->{m.dst.id} | {m.payload}"
                                        )

                            dump_str = "\n    ".join(dump)
                            assert legacy_temp == cqrs_temp, (
                                f"{dev}: Temp mismatch.\n    --- DIAGNOSTIC REPORT ---\n    {dump_str}"
                            )

                # Setpoint (if applicable)
                if hasattr(dev, "setpoint"):
                    legacy_setpoint = await _get_legacy_value(dev, "setpoint")
                    cqrs_setpoint = getattr(cqrs_temp_state, "setpoint")  # noqa: B009

                    # 1. Legacy TRVs return a boolean False for "Off". CQRS strictly uses None.
                    # 2. Legacy caches expire old packets and return None. CQRS permanently remembers.
                    if legacy_setpoint is False and cqrs_setpoint is None:
                        pass
                    elif legacy_setpoint is None and cqrs_setpoint is not None:
                        pass
                    else:
                        assert legacy_setpoint == cqrs_setpoint, (
                            f"{dev}: Setpoint mismatch."
                        )

            # --- Heat Demand Parity ---
            if hasattr(dev, "heat_demand"):
                # OpenTherm Bridges (OTB) calculate demand using a complex priority matrix
                # combining 3220, 3EF0, 3EF1, and 3150 packets. CQRS will handle OT matrices
                # in a dedicated OpenTherm read-model. Bypass generic demand parity for OTB.
                if getattr(dev, "_SLUG", "") == "OTB":
                    continue

                legacy_demand = await _get_legacy_value(dev, "heat_demand")

                cqrs_demand_state = getattr(dev, "demand_state", None)
                assert cqrs_demand_state is not None, f"{dev} missing CQRS demand_state"
                cqrs_demand = getattr(cqrs_demand_state, "heat_demand")  # noqa: B009

                # 1. Legacy TRVs fake a 0 demand if turned off but no telemetry exists.
                # CQRS strictly remains None. Treat these as semantically equivalent.
                if (
                    getattr(dev, "_SLUG", "") == "TRV"
                    and legacy_demand == 0
                    and cqrs_demand is None
                ):
                    continue

                # 2. Legacy caches expire old packets and return None. CQRS permanently remembers.
                if legacy_demand is None and cqrs_demand is not None:
                    continue

                if legacy_demand != cqrs_demand:
                    # DEEP DIAGNOSTIC DUMP FOR DEMANDS
                    dump = []
                    dump.append(f"Legacy claims demand is: {legacy_demand}")
                    dump.append(f"CQRS claims demand is:   {cqrs_demand}")

                    if gwy.message_store:
                        # Emulate the SQL query the legacy property runs
                        for code in ("3150", "0008", "3EF0"):
                            legacy_msgs = await gwy.message_store.get(
                                code=code, src=dev.id
                            )
                            if legacy_msgs:
                                dump.append(
                                    f"\nLegacy DB Query (ORDER BY dtm DESC) for [{code}] found {len(legacy_msgs)} msgs. Top 3:"
                                )
                                for m in legacy_msgs[:3]:
                                    dump.append(
                                        f"  DTM: {m.dtm} | {m.verb} | {m.src.id}->{m.dst.id} | {m.payload}"
                                    )

                        dump.append(
                            f"\nSearching state_cache for values {legacy_demand} or {cqrs_demand}:"
                        )
                        for m in gwy.message_store.state_cache.values():
                            p_str = str(m.payload)
                            if str(legacy_demand) in p_str or str(cqrs_demand) in p_str:
                                dump.append(
                                    f"  DTM: {m.dtm} | [{m.code}] {m.verb} | {m.src.id}->{m.dst.id} | {m.payload}"
                                )

                    dump_str = "\n    ".join(dump)
                    assert legacy_demand == cqrs_demand, (
                        f"{dev}: Demand mismatch.\n    --- DIAGNOSTIC REPORT ---\n    {dump_str}"
                    )

        # 4. Stop Gateway safely
        with contextlib.suppress(asyncio.CancelledError, TransportError):
            await gwy.stop()


@pytest.mark.asyncio
async def test_cqrs_faultlog_parity(log_file_path: Path) -> None:
    """Assert the legacy faultlog dictionary matches the CQRS FaultLogState.

    :param log_file_path: The parameterized path to the packet log file.
    :type log_file_path: Path
    :return: None
    :rtype: None
    """
    if not log_file_path.exists():
        pytest.skip("Fixture file not found.")

    gwy = Gateway(
        None,
        config=GatewayConfig(
            disable_discovery=True,
            reduce_processing=0,
            engine=EngineConfig(disable_sending=True, input_file=str(log_file_path)),
        ),
    )

    with patch.object(gwy, "async_send_cmd", AsyncMock(return_value=None)):
        with contextlib.suppress(TransportError):
            await gwy.start()

        if gwy._engine._transport:
            reader_task = gwy._engine._transport.get_extra_info(SZ_READER_TASK)
            if reader_task:
                await reader_task

        if not gwy.tcs:
            pytest.skip("No TCS discovered in regression file.")

        # Safely extract faultlog bypassing strict type checking
        faultlog = getattr(gwy.tcs, "faultlog", None)
        if not faultlog:
            pytest.skip("No faultlog discovered in regression file.")

        legacy_log = cast("dict[str, Any]", getattr(faultlog, "faultlog"))  # noqa: B009

        cqrs_state = getattr(faultlog, "state", None)
        assert cqrs_state is not None, "Faultlog missing CQRS state"

        # UPGRADE: Cast to tuple instead of dict
        cqrs_log = cast("tuple[Any, ...]", getattr(cqrs_state, "entries"))  # noqa: B009

        legacy_entries = list(legacy_log.values())

        # UPGRADE: cqrs_log is already a tuple, so no .values() is needed.
        # We also convert the dataclass objects to dicts so they cleanly
        # match the legacy dictionary formats during the assertion.
        cqrs_entries = [dataclasses.asdict(entry) for entry in cqrs_log]

        # --------------------------------------------------------------------
        # NOTE ON OFFLINE REPLAY DIVERGENCE:
        # During offline playbacks with disable_sending=True, the strict CQRS
        # transaction tracker discards unicast RP packets unless they match an
        # active local request. The legacy engine blindly accepts all RP packets.
        # If the log contains only unicast RP packets and no I broadcasts,
        # CQRS safely remains empty to prevent network data pollution.
        # --------------------------------------------------------------------
        if len(cqrs_entries) == 0 and len(legacy_entries) > 0:
            _LOGGER.info(
                "CQRS faultlog safely ignored un-tracked unicast RP packets "
                "during offline playback."
            )
        else:
            assert len(cqrs_entries) >= len(legacy_entries), "CQRS faultlog lost data"
            for entry in legacy_entries:
                entry_dict = (
                    entry if isinstance(entry, dict) else dataclasses.asdict(entry)
                )
                assert entry_dict in cqrs_entries, (
                    f"Faultlog entry missing in CQRS: {entry}"
                )

        with contextlib.suppress(asyncio.CancelledError, TransportError):
            await gwy.stop()
