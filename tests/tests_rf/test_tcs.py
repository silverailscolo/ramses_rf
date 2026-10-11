#!/usr/bin/env python3
"""RAMSES RF - Unit tests for Evohome TCS system operations."""

import asyncio
from datetime import UTC, datetime as dt
from typing import Any, Final
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest

from ramses_rf import Gateway
from ramses_rf.const import Code
from ramses_rf.gateway import GatewayConfig
from ramses_rf.messages import Message
from ramses_rf.systems import Evohome
from ramses_tx import Packet
from ramses_tx.address import HGI_DEVICE_ID, Address
from ramses_tx.typing import DeviceIdT

TST_ID_ = Address("18:123456").id
PKT_3150: Final = (
    f"064  I --- 01:145038 --:------ 01:145038 {Code._3150} 002 FCC8"
)

pytestmark = pytest.mark.asyncio()


@pytest.fixture()
def gwy_config() -> dict[str, Any]:
    """Return a gateway test configuration."""
    return {
        "config": GatewayConfig(disable_discovery=True),
        "disable_qos": False,
        "enforce_known_list": False,
        "known_list": {HGI_DEVICE_ID: {}},
    }


@pytest.fixture()
def gwy_dev_id() -> DeviceIdT:
    """Return device ID fixture."""
    return TST_ID_


@pytest.mark.asyncio
async def test_tcs_lockless_concurrent_schedules(fake_evofw3: Gateway) -> None:
    """Verify that multiple zones on the same TCS execute schedules concurrently.

    Lockless scheduling allows zone schedules to be requested concurrently
    without raising lock contention timeouts.
    """

    # Arrange: Bootstrap TCS via packet ingestion
    packet = Packet.from_port(dt.now(), PKT_3150)
    fake_evofw3._engine._protocol.packet_received(packet)
    await asyncio.sleep(0)

    tcs: Evohome | None = fake_evofw3.tcs
    assert isinstance(tcs, Evohome)

    zone0 = tcs.get_htg_zone("00")
    zone1 = tcs.get_htg_zone("01")

    # Act & Assert
    with (
        patch.object(
            zone0._schedule, "get_schedule", new=AsyncMock(return_value=[])
        ),
        patch.object(
            zone1._schedule, "get_schedule", new=AsyncMock(return_value=[])
        ),
        patch.object(
            type(zone0._schedule),
            "schedule",
            new_callable=PropertyMock,
            return_value=[],
        ),
    ):
        task0 = asyncio.create_task(zone0.get_schedule())
        task1 = asyncio.create_task(zone1.get_schedule())

        results = await asyncio.gather(task0, task1, return_exceptions=True)

    assert results[0] == []
    assert results[1] == []
    assert not any(isinstance(r, Exception) for r in results)


@pytest.mark.asyncio
async def test_schedule_version_cached_aware_dtm(fake_evofw3: Gateway) -> None:
    """Regression: cached 0006 messages may carry tz-aware timestamps.

    Depending on the transport, packet dtms can be tz-aware; the
    cached-value check in _schedule_version must not raise TypeError
    comparing them with a naive dt.now().
    """

    # Arrange: Bootstrap TCS via packet ingestion
    packet = Packet.from_port(dt.now(), PKT_3150)
    fake_evofw3._engine._protocol.packet_received(packet)
    await asyncio.sleep(0)

    tcs: Evohome | None = fake_evofw3.tcs
    assert isinstance(tcs, Evohome)

    # Simulate a cached 0006 reply with a tz-aware timestamp
    pkt_0006 = Packet.from_port(
        dt.now(UTC), "RP --- 01:145038 18:123456 --:------ 0006 004 000500E6"
    )
    tcs._msg_0006 = Message._from_packet(pkt_0006)

    # Act & Assert: must serve from cache without raising TypeError
    global_ver, did_io = await tcs._schedule_version()

    assert global_ver == 230
    assert did_io is False
