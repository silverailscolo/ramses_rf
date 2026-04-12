#!/usr/bin/env python3
"""RAMSES RF - Unittests for dispatcher."""

import logging
from collections.abc import Generator
from datetime import datetime as dt, timedelta as td
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ramses_rf import Device, dispatcher
from ramses_rf.gateway import Gateway, GatewayConfig
from ramses_rf.message_store import MessageStore
from ramses_tx import Address, DeviceIdT, Message, Packet


@pytest.fixture
def mock_gateway() -> Generator[MagicMock, None, None]:
    """Create a mock Gateway instance for testing."""
    gateway = MagicMock(spec=Gateway)
    gateway.send_cmd = AsyncMock()

    # Use the strictly typed GatewayConfig DTO instead of loose mock attributes
    gateway.config = GatewayConfig(
        disable_discovery=False,
        enable_eavesdrop=False,
        reduce_processing=0,
    )

    # Mock the internal engine and its loop to reflect the new architecture
    gateway._engine = MagicMock()
    gateway._engine._loop = MagicMock()
    gateway._engine._loop.call_soon = MagicMock()
    gateway._engine._loop.call_later = MagicMock()
    gateway._engine._loop.time = MagicMock(return_value=0.0)

    # Support legacy proxy access (dispatcher.py currently still uses `gwy._loop`)
    gateway._loop = gateway._engine._loop

    # Correctly mock the device registry structure
    gateway.device_registry = MagicMock()
    gateway.device_registry.device_by_id = {}

    gateway._engine._include = {}

    # activate the SQLite MessageStore
    gateway.message_store = MessageStore(maintain=False)

    yield gateway


class Test_dispatcher_gateway:
    """Test Dispatcher class."""

    _SRC1 = "32:166025"
    _SRC2 = "01:087939"  # (CTR)
    _NONA = "--:------"
    _NOW = dt.now().replace(microsecond=0)

    msg5: Message = Message._from_pkt(
        Packet(
            _NOW + td(seconds=40),
            "...  I --- 04:189078 --:------ 01:145038 3150 002 0100",  # heat_demand
        )
    )

    msg6: Message = Message._from_pkt(
        Packet(
            _NOW + td(seconds=50),
            "061 RP --- 10:078099 01:087939 --:------ 3220 005 00C0110000",  # OTB
        )
    )

    @pytest.mark.skip(reason="requires gwy")
    def test_instantiate_devices(self, mock_gateway: MagicMock) -> None:
        """Test device creation from addresses via pipeline stage."""
        dev1 = Device(mock_gateway, Address(DeviceIdT("04:189078")))
        mock_gateway.device_registry.device_by_id.get = MagicMock(return_value=dev1)
        mock_gateway._check_dst_slug = MagicMock(return_value="CTL")

        dispatcher.instantiate_devices(mock_gateway, self.msg5)

        mock_gateway.message_store.stop()  # close sqlite3 connection

    def test_validate_addresses(self, mock_gateway: MagicMock) -> None:
        """Test address validation via pipeline stage."""
        dispatcher.validate_addresses(mock_gateway, self.msg5)
        dispatcher.validate_addresses(mock_gateway, self.msg6)

    def test_validate_slugs(self, mock_gateway: MagicMock) -> None:
        """Test destination slug validation via pipeline stage."""
        dispatcher.validate_slugs(mock_gateway, self.msg5)

    def test_detect_array_fragment(self) -> None:
        """Test detection of array fragments."""
        msg1: Message = Message._from_pkt(
            Packet(
                self._NOW,
                "...  I --- 01:158182 --:------ 01:158182 000A 048 001001F40BB8011101F40BB8021101F40BB8031001F40BB8041101F40BB8051101F40BB8061101F40BB8071001F40BB8",
            )
        )
        msg2: Message = Message._from_pkt(
            Packet(
                self._NOW + td(seconds=1),  # delta dtm < 3 secs
                "...  I --- 01:158182 --:------ 01:158182 000A 006 081001F409C4",
            )
        )
        msg3: Message = Message._from_pkt(
            Packet(
                self._NOW + td(seconds=10),  # delta dtm > 3 secs
                "...  I --- 01:158182 --:------ 01:158182 000A 006 081001F409C4",
            )
        )
        assert msg1._has_array
        assert dispatcher.detect_array_fragment(msg2, msg1)
        assert not dispatcher.detect_array_fragment(msg3, msg1)


