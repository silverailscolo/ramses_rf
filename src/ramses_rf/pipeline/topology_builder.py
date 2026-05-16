"""RAMSES RF - The Asynchronous Topology Builder Engine."""

from __future__ import annotations

from collections.abc import Callable

from ramses_rf.const import (
    I_,
    SZ_DEVICES,
    SZ_UFH_IDX,
    SZ_ZONE_IDX,
    SZ_ZONE_TYPE,
    ZON_ROLE_MAP,
    Code,
)
from ramses_rf.enums import TopologyAction
from ramses_rf.messages import Message
from ramses_rf.models import TopologyChangedEvent
from ramses_rf.protocol.ramses import CODES_ONLY_FROM_CTL


class TopologyBuilder:
    """Centralized engine for heuristic eavesdropping and graph mutation.

    This engine consumes Message objects from the Discovery Queue and
    evaluates them against protocol-specific rulesets. When a structural
    relationship is deduced, it emits a TopologyChangedEvent. By keeping
    this logic here, Domain Entities (like Devices) remain pure, dumb
    CQRS Read-Models that do not mutate the network structure.
    """

    def __init__(
        self,
        emit_event_cb: Callable[[TopologyChangedEvent], None],
    ) -> None:
        """Initialize the TopologyBuilder.

        :param emit_event_cb: Callback to emit topology events back
            onto the central event bus or directly to the registry.
        """
        self._emit = emit_event_cb

    async def consume(self, msg: Message) -> None:
        """Ingest a message and evaluate all heuristic rulesets.

        :param msg: The immutable Message L7 envelope to evaluate.
        """
        self._evaluate_evohome_rules(msg)
        self._evaluate_ufh_rules(msg)
        self._evaluate_hvac_rules(msg)
        self._evaluate_dhw_opentherm_rules(msg)

    def _evaluate_evohome_rules(self, msg: Message) -> None:
        """Evaluate rules specific to the Evohome CH/DHW ecosystem.

        Historically, entities intercepted CODES_ONLY_FROM_CTL to
        dynamically promote themselves to Controllers. We now extract
        that logic into this explicit, trackable rule.
        """
        if msg.verb == I_ and msg.code in CODES_ONLY_FROM_CTL:
            # If a device broadcasts a code only controllers can send,
            # we deduce it must be a controller.
            event = TopologyChangedEvent(
                action=TopologyAction.CREATE_CONTROLLER,
                device_id=msg.src.id,
                causation="Rule_Evohome_Controller_Broadcast",
            )
            self._emit(event)

    def _evaluate_ufh_rules(self, msg: Message) -> None:
        """Evaluate rules specific to Underfloor Heating (UFH).

        UFCs broadcast their circuit mappings via 000C messages.
        We intercept these to bind the UFC to the Controller and map
        the individual circuits to their corresponding zones.
        """
        if msg.code != Code._000C:
            return

        zone_type = msg.payload.get(SZ_ZONE_TYPE)
        if zone_type not in (ZON_ROLE_MAP.ACT, ZON_ROLE_MAP.UFH):
            return

        devices = msg.payload.get(SZ_DEVICES, [])
        if not devices:
            return

        ctl_id = devices[0]
        ufc_id = msg.src.id

        # 1. Bind the UFC to the parent Controller
        event_bind = TopologyChangedEvent(
            action=TopologyAction.BIND_DEVICE,
            parent_id=ctl_id,
            child_id=ufc_id,
            causation="Rule_UFH_000C_Binding",
        )
        self._emit(event_bind)

        # 2. Create the Circuit and map it to the Zone
        ufh_idx = msg.payload.get(SZ_UFH_IDX)
        zone_idx = msg.payload.get(SZ_ZONE_IDX)

        if ufh_idx is not None:
            event_circuit = TopologyChangedEvent(
                action=TopologyAction.CREATE_CIRCUIT,
                device_id=ufc_id,
                metadata={
                    "ufh_idx": ufh_idx,
                    "zone_idx": zone_idx if zone_idx else "None",
                },
                causation="Rule_UFH_000C_Circuit",
            )
            self._emit(event_circuit)

    def _evaluate_hvac_rules(self, msg: Message) -> None:
        """Evaluate rules specific to Ventilation and HVAC.

        HVAC devices are often identified by their unique payload codes
        (like 31DA for ventilators or 1298 for CO2 sensors).
        """
        if msg.code in (Code._31D9, Code._31DA):
            event = TopologyChangedEvent(
                action=TopologyAction.PROMOTE_CLASS,
                device_id=msg.src.id,
                metadata={"device_class": "FAN"},
                causation="Rule_HVAC_Fan_Signature",
            )
            self._emit(event)

        elif msg.code == Code._1298:
            event = TopologyChangedEvent(
                action=TopologyAction.PROMOTE_CLASS,
                device_id=msg.src.id,
                metadata={"device_class": "CO2"},
                causation="Rule_HVAC_CO2_Signature",
            )
            self._emit(event)

        elif msg.code == Code._12A0:
            event = TopologyChangedEvent(
                action=TopologyAction.PROMOTE_CLASS,
                device_id=msg.src.id,
                metadata={"device_class": "HUM"},
                causation="Rule_HVAC_HUM_Signature",
            )
            self._emit(event)

    def _evaluate_dhw_opentherm_rules(self, msg: Message) -> None:
        """Evaluate rules specific to DHW and OpenTherm Bridges.

        OpenTherm Bridges exclusively use 3220. DHW sensors are deduced
        via 1260 and 10A0 packets.
        """
        if msg.code == Code._3220:
            event = TopologyChangedEvent(
                action=TopologyAction.PROMOTE_CLASS,
                device_id=msg.src.id,
                metadata={"device_class": "OTB"},
                causation="Rule_OTB_3220_Signature",
            )
            self._emit(event)

        elif msg.code in (Code._1260, Code._10A0):
            event = TopologyChangedEvent(
                action=TopologyAction.PROMOTE_CLASS,
                device_id=msg.src.id,
                metadata={"device_class": "DHW"},
                causation="Rule_DHW_Signature",
            )
            self._emit(event)
