"""Pure unit tests for the StateProjector worker in the pipeline.

This suite tests the StateProjector in absolute isolation from the Gateway
or live file streaming, verifying the hexagonal data conversion logic
using pure mock entities.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from ramses_rf.const import (
    SZ_MODULATION_LEVEL,
    SZ_REL_MODULATION_LEVEL,
    SZ_REMAINING_DAYS,
    SZ_SETPOINT,
    Code,
    DevType,
    Verb,
)
from ramses_rf.messages import Message
from ramses_rf.models import (
    ActuatorState,
    HvacState,
    OpenThermState,
    StateUpdatedEvent,
)
from ramses_rf.pipeline.ingestion import StateProjector
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
        self,
        code: Code,
        verb: str,
        payload: dict[str, Any],
        src_id: str,
        dst_id: str = "--:------",
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
        :param dst_id: The destination hardware ID string.
        :type dst_id: str
        """
        self.code: Code = code
        self.verb: str = verb
        self.payload: dict[str, Any] = payload
        self.src: MockAddr = MockAddr(src_id)
        self.dst: MockAddr = MockAddr(dst_id)
        self.correlation_id: uuid.UUID = uuid.uuid4()
        self.message_id: uuid.UUID = uuid.uuid4()


class FakeDevice:
    """A minimal fake device twin to act as an outbound target port."""

    def __init__(self) -> None:
        """Initialize the fake device with base state models."""
        self.id: str = "10:064873"
        self._SLUG: str = DevType.OTB
        self.opentherm_state: OpenThermState = OpenThermState()
        self.act_state: ActuatorState = ActuatorState()
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
        elif isinstance(event.state, ActuatorState):
            self.act_state = event.state
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
        self.systems: list[Any] = []


class FakeGatewayAdapter:
    """A mock gateway boundary adapter wrapping our device registry port."""

    def __init__(self, registry: FakeRegistry) -> None:
        """Initialize the gateway adapter port wrapper.

        :param registry: The fake registry instance to wrap.
        :type registry: FakeRegistry
        """
        self.device_registry: FakeRegistry = registry


def test_worker_opentherm_modulation_parsing() -> None:
    """Verify that the worker translates modulation messages into OpenThermStates."""
    # Arrange
    device = FakeDevice()
    registry = FakeRegistry(device)
    gwy_adapter = FakeGatewayAdapter(registry)
    queue: asyncio.Queue[Message] = asyncio.Queue()

    worker = StateProjector(gwy_adapter, queue)

    mock_msg = MockMessage(
        code=Code._3220,
        verb=Verb.RP,
        payload={"msg_id": int(OtDataId.REL_MODULATION_LEVEL), "value": 42.5},
        src_id=device.id,
    )

    # Act
    worker._update_opentherm_state(device, mock_msg.payload, mock_msg)

    # Assert
    assert device.opentherm_state.rel_modulation_level == 42.5
    assert len(device.events) == 1
    assert device.events[0].entity_id == device.id


def test_worker_opentherm_status_flag_parsing() -> None:
    """Verify that the worker translates status arrays into flag booleans."""
    # Arrange
    device = FakeDevice()
    registry = FakeRegistry(device)
    gwy_adapter = FakeGatewayAdapter(registry)
    queue: asyncio.Queue[Message] = asyncio.Queue()

    worker = StateProjector(gwy_adapter, queue)

    status_array = [0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0]
    mock_msg = MockMessage(
        code=Code._3220,
        verb=Verb.RP,
        payload={"msg_id": int(OtDataId.STATUS), "value": status_array},
        src_id=device.id,
    )

    # Act
    worker._update_opentherm_state(device, mock_msg.payload, mock_msg)

    # Assert
    assert device.opentherm_state.flags.ch_active is True
    assert device.opentherm_state.flags.flame_active is True
    assert device.opentherm_state.flags.ch_enabled is False


def test_worker_hvac_state_parsing() -> None:
    """Verify that the worker extracts multi-property HVAC data into HvacState."""
    # Arrange
    device = FakeDevice()
    device.id = "32:123456"
    device._SLUG = DevType.HVC

    registry = FakeRegistry(device)
    gwy_adapter = FakeGatewayAdapter(registry)
    queue: asyncio.Queue[Message] = asyncio.Queue()

    worker = StateProjector(gwy_adapter, queue)

    hvac_payload = {
        "co2_level": 850,
        "indoor_humidity": 45.2,
        "fan_mode": "auto",
        "presence_detected": True,
        SZ_REMAINING_DAYS: 120,
    }

    mock_msg = MockMessage(
        code=Code._31D9,
        verb="I",
        payload=hvac_payload,
        src_id=device.id,
    )

    # Act
    worker._update_hvac_state(device, mock_msg.payload, mock_msg)

    # Assert
    assert device.hvac_state.co2_level == 850
    assert device.hvac_state.indoor_humidity == 45.2
    assert device.hvac_state.fan_mode == "auto"
    assert device.hvac_state.presence_detected is True
    assert device.hvac_state.filter_remaining_days == 120

    assert len(device.events) == 1
    assert isinstance(device.events[0].state, HvacState)