class TestDispatcherErrorHandling:
    """Test Dispatcher exception handling logic."""

    async def test_process_msg_strict_mode(self, mock_gateway: MagicMock) -> None:
        """Test process_msg raises exception in strict mode."""
        # Enable strict mode
        mock_gateway.config.enforce_strict_handling = True

        # Create a message with a valid payload for code 0001
        msg = Message._from_pkt(
            Packet(
                dt.now(),
                "...  I --- 01:000001 --:------ 01:000001 0001 005 00FFFF0200",
            )
        )

        # Force a ValueError within process_msg by mocking the first pipeline stage
        with (
            patch(
                "ramses_rf.dispatcher.validate_addresses",
                side_effect=ValueError("Test Error"),
            ),
            pytest.raises(ValueError, match="Test Error"),
        ):
            await dispatcher.process_msg(mock_gateway, msg)

    async def test_process_msg_safe_mode(
        self, mock_gateway: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test process_msg logs warning with trace in safe mode."""
        # Disable strict mode (safe mode)
        mock_gateway.config.enforce_strict_handling = False

        msg = Message._from_pkt(
            Packet(
                dt.now(),
                "...  I --- 01:000001 --:------ 01:000001 0001 005 00FFFF0200",
            )
        )

        # Force a ValueError within process_msg by mocking the first pipeline stage
        with (
            patch(
                "ramses_rf.dispatcher.validate_addresses",
                side_effect=ValueError("Test Error"),
            ),
            caplog.at_level(logging.WARNING),
        ):
            await dispatcher.process_msg(mock_gateway, msg)

        # Assert exception was caught and logged
        assert "Test Error" in caplog.text
        # Check that it was logged as a WARNING
        assert any(r.levelname == "WARNING" for r in caplog.records)
        # Check that traceback information is present (exc_info=True)
        assert any(r.exc_info is not None for r in caplog.records)


class TestDispatcherHeartbeats:
    """Test that heartbeat (empty) payloads are correctly dispatched to devices."""

    @pytest.mark.parametrize(
        ("pkt_line", "src_id", "dev_type"),
        [
            # TRV sending a 3150 heat demand heartbeat (1-byte "00" payload, I verb)
            (
                "045  I --- 04:123456 --:------ 04:123456 3150 001 00",
                "04:123456",
                "TRV",
            ),
            # FAN sending a 2411 fan parameters heartbeat (1-byte "00" payload, RP verb)
            (
                "045 RP --- 32:155617 29:123160 --:------ 2411 001 00",
                "32:155617",
                "FAN",
            ),
            # TRV sending a 12B0 window state heartbeat (1-byte "00" payload, I verb)
            (
                "045  I --- 04:123456 --:------ 04:123456 12B0 001 00",
                "04:123456",
                "TRV",
            ),
            # TRV sending an empty 2309 setpoint heartbeat (1-byte "00" payload, I verb)
            (
                "045  I --- 04:123456 --:------ 04:123456 2309 001 00",
                "04:123456",
                "TRV",
            ),
        ],
    )
    async def test_heartbeat_dispatch(
        self,
        mock_gateway: MagicMock,
        pkt_line: str,
        src_id: str,
        dev_type: str,
    ) -> None:
        """Test that empty payload heartbeats are routed to update device timestamps."""
        # 1. Parse the packet into a Message
        # This confirms that message.py correctly validates and bypasses empty heartbeats
        dtm = dt.now()
        packet = Packet(dtm, pkt_line)
        msg = Message(packet)

        # Confirm it safely processed as an empty heartbeat message
        assert msg._has_payload is False
        assert msg.payload == {}

        # 2. Setup the mock registry and device
        # We mock a device matching the source ID and set its slug to pass validation
        mock_dev = MagicMock(spec=Device)
        mock_dev.id = src_id
        mock_dev._SLUG = dev_type
        mock_dev._is_binding = False
        mock_dev.is_faked = False

        # Inject the mock device into the registry so instantiate_devices maps to it
        mock_gateway.device_registry.device_by_id[src_id] = mock_dev
        mock_gateway.device_registry.get_device.return_value = mock_dev

        # Give the mocked HGI a different ID so the packet is treated as remote
        mock_gateway.hgi.id = "18:000730"

        # 3. Process the message through the dispatcher
        await dispatcher.process_msg(mock_gateway, msg)

        # 4. Assert the message was explicitly dispatched to the device
        # The dispatcher queues the update via gwy._engine._loop.call_soon()
        # which triggers mock_dev._handle_msg(msg) containing the timestamp updates
        mock_gateway._engine._loop.call_soon.assert_any_call(mock_dev._handle_msg, msg)
