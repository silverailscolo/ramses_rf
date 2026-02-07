"""Regression tests for the application layer (Gateway state)."""

import asyncio
import contextlib
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from syrupy.assertion import SnapshotAssertion

from ramses_rf import Gateway
from ramses_rf.device import DeviceHeat, DeviceHvac
from ramses_tx.exceptions import TransportError
from ramses_tx.transport import SZ_READER_TASK

# Navigate up from tests/tests_rf/test_regression_rf.py to tests/fixtures/
FIXTURE_FILE = Path(__file__).parents[1] / "fixtures" / "regression_packets.txt"


def serialize_device(dev: Any) -> dict[str, Any]:
    """Helper to serialize a device's state for snapshotting."""
    # Base attributes for all devices
    data: dict[str, Any] = {
        "id": dev.id,
        "type": type(dev).__name__,
        "is_alive": getattr(dev, "_is_alive", None),
    }

    # Capture specific state for Heating devices (e.g., TRVs, Controllers)
    if isinstance(dev, DeviceHeat):
        # Safely access zone index; dev.zone might be None or (rarely) an object without idx
        # e.g. An Evohome controller might be its own zone parent but lack an idx attribute
        zone = getattr(dev, "zone", None)
        zone_idx = getattr(zone, "idx", None)

        tcs = getattr(dev, "tcs", None)
        tcs_id = tcs.id if tcs else None

        data.update(
            {
                "tcs_id": tcs_id,
                "zone_idx": zone_idx,
            }
        )

    # Capture specific state for HVAC devices
    if isinstance(dev, DeviceHvac):
        data.update(
            {
                # Add HVAC specific fields if available/relevant
            }
        )

    return data


@pytest.mark.asyncio
async def test_gateway_replay_regression(snapshot: SnapshotAssertion) -> None:
    """Replay the packet log and snapshot the final Gateway state.

    This ensures that processing the same packets always results in the same
    device discovery, schema generation, and system state.
    """
    if not FIXTURE_FILE.exists():
        raise FileNotFoundError(f"Fixture not found at {FIXTURE_FILE}")

    # 1. Initialize Gateway with FileTransport
    # reduce_processing=0 ensures full processing (Parsing + State)
    # config options set to prevent networking attempts
    gwy = Gateway(
        None,  # port_name is required (positional arg)
        input_file=str(FIXTURE_FILE),
        config={
            "disable_discovery": True,
            "disable_sending": True,
            "reduce_processing": 0,
        },
    )

    # 2. Patch sending methods to prevent "Read-Only" errors & background noise.
    # The gateway logic might try to reply to RQs found in the logs.
    # We use a MagicMock that returns an awaitable (Future) resolving to None.
    mock_send = MagicMock(return_value=asyncio.Future())
    mock_send.return_value.set_result(None)

    with patch.object(gwy, "async_send_cmd", mock_send):
        # 3. Start the Gateway (spawns the reader task)
        # The library's `start()` method has a strict 1s timeout for file parsing.
        # Large regression files take longer, raising TransportError.
        # We catch this expected timeout gracefully.
        with contextlib.suppress(TransportError):
            await gwy.start()

        # 4. Wait for the Transport to finish reading the file
        # Instead of relying on the possibly-cancelled protocol future,
        # we await the specific reader task responsible for file processing.
        if gwy._transport:
            reader_task = gwy._transport.get_extra_info(SZ_READER_TASK)
            if reader_task:
                await reader_task

        # 5. Extract State for Snapshot
        # We create a deterministic dictionary of the system state
        system_state: dict[str, Any] = {
            "schema": gwy.schema,
            "devices": [
                serialize_device(d) for d in sorted(gwy.devices, key=lambda x: x.id)
            ],
        }

        # Add specific System (TCS) details if a TCS was discovered
        if gwy.tcs:
            system_state["tcs"] = {
                "id": gwy.tcs.id,
                "zones": {
                    z.idx: {
                        "name": z.name,
                        "type": type(z).__name__,
                        "sensor": z.sensor.id if z.sensor else None,
                        "actuators": sorted([a.id for a in z.actuators]),
                    }
                    for z in sorted(gwy.tcs.zones, key=lambda x: x.idx)
                },
            }

        # 6. Stop Gateway
        # We suppress CancelledError because the initial start() timeout likely
        # cancelled the internal connection_lost future, which stop() tries to await.
        with contextlib.suppress(asyncio.CancelledError, TransportError):
            await gwy.stop()

    # 7. Assert Snapshot
    assert snapshot == system_state
