#!/usr/bin/env python3
"""Unittests for the base device classes and HgiGateway.

This module combines tests for DeviceBase, HgiGateway, and BatteryState
which all reside in ramses_rf/device/base.py.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from collections.abc import Generator
from datetime import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ramses_rf.const import GATEWAY_MESSAGE_TIMEOUT
from ramses_rf.device.base import BatteryState, DeviceBase, HgiGateway
from ramses_rf.database import MessageIndex
from ramses_rf.device import HgiGateway
from ramses_rf.gateway import Gateway
from ramses_tx import Address
from ramses_tx.typing import DeviceIdT


@pytest.fixture
def mock_gateway() -> MagicMock:
    """Create a mock Gateway instance for testing.

    :return: A mocked Gateway object.
    :rtype: MagicMock
    """
    gwy = MagicMock(spec=Gateway)
    gwy.config.enable_eavesdrop = False
    gwy._engine = MagicMock()
    gwy._engine._this_msg = None
    return gwy


@pytest.fixture
def hgi_gateway(mock_gateway: MagicMock) -> HgiGateway:
    """Create an HgiGateway instance for testing.

    :param mock_gateway: The mock gateway fixture.
    :type mock_gateway: MagicMock
    :return: An initialized HgiGateway.
    :rtype: HgiGateway
    """
    # HGI devices always have an address starting with 18:
    return HgiGateway(mock_gateway, Address("18:123456"))


class TestDeviceBase:
    """Test the DeviceBase logic."""

    def test_heartbeat_availability(self, mock_gateway: MagicMock) -> None:
        """Test is_available heartbeat logic.

        :param mock_gateway: The mock gateway fixture.
        :type mock_gateway: MagicMock
        """
        dev = DeviceBase(mock_gateway, Address("34:123456"))

        # No messages yet - assume available
        assert dev.is_available

        # Recent message
        dev._last_msg_dtm = datetime.now(UTC)
        assert dev.is_available

        # Expired heartbeat (Default 1 hour)
        expired_dtm = datetime.now(UTC) - timedelta(hours=1, seconds=1)
        dev._last_msg_dtm = expired_dtm
        assert not dev.is_available

    def test_device_promotion_prevention(self, mock_gateway: MagicMock) -> None:
        """Test that non-promotable slugs don't trigger promotion.

        :param mock_gateway: The mock gateway fixture.
        :type mock_gateway: MagicMock
        """
        dev = DeviceBase(mock_gateway, Address("34:123456"))

        # Explicitly set slug to ensure it's not in PROMOTABLE_SLUGS
        dev._SLUG = "NON_PROMOTABLE_SLUG"

        msg = MagicMock()
        msg.dtm = datetime.now(UTC)

        dev._handle_msg(msg)

        # Verify the class was not promoted using __class__ to satisfy Mypy
        assert dev.__class__ is DeviceBase

    @pytest.mark.asyncio
    async def test_async_attributes(self, mock_gateway: MagicMock) -> None:
        """Test async baseline properties.

        :param mock_gateway: The mock gateway fixture.
        :type mock_gateway: MagicMock
        """
        dev = DeviceBase(mock_gateway, Address("34:123456"))
        assert await dev.schema() == {}
        assert await dev.params() == {}
        assert await dev.status() == {}


class TestBatteryState:
    """Test the BatteryState mixin class logic."""

    @pytest.mark.asyncio
    async def test_battery_methods_when_faked(self, mock_gateway: MagicMock) -> None:
        """Test battery_low and battery_state return defaults if faked.

        :param mock_gateway: The mock gateway fixture.
        :type mock_gateway: MagicMock
        """
        dev = BatteryState(mock_gateway, Address("04:123456"))

        # Simulate a faked device by attaching a mocked binding manager
        dev._binding_manager = MagicMock()
        dev._binding_manager.is_binding = False

        assert dev.is_faked
        assert await dev.battery_low() is False
        assert await dev.battery_state() is None


class TestHgiGateway:
    """Test HgiGateway class."""

    def test_initialization(self, hgi_gateway: HgiGateway) -> None:
        """Test that the gateway device initializes with expected defaults.

        :param hgi_gateway: The gateway fixture.
        :type hgi_gateway: HgiGateway
        """
        # Bypassing strict type inference with getattr
        assert getattr(hgi_gateway, "ctl", False) is None
        assert hgi_gateway._child_id == "gw"
        assert getattr(hgi_gateway, "tcs", False) is None

    @pytest.mark.asyncio
    async def test_is_active_no_msg(self, hgi_gateway: HgiGateway) -> None:
        """Test is_active returns False when no messages are received.

        :param hgi_gateway: The gateway fixture.
        :type hgi_gateway: HgiGateway
        """
        hgi_gateway._gwy._engine._this_msg = None
        assert not await hgi_gateway.is_active()

    @pytest.mark.asyncio
    async def test_is_active_recent_msg(self, hgi_gateway: HgiGateway) -> None:
        """Test is_active returns True when a recent message exists.

        :param hgi_gateway: The gateway fixture.
        :type hgi_gateway: HgiGateway
        """
        mock_msg = MagicMock()
        mock_msg.dtm = datetime.now(UTC)

        hgi_gateway._gwy._engine._this_msg = mock_msg
        assert await hgi_gateway.is_active()

    @pytest.mark.asyncio
    async def test_is_active_expired_msg(self, hgi_gateway: HgiGateway) -> None:
        """Test is_active returns False when the latest message is too old.

        :param hgi_gateway: The gateway fixture.
        :type hgi_gateway: HgiGateway
        """
        mock_msg = MagicMock()
        expired_dtm = datetime.now(UTC) - (
            GATEWAY_MESSAGE_TIMEOUT + timedelta(seconds=1)
        )
        mock_msg.dtm = expired_dtm

        hgi_gateway._gwy._engine._this_msg = mock_msg
        assert not await hgi_gateway.is_active()

    @pytest.mark.asyncio
    async def test_is_active_naive_datetime(self, hgi_gateway: HgiGateway) -> None:
        """Test is_active handles naive datetimes gracefully.

        :param hgi_gateway: The gateway fixture.
        :type hgi_gateway: HgiGateway
        """
        mock_msg = MagicMock()
        mock_msg.dtm = datetime.now()

        hgi_gateway._gwy._engine._this_msg = mock_msg
        assert await hgi_gateway.is_active()

    @pytest.mark.asyncio
    async def test_status_with_latest_dtm(self, hgi_gateway: HgiGateway) -> None:
        # Mock the parent class's status method
        latest_dt = dt(2023, 1, 1, 12, 0, 0)
        mock_parent_status = {"gateway_dtm": latest_dt}
        with patch.object(HgiGateway, "status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = mock_parent_status

            hgi_gateway.latest_dtm = latest_dt

            # Call the status method
            result = await hgi_gateway.status()

            # Assert the result
            assert result == {
                **mock_parent_status,
                "gateway_dtm": hgi_gateway.latest_dtm,
            }


    @pytest.mark.asyncio
    async def test_status_without_latest_dtm(self, hgi_gateway: HgiGateway) -> None:
        # Mock the parent class's status method
        mock_parent_status = {"gateway_dtm": None}
        with patch.object(HgiGateway, "status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = mock_parent_status

            hgi_gateway.latest_dtm = None

            # Call the status method
            result = await hgi_gateway.status()

            # Assert the result
            assert result == {**mock_parent_status, "gateway_dtm": None}
