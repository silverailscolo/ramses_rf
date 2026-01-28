#!/usr/bin/env python3
"""Test the injection of a custom HGI Device ID into the Gateway."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ramses_rf import Gateway
from ramses_tx.address import HGI_DEV_ADDR
from ramses_tx.const import SZ_ACTIVE_HGI

TEST_HGI_ID = "18:005960"


@pytest.mark.asyncio
async def test_hgi_id_injection() -> None:
    """Check that the custom HGI ID is passed correctly to the Engine/Transport."""

    # Mock the transport factory to avoid creating a real connection/transport
    # We want to inspect the kwargs passed to it.
    with patch("ramses_tx.gateway.transport_factory") as mock_transport_factory:
        # Setup the mock transport to be returned by the factory
        mock_transport = MagicMock()
        mock_transport.get_extra_info.return_value = TEST_HGI_ID

        # Configure the factory mock to return our transport mock (as an async result)
        mock_transport_factory.return_value = mock_transport

        # 1. Instantiate Gateway with the custom hgi_id
        # We must provide a dummy port_name to satisfy Engine.__init__ validation
        gwy = Gateway("/dev/ttyMOCK", input_file=None, hgi_id=TEST_HGI_ID)

        # 2. Check that the Engine (Gateway base class) has stored the ID
        assert gwy._hgi_id == TEST_HGI_ID

        # 3. Check the string representation reflects the custom ID
        # Note: Before start(), it uses the stored _hgi_id
        assert str(gwy).startswith(TEST_HGI_ID)

        # 4. Start the gateway to trigger the transport factory call
        # We patch the protocol's wait method to bypass the handshake timeout
        with patch.object(
            gwy._protocol, "wait_for_connection_made", new_callable=AsyncMock
        ):
            await gwy.start()

        # 5. Verify transport_factory was called with the correct kwarg
        _, kwargs = mock_transport_factory.call_args

        assert SZ_ACTIVE_HGI in kwargs
        assert kwargs[SZ_ACTIVE_HGI] == TEST_HGI_ID

        # Cleanup
        await gwy.stop()


@pytest.mark.asyncio
async def test_hgi_id_default_behavior() -> None:
    """Check that the Gateway defaults to the hardcoded ID when no custom ID is provided."""

    with patch("ramses_tx.gateway.transport_factory") as mock_transport_factory:
        # Setup the mock transport
        mock_transport = MagicMock()
        # Default behavior: if get_extra_info is called for HGI, it might return None or default
        mock_transport.get_extra_info.return_value = HGI_DEV_ADDR.id

        mock_transport_factory.return_value = mock_transport

        # 1. Instantiate Gateway WITHOUT the custom hgi_id
        gwy = Gateway("/dev/ttyMOCK", input_file=None)

        # 2. Check that the Engine has NO stored custom ID
        assert gwy._hgi_id is None

        # 3. Check the string representation falls back to the default constant
        assert str(gwy).startswith(HGI_DEV_ADDR.id)

        # 4. Start the gateway
        # We patch the protocol's wait method to bypass the handshake timeout
        with patch.object(
            gwy._protocol, "wait_for_connection_made", new_callable=AsyncMock
        ):
            await gwy.start()

        # 5. Verify transport_factory was called WITHOUT the active_gwy override
        _, kwargs = mock_transport_factory.call_args

        # The key should NOT be present if we didn't inject it
        assert SZ_ACTIVE_HGI not in kwargs

        # Cleanup
        await gwy.stop()
