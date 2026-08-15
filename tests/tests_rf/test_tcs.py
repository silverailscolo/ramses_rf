#!/usr/bin/env python3
"""RAMSES RF - Unit tests for Evohome TCS system operations."""

import asyncio
from datetime import datetime as dt
from typing import Any, Final
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest

from ramses_rf import Gateway
from ramses_rf.const import Code
from ramses_rf.gateway import GatewayConfig
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
    pkt = Packet.from_port(dt.now(), PKT_3150)
    fake_evofw3._engine._protocol.pkt_received(pkt)
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
