"""Phase 1: Legacy Characterisation Testing for Eavesdropping."""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
from unittest.mock import patch

import pytest

from ramses_rf import Gateway
from ramses_rf.config import GatewayConfig
from ramses_rf.messages.base import Message
from ramses_tx.packet import Packet

# THE RAW DATA EXEMPTION: Exempt from line-length wrapping
TRV_PACKETS = [
    "2021-11-11T11:11:01.001111 ...  I --- 04:111111 --:------ 01:123456 1060 003 01FF01",
    "2021-11-11T11:11:02.002222 ...  I --- 04:222222 --:------ 01:123456 12B0 003 020000",
    "2021-11-11T11:11:03.003333 ...  I --- 04:333333 --:------ 01:123456 2309 003 03076C",
    "2021-11-11T11:11:04.004444 ...  I --- 04:444444 --:------ 01:123456 3150 002 043C",
    "2021-11-11T11:12:06.001111 ...  I --- 04:666666 --:------ 01:123456 1060 003 00FF01",
    "2021-11-11T11:12:07.002222 ...  I --- 04:777777 --:------ 01:123456 12B0 003 070000",
    "2021-11-11T11:12:08.003333 ...  I --- 04:888888 --:------ 01:123456 2309 003 08076C",
    "2021-11-11T11:12:09.004444 ...  I --- 04:999999 --:------ 01:123456 3150 002 093C",
    "2021-11-11T11:13:06.006666 ...  I --- 04:616161 --:------ 01:123456 1060 003 00FF01",
    "2021-11-11T11:13:07.007777 ...  I --- 04:717171 --:------ 01:123456 12B0 003 070000",
    "2021-11-11T11:13:08.008888 ...  I --- 04:818181 --:------ 01:123456 2309 003 08076C",
    "2021-11-11T11:13:09.009999 ...  I --- 04:919191 --:------ 01:123456 3150 002 093C",
]

HVAC_PACKETS = [
    "2021-11-11T11:14:01.000000 ...  I --- 32:111111 --:------ 32:111111 1298 003 0030C8",
    "2021-11-11T11:14:02.000000 ...  I --- 32:222222 --:------ 01:123456 31D9 003 000000",
]


def _create_message(log_line: str) -> Message:
    """Parse a raw string into a robust ramses_rf Message."""
    dt_str = log_line.split()[0]

    # Find the exact index of the verb to preserve leading whitespace perfectly
    verb_idx = -1
    for verb in (" I ---", " W ---", "RQ ---", "RP ---"):
        verb_idx = log_line.find(verb)
        if verb_idx != -1:
            break

    if verb_idx == -1:
        raise ValueError(f"Could not locate verb in log line: {log_line}")

    # Extract the core frame and strip comments
    frame_core = log_line[verb_idx:].split("#")[0].rstrip()

    # Prepend dummy RSSI exactly as the L3 parser expects (4 chars: "000 ")
    frame = f"000 {frame_core}"

    pkt = Packet.from_file(dt_str, frame)
    return Message._from_pkt(pkt)


@pytest.mark.asyncio
async def test_trace_legacy_topology_discovery() -> None:
    """Trace how the legacy Gateway handled eavesdropped topology events."""
    with tempfile.NamedTemporaryFile() as tmp:
        config = GatewayConfig(enable_eavesdrop=True)
        config.disable_discovery = True
        config.engine.input_file = tmp.name

        gwy = Gateway(config=config)
        await gwy.start(start_discovery=False)
        await asyncio.sleep(0.01)

        # Spying on DeviceRegistry to catch explicit binding calls from Zone._handle_msg
        with contextlib.ExitStack() as stack:
            get_dev_spy = stack.enter_context(
                patch.object(
                    gwy.device_registry,
                    "get_device",
                    wraps=gwy.device_registry.get_device,
                )
            )

            print("\n\n--- STARTING TRV EAVESDROP TRACE ---")
            for i, line in enumerate(TRV_PACKETS):
                msg = _create_message(line)

                # Route the packet via the exact same pipeline real radio data uses
                await gwy._msg_handler(msg._dto)

                # Catch topological parent/child bindings
                print(f"\n[{i}] Processed: {msg.code} from {msg.src.id}")
                if get_dev_spy.call_count > 0:
                    for call in get_dev_spy.call_args_list:
                        _, kwargs = call
                        if kwargs.get("parent") is not None:
                            dev_id = (
                                call.args[0] if call.args else kwargs.get("device_id")
                            )
                            role = "SENSOR" if kwargs.get("is_sensor") else "ACTUATOR"
                            parent = kwargs.get("parent")
                            child = kwargs.get("child_id", "Unknown")
                            print(
                                f"  -> BINDING TRACE: Legacy linked {dev_id} as "
                                f"{role} to {parent.id} (child_id={child})"
                            )
                    get_dev_spy.reset_mock()

            print("\n\n--- STARTING HVAC EAVESDROP TRACE ---")
            for i, line in enumerate(HVAC_PACKETS):
                msg = _create_message(line)

                pre_dev_classes = {
                    d.id: d.__class__.__name__ for d in gwy.device_registry.devices
                }

                await gwy._msg_handler(msg._dto)

                post_dev_classes = {
                    d.id: d.__class__.__name__ for d in gwy.device_registry.devices
                }
                print(f"\n[{i}] Processed HVAC: {msg.code} from {msg.src.id}")

                for dev_id, klass_name in post_dev_classes.items():
                    old_klass = pre_dev_classes.get(dev_id, "None")
                    if old_klass != klass_name:
                        print(
                            f"  -> PROMOTION TRACE: {dev_id} transitioned from "
                            f"{old_klass} to {klass_name}"
                        )

        devices = sorted(
            [f"{d.id} ({d.__class__.__name__})" for d in gwy.device_registry.devices]
        )
        print(f"\n\n--- FINAL DEVICES DISCOVERED ---\n{devices}\n")

        await gwy.stop()