def test_worker_opentherm_modulation_keys_parity() -> None:
    # Arrange
    device = FakeDevice()
    registry = FakeRegistry(device)
    gwy_adapter = FakeGatewayAdapter(registry)
    queue: asyncio.Queue[Message] = asyncio.Queue()
    worker = StateProjector(gwy_adapter, queue)

    msg_mod_level = MockMessage(
        code=Code._3EF0,
        verb=Verb.I_,
        payload={SZ_MODULATION_LEVEL: 0.65},
        src_id=device.id,
    )
    msg_rel_mod_level = MockMessage(
        code=Code._3EF0,
        verb=Verb.I_,
        payload={SZ_REL_MODULATION_LEVEL: 0.85},
        src_id=device.id,
    )

    # Act
    worker._update_opentherm_state(
        device, msg_mod_level.payload, msg_mod_level
    )

    # Assert
    assert device.opentherm_state.rel_modulation_level == 0.65

    # Act
    worker._update_opentherm_state(
        device, msg_rel_mod_level.payload, msg_rel_mod_level
    )

    # Assert
    assert device.opentherm_state.rel_modulation_level == 0.85


def test_state_projector_routes_controller_22d9_to_appliance_control() -> None:
    # Arrange
    ctl_dev = FakeDevice()
    ctl_dev.id = "01:054173"
    ctl_dev._SLUG = DevType.CTL

    otb_dev = FakeDevice()
    otb_dev.id = "10:048122"
    otb_dev._SLUG = DevType.OTB

    class FakeTcs:
        id = "01:054173"
        appliance_control = otb_dev
        zone_by_index: dict[str, Any] = {}

    mock_tcs = FakeTcs()
    registry = FakeRegistry(ctl_dev)
    registry.device_by_id[otb_dev.id] = otb_dev
    registry.systems = [mock_tcs]

    gwy_adapter = FakeGatewayAdapter(registry)
    queue: asyncio.Queue[Message] = asyncio.Queue()
    worker = StateProjector(gwy_adapter, queue)

    # Act: Controller broadcasts 22D9 (Boiler Setpoint 48.5C) to --:------
    broadcast_msg = MockMessage(
        code=Code._22D9,
        verb=Verb.I_,
        payload={SZ_SETPOINT: 48.5},
        src_id="01:054173",
        dst_id="--:------",
    )
    worker.process_message_state(broadcast_msg)

    # Assert
    assert otb_dev.opentherm_state.temperatures.boiler_setpoint == 48.5


def test_state_projector_routes_controller_3ef0_to_appliance_control() -> None:
    # Arrange
    ctl_dev = FakeDevice()
    ctl_dev.id = "01:054173"
    ctl_dev._SLUG = DevType.CTL

    otb_dev = FakeDevice()
    otb_dev.id = "10:048122"
    otb_dev._SLUG = DevType.OTB

    class FakeTcs:
        id = "01:054173"
        appliance_control = otb_dev
        zone_by_index: dict[str, Any] = {}

    mock_tcs = FakeTcs()
    registry = FakeRegistry(ctl_dev)
    registry.device_by_id[otb_dev.id] = otb_dev
    registry.systems = [mock_tcs]

    gwy_adapter = FakeGatewayAdapter(registry)
    queue: asyncio.Queue[Message] = asyncio.Queue()
    worker = StateProjector(gwy_adapter, queue)

    # Act: Controller broadcasts 3EF0 (Modulation 55% + CH active) to --:------
    broadcast_msg = MockMessage(
        code=Code._3EF0,
        verb=Verb.I_,
        payload={
            SZ_MODULATION_LEVEL: 0.55,
            "ch_active": True,
            "ch_enabled": True,
        },
        src_id="01:054173",
        dst_id="--:------",
    )
    worker.process_message_state(broadcast_msg)

    # Assert
    assert otb_dev.opentherm_state.rel_modulation_level == 0.55
    assert otb_dev.opentherm_state.flags.ch_active is True
    assert otb_dev.opentherm_state.flags.ch_enabled is True
    assert otb_dev.act_state.modulation_level == 0.55


def test_state_projector_routes_opentherm_3220_data_id_responses() -> None:
    # Arrange
    device = FakeDevice()
    registry = FakeRegistry(device)
    gwy_adapter = FakeGatewayAdapter(registry)
    queue: asyncio.Queue[Message] = asyncio.Queue()
    worker = StateProjector(gwy_adapter, queue)

    # Act: Ingest Boiler Output Temp (0x19), Return Temp (0x1C), DHW Setpoint (0x38), CH Max Setpoint (0x39)
    msg_flow_temp = MockMessage(
        code=Code._3220,
        verb=Verb.RP,
        payload={"msg_id": int(OtDataId.BOILER_OUTPUT_TEMP), "value": 58.5},
        src_id=device.id,
    )
    msg_return_temp = MockMessage(
        code=Code._3220,
        verb=Verb.RP,
        payload={"msg_id": int(OtDataId.BOILER_RETURN_TEMP), "value": 41.2},
        src_id=device.id,
    )
    msg_dhw_setpoint = MockMessage(
        code=Code._3220,
        verb=Verb.RP,
        payload={"msg_id": int(OtDataId.DHW_SETPOINT), "value": 52.0},
        src_id=device.id,
    )
    msg_ch_max_setpoint = MockMessage(
        code=Code._3220,
        verb=Verb.RP,
        payload={"msg_id": int(OtDataId.CH_MAX_SETPOINT), "value": 75.0},
        src_id=device.id,
    )

    worker.process_message_state(msg_flow_temp)
    worker.process_message_state(msg_return_temp)
    worker.process_message_state(msg_dhw_setpoint)
    worker.process_message_state(msg_ch_max_setpoint)

    # Assert
    assert device.opentherm_state.temperatures.boiler_output == 58.5
    assert device.opentherm_state.temperatures.boiler_return == 41.2
    assert device.opentherm_state.temperatures.dhw_setpoint == 52.0
    assert device.opentherm_state.temperatures.ch_max_setpoint == 75.0
