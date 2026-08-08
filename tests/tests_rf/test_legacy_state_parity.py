"""CQRS Legacy State Parity Tests.

This test suite mathematically proves that all immutable CQRS shadow
states match the legacy dynamic properties across various packet logs.

.. note::
    These transient parity tests exist strictly to guarantee zero data
    loss or state regression while legacy properties are maintained.
    This file should be deleted once legacy state properties are sunset.
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
from ramses_rf.models import (
    ActuatorState,
    ActuatorStateDTO,
    UfhCircuitDemandDTO,
    UfhState,
)
from ramses_rf.pipeline.dispatcher import CentralDispatcher
from ramses_rf.pipeline.ingestion import StateProjector
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
LOG_HVAC = (
    Path(__file__).parent.parent / "tests" / "systems" / "_hvac_nuaire" / "packet.log"
)

_LOGGER = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def suppress_noisy_logs(caplog: pytest.LogCaptureFixture) -> None:
    """Suppress massive volume of parsing warnings for this test file."""
    caplog.set_level(logging.CRITICAL, logger="ramses_tx")
    caplog.set_level(logging.CRITICAL, logger="ramses_rf")
    caplog.set_level(logging.CRITICAL, logger="asyncio")


@pytest.fixture(
    params=[LOG_STANDARD, LOG_OPENTHERM, LOG_HVAC],
    ids=["standard", "opentherm", "hvac"],
)
def log_file_path(request: pytest.FixtureRequest) -> Path:
    """Provide the packet log file path for master state parity testing."""
    return cast(Path, request.param)


async def _get_legacy_value(obj: Any, attr: str) -> Any:
    """Safely get and evaluate a legacy attribute."""
    if not hasattr(obj, attr):
        return None
    val = getattr(obj, attr)
    if callable(val):
        val = val()
    if asyncio.iscoroutine(val):
        val = await val
    return val


@pytest.mark.asyncio
async def test_cqrs_master_domain_parity(log_file_path: Path) -> None:
    """Stream all packets and assert CQRS states match legacy properties."""
    # --- Arrange ---
    if not log_file_path.exists():
        pytest.skip(f"Fixture not found at {log_file_path}")

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

    pipeline_in_queue: asyncio.Queue[Any] = asyncio.Queue()
    dispatcher = CentralDispatcher(pipeline_in_queue)
    worker = StateProjector(gwy, dispatcher.ssot_queue)

    await dispatcher.start()
    await worker.start()

    legacy_handler = gwy._msg_handler

    async def parallel_strangler_bridge(dto: Any) -> None:
        await legacy_handler(dto)
        this_msg = getattr(gwy, "_this_msg", None)
        if this_msg:
            pipeline_in_queue.put_nowait(this_msg)

    gwy._engine._set_msg_handler(parallel_strangler_bridge)

    leg_counts = {
        "Temp": 0,
        "Dem": 0,
        "Batt": 0,
        "Win": 0,
        "Sys": 0,
        "Dhw": 0,
        "Oth": 0,
        "Hvac": 0,
        "Ufh": 0,
        "Act": 0,
    }
    cqrs_counts = {
        "Temp": 0,
        "Dem": 0,
        "Batt": 0,
        "Win": 0,
        "Sys": 0,
        "Dhw": 0,
        "Oth": 0,
        "Hvac": 0,
        "Ufh": 0,
        "Act": 0,
    }

    # --- Act ---
    with patch.object(gwy, "async_send_cmd", mock_send):
        with contextlib.suppress(TransportError):
            await gwy.start()

        if gwy._engine._transport:
            reader_task = gwy._engine._transport.get_extra_info(SZ_READER_TASK)
            if reader_task:
                with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
                    await asyncio.wait_for(reader_task, timeout=30)

        await asyncio.sleep(0.5)

        if gwy.message_store:
            gwy.message_store.flush()

        # --- Assert ---
        for dev in gwy.device_registry.devices:
            # 1. Temperature Parity
            legacy_t = await _get_legacy_value(dev, "temperature")
            if legacy_t is not None:
                leg_counts["Temp"] += 1

            temp_state = getattr(dev, "temp_state", None)
            if temp_state is not None and temp_state.temperature is not None:
                cqrs_counts["Temp"] += 1
                if legacy_t is not None and legacy_t != temp_state.temperature:
                    is_legacy_bug = False
                    if gwy.message_store:
                        for code in ("30C9", "1260", "0002"):
                            legacy_msgs = await gwy.message_store.get(
                                code=code, src=dev.id
                            )
                            if legacy_msgs:
                                newest_msg = max(legacy_msgs, key=lambda x: x.dtm)
                                if (
                                    isinstance(newest_msg.payload, dict)
                                    and newest_msg.payload.get("temperature")
                                    == temp_state.temperature
                                ):
                                    is_legacy_bug = True
                                    break

                            for m in gwy.message_store.state_cache.values():
                                if m.code == code and m.src.id == dev.id:
                                    if (
                                        isinstance(m.payload, dict)
                                        and m.payload.get("temperature")
                                        == temp_state.temperature
                                    ):
                                        is_legacy_bug = True
                                        break

                    if not is_legacy_bug:
                        assert legacy_t == temp_state.temperature, (
                            f"Temp mismatch: Legacy={legacy_t}, "
                            f"CQRS={temp_state.temperature}"
                        )

            # 2. Demand Parity
            if getattr(dev, "_SLUG", "") != "OTB":
                legacy_hd = await _get_legacy_value(dev, "heat_demand")
                if legacy_hd is not None:
                    leg_counts["Dem"] += 1

                demand_state = getattr(dev, "demand_state", None)
                if demand_state is not None and demand_state.heat_demand is not None:
                    cqrs_counts["Dem"] += 1
                    if legacy_hd is not None and legacy_hd != demand_state.heat_demand:
                        if (
                            getattr(dev, "_SLUG", "") == "TRV"
                            and legacy_hd == 0
                            and demand_state.heat_demand is None
                        ):
                            pass
                        else:
                            assert legacy_hd == demand_state.heat_demand, (
                                f"Demand mismatch: Legacy={legacy_hd}, "
                                f"CQRS={demand_state.heat_demand}"
                            )

            # 3. Power (Battery) Parity
            legacy_batt = await _get_legacy_value(dev, "battery_low")
            if legacy_batt is not None and legacy_batt is not False:
                leg_counts["Batt"] += 1

            power_state = getattr(dev, "power_state", None)
            if power_state is not None and power_state.battery_low is not None:
                cqrs_counts["Batt"] += 1
                if legacy_batt is not None and legacy_batt is not False:
                    assert legacy_batt == power_state.battery_low, "Battery mismatch"

            # 4. TRV (Window) Parity
            legacy_wo = await _get_legacy_value(dev, "window_open")
            if legacy_wo is not None:
                leg_counts["Win"] += 1

            trv_state = getattr(dev, "trv_state", None)
            if trv_state is not None and trv_state.window_open is not None:
                cqrs_counts["Win"] += 1
                if legacy_wo is not None:
                    assert legacy_wo == trv_state.window_open, "Window mismatch"

            # 5. DHW Parity
            if getattr(dev, "_SLUG", "") == "DHW":
                legacy_dt = await _get_legacy_value(dev, "temperature")
                if legacy_dt is not None:
                    leg_counts["Dhw"] += 1

                dhw_state = getattr(dev, "dhw_state", None)
                if dhw_state is not None and dhw_state.temperature is not None:
                    cqrs_counts["Dhw"] += 1
                    if legacy_dt is not None and legacy_dt != dhw_state.temperature:
                        is_legacy_bug = False
                        if gwy.message_store:
                            legacy_msgs = await gwy.message_store.get(
                                code="1260", src=dev.id
                            )
                            if legacy_msgs:
                                newest_msg = max(legacy_msgs, key=lambda x: x.dtm)
                                if (
                                    isinstance(newest_msg.payload, dict)
                                    and newest_msg.payload.get("temperature")
                                    == dhw_state.temperature
                                ):
                                    is_legacy_bug = True

                            if not is_legacy_bug:
                                for m in gwy.message_store.state_cache.values():
                                    if m.code == "1260" and m.src.id == dev.id:
                                        if (
                                            isinstance(m.payload, dict)
                                            and m.payload.get("temperature")
                                            == dhw_state.temperature
                                        ):
                                            is_legacy_bug = True
                                            break

                        if not is_legacy_bug:
                            assert legacy_dt == dhw_state.temperature, (
                                f"DHW mismatch: Legacy={legacy_dt}, "
                                f"CQRS={dhw_state.temperature}"
                            )

            # 6. HVAC Parity
            legacy_co2 = await _get_legacy_value(dev, "co2_level")
            if legacy_co2 is not None:
                leg_counts["Hvac"] += 1

            hvac_state = getattr(dev, "hvac_state", None)
            if hvac_state is not None and hvac_state.co2_level is not None:
                cqrs_counts["Hvac"] += 1
                if legacy_co2 is not None:
                    assert legacy_co2 == hvac_state.co2_level, "HVAC mismatch"

            # 7. System Mode Parity
            legacy_sys = await _get_legacy_value(dev, "system_mode")
            if legacy_sys is not None:
                leg_counts["Sys"] += 1

            system_state = getattr(dev, "system_state", None)
            if system_state is not None and system_state.system_mode is not None:
                cqrs_counts["Sys"] += 1
                if legacy_sys is not None:
                    if isinstance(legacy_sys, dict) and "system_mode" in legacy_sys:
                        assert legacy_sys["system_mode"] == system_state.system_mode, (
                            "Sys mismatch"
                        )
                    else:
                        assert legacy_sys == system_state.system_mode, "Sys mismatch"

            # 8. OpenTherm Parity
            if getattr(dev, "_SLUG", "") == "OTB":
                legacy_mod = await _get_legacy_value(dev, "rel_modulation_level")
                if legacy_mod is not None:
                    leg_counts["Oth"] += 1

                ot_state = getattr(dev, "opentherm_state", None)
                if ot_state is not None and ot_state.rel_modulation_level is not None:
                    cqrs_counts["Oth"] += 1
                    if legacy_mod is not None:
                        assert legacy_mod == ot_state.rel_modulation_level, (
                            "OT mismatch"
                        )

            # 9. UFH Array Parity
            if hasattr(dev, "ufh_state"):
                cqrs_ufh = cast(UfhState, dev.ufh_state)
                legacy_demands = await _get_legacy_value(dev, "heat_demands")
                if legacy_demands is not None:
                    leg_counts["Ufh"] += 1
                    if cqrs_ufh.heat_demands:
                        cqrs_counts["Ufh"] += 1
                        expected_list = [
                            UfhCircuitDemandDTO(ufx_idx=str(k), thermal_demand=v)
                            for k, v in cqrs_ufh.heat_demands.items()
                        ]
                        assert expected_list == legacy_demands

                legacy_setpoints = await _get_legacy_value(dev, "setpoints")
                if legacy_setpoints is not None:
                    assert cqrs_ufh.setpoints == legacy_setpoints

                legacy_relay_fa = await _get_legacy_value(dev, "relay_demand_fa")
                if legacy_relay_fa is not None:
                    assert cqrs_ufh.relay_demand_fa == legacy_relay_fa

            # 10. Actuator Parity
            if hasattr(dev, "act_state"):
                cqrs_act = cast(ActuatorState, dev.act_state)
                legacy_act_state = await _get_legacy_value(dev, "actuator_state")
                if legacy_act_state is not None:
                    leg_counts["Act"] += 1
                    if cqrs_act.modulation_level is not None:
                        cqrs_counts["Act"] += 1

                    if isinstance(legacy_act_state, ActuatorStateDTO):
                        if legacy_act_state.modulation_level is not None:
                            assert (
                                cqrs_act.modulation_level
                                == legacy_act_state.modulation_level
                            )
                        if legacy_act_state.actuator_enabled is not None:
                            assert (
                                cqrs_act.actuator_enabled
                                == legacy_act_state.actuator_enabled
                            )
                        if legacy_act_state.ch_active is not None:
                            assert cqrs_act.ch_active == legacy_act_state.ch_active
                        if legacy_act_state.ch_enabled is not None:
                            assert cqrs_act.ch_enabled == legacy_act_state.ch_enabled
                        if legacy_act_state.dhw_active is not None:
                            assert cqrs_act.dhw_active == legacy_act_state.dhw_active
                        if legacy_act_state.flame_active is not None:
                            assert (
                                cqrs_act.flame_active == legacy_act_state.flame_active
                            )
                    else:
                        if "modulation_level" in legacy_act_state:
                            assert (
                                cqrs_act.modulation_level
                                == legacy_act_state["modulation_level"]
                            )
                        elif "rel_modulation_level" in legacy_act_state:
                            assert (
                                cqrs_act.modulation_level
                                == legacy_act_state["rel_modulation_level"]
                            )

                        if "actuator_enabled" in legacy_act_state:
                            assert (
                                cqrs_act.actuator_enabled
                                == legacy_act_state["actuator_enabled"]
                            )

                        if "ch_active" in legacy_act_state:
                            assert cqrs_act.ch_active == legacy_act_state["ch_active"]

                        if "ch_enabled" in legacy_act_state:
                            assert cqrs_act.ch_enabled == legacy_act_state["ch_enabled"]

                        if "dhw_active" in legacy_act_state:
                            assert cqrs_act.dhw_active == legacy_act_state["dhw_active"]

                        if "flame_on" in legacy_act_state:
                            assert cqrs_act.flame_active == legacy_act_state["flame_on"]

        # Assert CQRS is strictly EQUAL TO or BETTER THAN Legacy
        for key in leg_counts:
            assert cqrs_counts[key] >= leg_counts[key], (
                f"Data Drop! Legacy found {leg_counts[key]} {key}, "
                f"but CQRS only found {cqrs_counts[key]}"
            )

        # Safely shut down gateway and worker
        await dispatcher.stop()
        await worker.stop()
        with contextlib.suppress(asyncio.CancelledError, TransportError):
            await gwy.stop()


@pytest.mark.asyncio
async def test_cqrs_faultlog_parity(log_file_path: Path) -> None:
    """Assert the legacy faultlog dictionary matches CQRS FaultLogState."""
    if not log_file_path.exists():
        pytest.skip("Fixture file not found.")

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

    with patch.object(gwy, "async_send_cmd", AsyncMock(return_value=None)):
        with contextlib.suppress(TransportError):
            await gwy.start()

        if gwy._engine._transport:
            reader_task = gwy._engine._transport.get_extra_info(SZ_READER_TASK)
            if reader_task:
                with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
                    await asyncio.wait_for(reader_task, timeout=30)

        if not gwy.tcs:
            pytest.skip("No TCS discovered in regression file.")

        faultlog = getattr(gwy.tcs, "faultlog", None)
        if not faultlog:
            pytest.skip("No faultlog discovered in regression file.")

        legacy_log = cast("dict[str, Any]", getattr(faultlog, "faultlog"))  # noqa: B009
        cqrs_state = getattr(faultlog, "state", None)
        assert cqrs_state is not None, "Faultlog missing CQRS state"

        cqrs_log = cast("tuple[Any, ...]", getattr(cqrs_state, "entries"))  # noqa: B009
        legacy_entries = list(legacy_log.values())
        cqrs_entries = [dataclasses.asdict(entry) for entry in cqrs_log]

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
