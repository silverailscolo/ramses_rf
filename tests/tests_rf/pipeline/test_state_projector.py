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
    SZ_COOLING_DEMAND,
    SZ_DOMAIN_INDEX,
    SZ_MODULATION_LEVEL,
    SZ_REL_MODULATION_LEVEL,
    SZ_REMAINING_DAYS,
    SZ_SETPOINT,
    SZ_ZONE_INDEX,
    Code,
    DevType,
    Verb,
)
from ramses_rf.messages import Message
from ramses_rf.models import (
    ActuatorState,
    DhwState,
    HvacState,
    OpenThermState,
    StateUpdatedEvent,
    SystemState,
    TemperatureState,
    ZoneState,
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
        self.tcs: Any | None = None
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


class FakeZone:
    """A minimal fake zone entity to act as a state target."""

    def __init__(self, zone_id: str, setpoint: float = 5.0) -> None:
        """Initialize the fake zone with default state models.

        :param zone_id: The unique zone ID string.
        :type zone_id: str
        :param setpoint: Initial setpoint in degrees Celsius.
        :type setpoint: float
        """
        self.id: str = zone_id
        self.temp_state: TemperatureState = TemperatureState(setpoint=setpoint)
        self.zone_state: ZoneState = ZoneState(setpoint=setpoint)
        self.events: list[StateUpdatedEvent] = []

    def apply_state_update(self, event: StateUpdatedEvent) -> None:
        """Accept an immutable state update event for the zone.

        :param event: The state update event container.
        :type event: StateUpdatedEvent
        """
        self.events.append(event)
        if isinstance(event.state, TemperatureState):
            self.temp_state = event.state
        elif isinstance(event.state, ZoneState):
            self.zone_state = event.state


class FakeDhw:
    """A minimal fake DHW entity to act as a state target."""

    def __init__(self, dhw_id: str, setpoint: float = 50.0) -> None:
        """Initialize the fake DHW entity with default state models.

        :param dhw_id: The unique DHW ID string.
        :type dhw_id: str
        :param setpoint: Initial DHW setpoint in degrees Celsius.
        :type setpoint: float
        """
        self.id: str = dhw_id
        self.temp_state: TemperatureState = TemperatureState()
        self.dhw_state: DhwState = DhwState(setpoint=setpoint)
        self.events: list[StateUpdatedEvent] = []

    def apply_state_update(self, event: StateUpdatedEvent) -> None:
        """Accept an immutable state update event for DHW.

        :param event: The state update event container.
        :type event: StateUpdatedEvent
        """
        self.events.append(event)
        if isinstance(event.state, TemperatureState):
            self.temp_state = event.state
        elif isinstance(event.state, DhwState):
            self.dhw_state = event.state


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


def test_state_projector_routes_controller_2d49_to_tcs() -> None:
    # Arrange
    ctl_dev = FakeDevice()
    ctl_dev.id = "01:054173"
    ctl_dev._SLUG = DevType.CTL

    class FakeTcs:
        id = "01:054173"
        zone_by_index: dict[str, Any] = {}
        system_state: SystemState = SystemState()

    mock_tcs = FakeTcs()
    ctl_dev.tcs = mock_tcs
    registry = FakeRegistry(ctl_dev)
    registry.systems = [mock_tcs]

    gwy_adapter = FakeGatewayAdapter(registry)
    queue: asyncio.Queue[Message] = asyncio.Queue()
    worker = StateProjector(gwy_adapter, queue)

    # Act: Controller broadcasts 2D49 (Cooling Active)
    broadcast_msg = MockMessage(
        code=Code._2D49,
        verb=Verb.I_,
        payload={SZ_ZONE_INDEX: "00", SZ_COOLING_DEMAND: True},
        src_id="01:054173",
        dst_id="--:------",
    )
    worker.process_message_state(broadcast_msg)

    # Assert
    assert mock_tcs.system_state.cooling_mode is True


def test_state_projector_routes_ufc_2d49_to_tcs() -> None:
    # Arrange
    ufc_dev = FakeDevice()
    ufc_dev.id = "02:123456"
    ufc_dev._SLUG = DevType.UFC

    class FakeTcs:
        id = "01:054173"
        zone_by_index: dict[str, Any] = {}
        system_state: SystemState = SystemState()

    mock_tcs = FakeTcs()
    ufc_dev.tcs = mock_tcs
    registry = FakeRegistry(ufc_dev)
    registry.systems = [mock_tcs]

    gwy_adapter = FakeGatewayAdapter(registry)
    queue: asyncio.Queue[Message] = asyncio.Queue()
    worker = StateProjector(gwy_adapter, queue)

    # Act: UFC broadcasts 2D49 (Cooling Active)
    broadcast_msg = MockMessage(
        code=Code._2D49,
        verb=Verb.I_,
        payload={SZ_ZONE_INDEX: "01", SZ_COOLING_DEMAND: True},
        src_id="02:123456",
        dst_id="--:------",
    )
    worker.process_message_state(broadcast_msg)

    # Assert
    assert mock_tcs.system_state.cooling_mode is True


def test_state_projector_routes_2d49_inactive_cooling_to_tcs() -> None:
    # Arrange
    ctl_dev = FakeDevice()
    ctl_dev.id = "01:054173"
    ctl_dev._SLUG = DevType.CTL

    class FakeTcs:
        id = "01:054173"
        zone_by_index: dict[str, Any] = {}
        system_state: SystemState = SystemState()

    mock_tcs = FakeTcs()
    ctl_dev.tcs = mock_tcs
    registry = FakeRegistry(ctl_dev)
    registry.systems = [mock_tcs]

    gwy_adapter = FakeGatewayAdapter(registry)
    queue: asyncio.Queue[Message] = asyncio.Queue()
    worker = StateProjector(gwy_adapter, queue)

    # Act: Controller broadcasts 2D49 (Cooling Inactive)
    broadcast_msg = MockMessage(
        code=Code._2D49,
        verb=Verb.I_,
        payload={SZ_ZONE_INDEX: "00", SZ_COOLING_DEMAND: False},
        src_id="01:054173",
        dst_id="--:------",
    )
    worker.process_message_state(broadcast_msg)

    # Assert
    assert mock_tcs.system_state.cooling_mode is False


def test_22d9_boiler_setpoint_does_not_mutate_zone_00_setpoint() -> None:
    # Arrange
    ctl_dev = FakeDevice()
    ctl_dev.id = "01:216136"
    ctl_dev._SLUG = DevType.CTL

    otb_dev = FakeDevice()
    otb_dev.id = "10:064873"
    otb_dev._SLUG = DevType.OTB

    zone_00 = FakeZone("01:216136_00", setpoint=5.0)
    zone_01 = FakeZone("01:216136_01", setpoint=20.0)
    dhw = FakeDhw("01:216136_HW", setpoint=50.0)

    class FakeTcs:
        def __init__(self) -> None:
            self.id = "01:216136"
            self.appliance_control = otb_dev
            self.dhw = dhw
            self.zone_by_index = {"00": zone_00, "01": zone_01}

    mock_tcs = FakeTcs()
    registry = FakeRegistry(ctl_dev)
    registry.device_by_id[otb_dev.id] = otb_dev
    registry.systems = [mock_tcs]

    gwy_adapter = FakeGatewayAdapter(registry)
    queue: asyncio.Queue[Message] = asyncio.Queue()
    worker = StateProjector(gwy_adapter, queue)

    # Act 1: Controller broadcasts 22D9 (Boiler Setpoint 10.0C, idle)
    msg_22d9_idle = MockMessage(
        code=Code._22D9,
        verb=Verb.I_,
        payload={SZ_DOMAIN_INDEX: "00", SZ_SETPOINT: 10.0},
        src_id="01:216136",
        dst_id="--:------",
    )
    worker.process_message_state(msg_22d9_idle)

    # Assert 1: OTB receives boiler setpoint; Zone 00 remains 5.0C
    assert otb_dev.opentherm_state.temperatures.boiler_setpoint == 10.0
    assert zone_00.temp_state.setpoint == 5.0
    assert zone_01.temp_state.setpoint == 20.0
    assert dhw.dhw_state.setpoint == 50.0

    # Act 2: Controller broadcasts 22D9 (Boiler Setpoint 60.0C, burn)
    msg_22d9_burn = MockMessage(
        code=Code._22D9,
        verb=Verb.I_,
        payload={SZ_DOMAIN_INDEX: "00", SZ_SETPOINT: 60.0},
        src_id="01:216136",
        dst_id="--:------",
    )
    worker.process_message_state(msg_22d9_burn)

    # Assert 2: OTB receives boiler setpoint 60.0C; Zone 00 remains 5.0C
    assert otb_dev.opentherm_state.temperatures.boiler_setpoint == 60.0
    assert zone_00.temp_state.setpoint == 5.0
    assert zone_01.temp_state.setpoint == 20.0


def test_2309_and_2349_correctly_update_zones_and_do_not_mutate_appliance_control() -> (
    None
):
    # Arrange
    ctl_dev = FakeDevice()
    ctl_dev.id = "01:216136"
    ctl_dev._SLUG = DevType.CTL

    otb_dev = FakeDevice()
    otb_dev.id = "10:064873"
    otb_dev._SLUG = DevType.OTB

    zone_00 = FakeZone("01:216136_00", setpoint=5.0)
    zone_01 = FakeZone("01:216136_01", setpoint=20.0)

    class FakeTcs:
        id = "01:216136"
        appliance_control = otb_dev
        zone_by_index = {"00": zone_00, "01": zone_01}

    mock_tcs = FakeTcs()
    registry = FakeRegistry(ctl_dev)
    registry.device_by_id[otb_dev.id] = otb_dev
    registry.systems = [mock_tcs]

    gwy_adapter = FakeGatewayAdapter(registry)
    queue: asyncio.Queue[Message] = asyncio.Queue()
    worker = StateProjector(gwy_adapter, queue)

    # Initial boiler setpoint
    msg_22d9 = MockMessage(
        code=Code._22D9,
        verb=Verb.I_,
        payload={SZ_DOMAIN_INDEX: "00", SZ_SETPOINT: 60.0},
        src_id="01:216136",
        dst_id="--:------",
    )
    worker.process_message_state(msg_22d9)
    assert otb_dev.opentherm_state.temperatures.boiler_setpoint == 60.0

    # Act 1: Ingest 2309 for Zone 00 (target 18.0C)
    msg_2309_z00 = MockMessage(
        code=Code._2309,
        verb=Verb.I_,
        payload={SZ_ZONE_INDEX: "00", SZ_SETPOINT: 18.0},
        src_id="01:216136",
        dst_id="--:------",
    )
    worker.process_message_state(msg_2309_z00)

    # Assert 1: Zone 00 updates to 18.0C, OTB boiler setpoint unchanged
    assert zone_00.temp_state.setpoint == 18.0
    assert otb_dev.opentherm_state.temperatures.boiler_setpoint == 60.0

    # Act 2: Ingest 2349 for Zone 01 (target 21.5C)
    msg_2349_z01 = MockMessage(
        code=Code._2349,
        verb=Verb.I_,
        payload={SZ_ZONE_INDEX: "01", SZ_SETPOINT: 21.5},
        src_id="01:216136",
        dst_id="--:------",
    )
    worker.process_message_state(msg_2349_z01)

    # Assert 2: Zone 01 updates to 21.5C, Zone 00 remains 18.0C
    assert zone_01.temp_state.setpoint == 21.5
    assert zone_00.temp_state.setpoint == 18.0
    assert otb_dev.opentherm_state.temperatures.boiler_setpoint == 60.0


def test_issue_989_interleaved_packet_sequence_no_zone_00_oscillation() -> (
    None
):
    # Arrange: System with Zone 00 ("Garden room") and OTB appliance control
    ctl_dev = FakeDevice()
    ctl_dev.id = "01:216136"
    ctl_dev._SLUG = DevType.CTL

    otb_dev = FakeDevice()
    otb_dev.id = "10:064873"
    otb_dev._SLUG = DevType.OTB

    zone_00 = FakeZone("01:216136_00", setpoint=5.0)

    class FakeTcs:
        id = "01:216136"
        appliance_control = otb_dev
        zone_by_index = {"00": zone_00}

    mock_tcs = FakeTcs()
    registry = FakeRegistry(ctl_dev)
    registry.device_by_id[otb_dev.id] = otb_dev
    registry.systems = [mock_tcs]

    gwy_adapter = FakeGatewayAdapter(registry)
    queue: asyncio.Queue[Message] = asyncio.Queue()
    worker = StateProjector(gwy_adapter, queue)

    # Act: Replay exact interleaved sequence from issue #989
    interleaved_msgs = [
        # 1. 22D9 Boiler setpoint 10.0C (idle)
        MockMessage(
            code=Code._22D9,
            verb=Verb.I_,
            payload={SZ_DOMAIN_INDEX: "00", SZ_SETPOINT: 10.0},
            src_id="01:216136",
            dst_id="--:------",
        ),
        # 2. 2309 Zone 00 setpoint sync 5.0C
        MockMessage(
            code=Code._2309,
            verb=Verb.I_,
            payload={SZ_ZONE_INDEX: "00", SZ_SETPOINT: 5.0},
            src_id="01:216136",
            dst_id="--:------",
        ),
        # 3. 22D9 Boiler setpoint 60.0C (firing)
        MockMessage(
            code=Code._22D9,
            verb=Verb.I_,
            payload={SZ_DOMAIN_INDEX: "00", SZ_SETPOINT: 60.0},
            src_id="01:216136",
            dst_id="--:------",
        ),
        # 4. 22D9 Boiler setpoint 10.0C (idle)
        MockMessage(
            code=Code._22D9,
            verb=Verb.I_,
            payload={SZ_DOMAIN_INDEX: "00", SZ_SETPOINT: 10.0},
            src_id="01:216136",
            dst_id="--:------",
        ),
    ]

    for msg in interleaved_msgs:
        worker.process_message_state(msg)
        # Assert: Throughout the entire sequence, Zone 00 setpoint NEVER oscillates
        assert zone_00.temp_state.setpoint == 5.0
