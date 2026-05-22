"""Phase 2.95 State Ingestion Worker Pure Unit Tests.

This suite tests the StateIngestionWorker in absolute isolation from the
monolithic Gateway or live file streaming, verifying the hexagonal data
conversion logic using pure mock entities.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from ramses_rf.const import Code, DevType
from ramses_rf.messages import Message
from ramses_rf.models import HvacState, OpenThermState, StateUpdatedEvent
from ramses_rf.pipeline.ingestion import StateIngestionWorker
from ramses_rf.protocol.opentherm import OtDataId


class MockAddr:
    """Mock hardware address descriptor."""

    def __init__(self, device_id: str) -> None:
        """Initialize the mock address container.

        :param device_id: The target hardware ID string.
        :type device_id: str
        """
        self.id: str = device_id


class MockMessage:
    """Mock message container simulating a fully parsed L7 telemetry packet."""

    def __init__(
        self, code: Code, verb: str, payload: dict[str, Any], src_id: str
    ) -> None:
        """Initialize the mock message wrapper envelope.

        :param code: The packet command code signature.
        :type code: Code
        :param verb: The transmission verb signature.
        :type verb: str
        :param payload: The raw decoded dictionary.
        :type payload: dict[str, Any]
        :param src_id: The source hardware ID string.
        :type src_id: str
        """
        self.code: Code = code
        self.verb: str = verb
        self.payload: dict[str, Any] = payload
        self.src: MockAddr = MockAddr(src_id)
        self.correlation_id: uuid.UUID = uuid.uuid4()
        self.message_id: uuid.UUID = uuid.uuid4()


class FakeDevice:
    """A minimal fake device twin to act as an outbound target port."""

    def __init__(self) -> None:
        """Initialize the fake device with base state models."""
        self.id: str = "10:064873"
        self._SLUG: str = DevType.OTB
        self.opentherm_state: OpenThermState = OpenThermState()
        self.hvac_state: HvacState = HvacState()
        self.events: list[StateUpdatedEvent] = []

    def apply_state_update(self, event: StateUpdatedEvent) -> None:
        """Accept an immutable state event and apply it to the read-model.

        :param event: The state update event container.
        :type event: StateUpdatedEvent
        :return: None
        :rtype: None
        """
        self.events.append(event)
        if isinstance(event.state, OpenThermState):
            self.opentherm_state = event.state
        elif isinstance(event.state, HvacState):
            self.hvac_state = event.state


class FakeRegistry:
    """A minimal fake registry port to handle logical target lookups."""

    def __init__(self, device: FakeDevice) -> None:
        """Initialize the registry with a tracking device map.

        :param device: The fake device to store.
        :type device: FakeDevice
        """
        self.device_by_id: dict[str, FakeDevice] = {device.id: device}


class FakeGatewayAdapter:
    """A mock gateway boundary adapter wrapping our device registry port."""

    def __init__(self, registry: FakeRegistry) -> None:
        """Initialize the gateway adapter port wrapper.

        :param registry: The fake registry instance to wrap.
        :type registry: FakeRegistry
        """
        self.device_registry: FakeRegistry = registry


def test_worker_opentherm_modulation_parsing() -> None:
    """Verify that the worker translates modulation messages into OpenThermStates.

    :return: None
    :rtype: None
    """
    # 1. Arrange: Instantiate pure isolated test actors and adapters
    device = FakeDevice()
    registry = FakeRegistry(device)
    gwy_adapter = FakeGatewayAdapter(registry)
    queue: asyncio.Queue[Message] = asyncio.Queue()

    worker = StateIngestionWorker(gwy_adapter, queue)

    # 2. Construct an isolated mock Message envelope for modulation
    mock_msg = MockMessage(
        code=Code._3220,
        verb="RP",
        payload={"msg_id": int(OtDataId.REL_MODULATION_LEVEL), "value": 42.5},
        src_id=device.id,
    )

    # 3. Act: Trigger the state conversion extraction logic directly
    worker._update_opentherm_state(device, mock_msg.payload, mock_msg)

    # 4. Assert: Verify the target read-model box updated safely
    assert device.opentherm_state.rel_modulation_level == 42.5
    assert len(device.events) == 1
    assert device.events[0].entity_id == device.id


def test_worker_opentherm_status_flag_parsing() -> None:
    """Verify that the worker translates status arrays into flag booleans.

    :return: None
    :rtype: None
    """
    device = FakeDevice()
    registry = FakeRegistry(device)
    gwy_adapter = FakeGatewayAdapter(registry)
    queue: asyncio.Queue[Message] = asyncio.Queue()

    worker = StateIngestionWorker(gwy_adapter, queue)

    # Construct an array payload matching standard OpenTherm status flags
    # index 9 is ch_active, index 11 is flame_active
    status_array = [0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0]
    mock_msg = MockMessage(
        code=Code._3220,
        verb="RP",
        payload={"msg_id": int(OtDataId.STATUS), "value": status_array},
        src_id=device.id,
    )

    worker._update_opentherm_state(device, mock_msg.payload, mock_msg)

    assert device.opentherm_state.ch_active is True
    assert device.opentherm_state.flame_active is True
    assert device.opentherm_state.ch_enabled is False


def test_worker_hvac_state_parsing() -> None:
    """Verify that the worker extracts multi-property HVAC data into HvacState.

    :return: None
    :rtype: None
    """
    device = FakeDevice()
    # Spoof an HVAC device identity
    device.id = "32:123456"
    device._SLUG = DevType.HVC

    registry = FakeRegistry(device)
    gwy_adapter = FakeGatewayAdapter(registry)
    queue: asyncio.Queue[Message] = asyncio.Queue()

    worker = StateIngestionWorker(gwy_adapter, queue)

    # Construct a spoofed HVAC packet payload (e.g., Code._31D9 or Code._22F1)
    hvac_payload = {
        "co2_level": 850,
        "indoor_humidity": 45.2,
        "fan_mode": "auto",
        "presence_detected": True,
        "remaining_days": 120,
    }

    mock_msg = MockMessage(
        code=Code._31D9,
        verb="I",
        payload=hvac_payload,
        src_id=device.id,
    )

    worker._update_hvac_state(device, mock_msg.payload, mock_msg)

    # Assert that the extracted payload safely mapped onto the frozen HvacState dataclass
    assert device.hvac_state.co2_level == 850
    assert device.hvac_state.indoor_humidity == 45.2
    assert device.hvac_state.fan_mode == "auto"
    assert device.hvac_state.presence_detected is True
    assert device.hvac_state.filter_remaining_days == 120

    # Assert the event lineage was preserved
    assert len(device.events) == 1
    assert isinstance(device.events[0].state, HvacState)
