"""Legacy tracing test suite for identifying hidden topology rules.

CONTEXT FOR FUTURE SESSIONS:
----------------------------
This file was created during Phase 2.95 of the OSI Decoupling Master Plan.
We are transitioning from a synchronous, mutable graph architecture to an
asynchronous, event-driven CQRS architecture.

THE PROBLEM:
In the new architecture, packets containing unrecognised devices (or
schema conflicts) raise `DeviceNotFoundError` or `SchemaInconsistentError`.
These "poison pills" crash the new `asyncio.Queue` background tasks.
However, the legacy architecture survived these packets. We suspect the old
code had hidden suppression logic or alternative branching.

THE PURPOSE OF THIS TEST:
This test runs the legacy Gateway configuration with a highly filtered,
custom logger (`ramses_rf.legacy_trace`). It strips out all normal telemetry
noise and ONLY outputs when a topology mutation occurs or an exception is
raised at the structural boundary.

HOW TO USE:
1. Run this test via pytest: `pytest test_legacy_trace.py -s`
2. Collect the concise terminal output.
3. Provide the output to your AI Coding Partner to deduce the next
   instrumentation target for Iteration 2.
"""

from __future__ import annotations

import asyncio
import logging
import sys

import pytest

from ramses_rf.gateway import Gateway, GatewayConfig
from ramses_tx.config import EngineConfig

# Configure the targeted trace logger to intercept our custom hooks
_TRACE = logging.getLogger("ramses_rf.legacy_trace")
_TRACE.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(
    logging.Formatter("[LEGACY_TRACE] %(module)s.%(funcName)s | %(message)s")
)
_TRACE.addHandler(handler)

# Prevent propagation to the root logger to keep the terminal perfectly clean
_TRACE.propagate = False


@pytest.mark.asyncio
async def test_trace_poison_pill_packets() -> None:
    """Feed the legacy configuration a minimal dataset to trace exceptions."""

    # 1. Arrange: Setup exact configuration from test_topology_isolated.py
    INPUT_FILE = (
        "/home/phil/software/ramses_cc/tests/tests_new/fixtures/"
        "default/packets_rcvd.log"
    )

    known_list = {
        "01:145038": {"class": "CTL"},
        "03:123456": {"class": "THM", "faked": True},
        "10:123456": {"class": "OTB"},
        "18:006402": {"class": "HGI"},
        "13:120241": {"class": "BDR"},
        "13:120242": {"class": "BDR"},
        "07:046947": {"class": "DHW"},
        "34:092243": {"class": "THM"},
        "04:056053": {"class": "TRV"},
        "22:140285": {"class": "THM"},
        "04:189082": {"class": "TRV"},
        "13:081775": {"class": "BDR"},
        "13:202850": {"class": "BDR"},
        "32:097710": {"class": "CO2"},
        "32:139773": {"class": "HUM"},
    }

    schema = {
        "main_tcs": "01:145038",
        "01:145038": {
            "system": {"appliance_control": "10:123456"},
            "zones": {"00": {"sensor": "01:145038"}},
        },
    }

    engine_config = EngineConfig(
        disable_qos=True,
        input_file=INPUT_FILE,
        enforce_known_list=True,
        disable_sending=True,
    )

    gwy_config = GatewayConfig(
        disable_discovery=True,
        engine=engine_config,
        known_list=known_list,
        schema=schema,
    )

    _TRACE.info("Starting isolated trace gateway...")
    gwy = Gateway(port_name=None, config=gwy_config)

    # 2. Act: Start the gateway and let the packet log stream through
    await gwy.start()

    # Flush pending tasks to ensure all _handle_msg callbacks execute
    for _ in range(50):
        await asyncio.sleep(0)

    await gwy.stop()

    # 3. Assert: We are relying on terminal output analysis.
    _TRACE.info("Trace run complete.")
    assert True
