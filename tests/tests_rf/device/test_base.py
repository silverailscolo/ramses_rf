#!/usr/bin/env python3
"""Unittests for the base device classes and HgiGateway.

This module combines tests for DeviceBase, HgiGateway, and BatteryState
which all reside in ramses_rf/device/base.py.
"""

from datetime import UTC, datetime as dt, timedelta as td
from unittest.mock import MagicMock

import pytest

from ramses_rf.const import GATEWAY_MESSAGE_TIMEOUT
from ramses_rf.device.base import BatteryState, DeviceBase, HgiGateway
from ramses_rf.gateway import Gateway
from ramses_tx import Address


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
        dev._last_msg_dtm = dt.now(UTC)
        assert dev.is_available

        # Expired heartbeat (Default 1 hour)
        expired_dtm = dt.now(UTC) - td(hours=1, seconds=1)
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
        msg.dtm = dt.now(UTC)

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
        mock_msg.dtm = dt.now(UTC)

        hgi_gateway._gwy._engine._this_msg = mock_msg
        assert await hgi_gateway.is_active()

    @pytest.mark.asyncio
    async def test_is_active_expired_msg(self, hgi_gateway: HgiGateway) -> None:
        """Test is_active returns False when the latest message is too old.

        :param hgi_gateway: The gateway fixture.
        :type hgi_gateway: HgiGateway
        """
        mock_msg = MagicMock()
        expired_dtm = dt.now(UTC) - (GATEWAY_MESSAGE_TIMEOUT + td(seconds=1))
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
        mock_msg.dtm = dt.now()

        hgi_gateway._gwy._engine._this_msg = mock_msg
        assert await hgi_gateway.is_active()

    def test_message_timeout_custom(self, hgi_gateway: HgiGateway) -> None:
        """Test that the custom gateway timeout is correctly extracted.

        :param hgi_gateway: The gateway fixture.
        :type hgi_gateway: HgiGateway
        """
        # Inject a custom timeout into the mocked gateway config
        hgi_gateway._gwy.config.gateway_timeout = 15

        assert hgi_gateway.message_timeout == td(minutes=15)

    @pytest.mark.asyncio
    async def test_is_active_custom_timeout(self, hgi_gateway: HgiGateway) -> None:
        """Test is_active evaluates correctly against a custom timeout.

        :param hgi_gateway: The gateway fixture.
        :type hgi_gateway: HgiGateway
        """
        # Set a custom timeout of 15 minutes
        hgi_gateway._gwy.config.gateway_timeout = 15

        mock_msg = MagicMock()
        # Create a timestamp 10 minutes in the past
        # Under the default 5-minute timeout, this would be inactive.
        # Under our custom 15-minute timeout, this must be active.
        mock_msg.dtm = dt.now(UTC) - td(minutes=10)

        hgi_gateway._gwy._engine._this_msg = mock_msg
        assert await hgi_gateway.is_active() is True
