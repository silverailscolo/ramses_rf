"""
Automated execution tracer for ramses_rf packet processing.

This script traces the OpenTherm (3220) parsing and routing logic,
capturing how hex payloads are translated into OtDataId metrics and
routed to the OtbGateway in both bootstrap and steady-state.
"""

import asyncio
import sys
from collections.abc import Callable
from datetime import datetime as dt
from types import FrameType
from typing import Any, Final

import pytest

from ramses_rf import Gateway
from ramses_tx import Packet
from ramses_tx.address import HGI_DEVICE_ID
from ramses_tx.dtos import PacketDTO

# 1. System Bootstrap: Creates Controller and TCS
PKT_3150_SYS: Final = "064  I --- 01:078710 --:------ 01:078710 3150 002 FCC8"

# 2. OpenTherm Request (RQ) from Controller to OTB (DataId 5 - Fault Flags)
PKT_3220_RQ: Final = "066 RQ --- 01:078710 10:067219 --:------ 3220 005 0000050000"

# 3. OpenTherm Response (RP) from OTB to Controller (DataId 5 - Fault Flags)
PKT_3220_RP: Final = "065 RP --- 10:067219 01:078710 --:------ 3220 005 00C00500FF"


@pytest.fixture()
def gwy_config() -> dict[str, Any]:
    """
    Return a valid configuration dictionary for the gateway.

    :return: An empty configuration dict.
    :rtype: dict[str, Any]
    """
    return {}


@pytest.fixture()
def gwy_dev_id() -> str:
    """
    Return a valid device ID for the virtual gateway.

    :return: The default HGI device ID.
    :rtype: str
    """
    return HGI_DEVICE_ID


class RamsesTracer:
    """
    Custom execution tracer for the ramses_rf codebase.

    Filters execution frames to OpenTherm parsers and Gateway devices.
    """

    def __init__(self) -> None:
        """Initialize the tracer with a depth counter."""
        self.depth = 1

    def global_trace(
        self, frame: FrameType, event: str, arg: Any
    ) -> Callable[[FrameType, str, Any], Any] | None:
        """
        Global trace function to catch function calls.

        :param frame: The current stack frame.
        :type frame: FrameType
        :param event: The trace event type (e.g., 'call', 'return').
        :type event: str
        :param arg: Additional event arguments.
        :type arg: Any
        :return: The local trace function or None if filtered out.
        :rtype: Callable[[FrameType, str, Any], Any] | None
        """
        if event == "call":
            filename = frame.f_code.co_filename
            # Target the parsers and the physical devices
            if (
                any(
                    target in filename
                    for target in [
                        "ramses_tx/protocol",
                        "ramses_rf/device",
                        "opentherm",
                        "parsers",
                    ]
                )
                and "test_" not in filename
            ):
                func_name = frame.f_code.co_name

                # Extract the class name if the function is a method
                cls_name = ""
                if "self" in frame.f_locals:
                    cls_name = f"{frame.f_locals['self'].__class__.__name__}."

                indent = "  " * self.depth
                print(f"{indent}-> {cls_name}{func_name}()")

                # Trap payload states during routing
                if func_name == "_handle_msg" and "msg" in frame.f_locals:
                    msg = frame.f_locals["msg"]
                    if hasattr(msg, "payload"):
                        print(f"{indent}   [Payload State]: {msg.payload}")

                self.depth += 1
                return self.local_trace

        return None

    def local_trace(
        self, frame: FrameType, event: str, arg: Any
    ) -> Callable[[FrameType, str, Any], Any] | None:
        """
        Local trace function to track function returns and adjust depth.

        :param frame: The current stack frame.
        :type frame: FrameType
        :param event: The trace event type.
        :type event: str
        :param arg: Additional event arguments.
        :type arg: Any
        :return: Itself if tracing should continue, else None.
        :rtype: Callable[[FrameType, str, Any], Any] | None
        """
        if event == "return":
            self.depth -= 1
        return self.local_trace


@pytest.mark.asyncio
async def test_trace_opentherm_3220(fake_evofw3: Gateway) -> None:
    """
    Inject 3220 packets and trace the OpenTherm parsing and routing.

    :param fake_evofw3: The mocked Gateway fixture provided by pytest.
    :type fake_evofw3: Gateway
    """
    gwy = fake_evofw3

    # Backup the original handler
    original_handler = gwy._msg_handler

    # Create surgical wrapper for the parsing pipeline
    async def _traced_handler(dto: PacketDTO) -> None:
        # Only trace 3220 packets to avoid noise
        if "3220" not in str(dto):
            return await original_handler(dto)

        tracer = RamsesTracer()
        sys.settrace(tracer.global_trace)
        print(f"\n=== OPEN THERM PIPELINE: 3220 {dto.verb} ===")
        try:
            await original_handler(dto)
        finally:
            sys.settrace(None)

    # Monkey-patch the gateway engine
    gwy._engine._set_msg_handler(_traced_handler)

    try:
        # 1. Bootstrap Topology (Un-traced)
        gwy._engine._protocol.pkt_received(Packet.from_port(dt.now(), PKT_3150_SYS))
        await asyncio.sleep(0.1)

        # 2. Inject 3220 RQ (Controller asking OTB)
        print("\n--- INJECTING 3220 RQ ---")
        gwy._engine._protocol.pkt_received(Packet.from_port(dt.now(), PKT_3220_RQ))
        await asyncio.sleep(0.1)

        # 3. Inject 3220 RP (OTB replying to Controller - Bootstrap Cycle)
        print("\n--- INJECTING 3220 RP (CYCLE 1: BOOTSTRAP) ---")
        gwy._engine._protocol.pkt_received(Packet.from_port(dt.now(), PKT_3220_RP))
        await asyncio.sleep(0.1)

        # 4. Inject 3220 RP again (OTB replying to Controller - Steady-State Cycle)
        print("\n--- INJECTING 3220 RP (CYCLE 2: STEADY-STATE) ---")
        gwy._engine._protocol.pkt_received(Packet.from_port(dt.now(), PKT_3220_RP))
        await asyncio.sleep(0.1)

    finally:
        # Cleanup hooks
        gwy._engine._set_msg_handler(original_handler)
