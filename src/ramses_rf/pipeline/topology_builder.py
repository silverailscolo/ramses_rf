"""RAMSES RF - The Asynchronous Topology Builder Engine."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ramses_rf.const import (
    I_,
    SZ_DEVICES,
    SZ_DOMAIN_ID,
    SZ_UFH_IDX,
    SZ_ZONE_IDX,
    SZ_ZONE_TYPE,
    ZON_ROLE_MAP,
    Code,
    DevType,
)
from ramses_rf.enums import TopologyAction
from ramses_rf.messages import Message
from ramses_rf.models import TopologyChangedEvent
from ramses_rf.protocol.ramses import CODES_ONLY_FROM_CTL

_LOGGER = logging.getLogger(__name__)


class TopologyBuilder:
    """Centralised engine for heuristic eavesdropping and graph mutation.

    INDUSTRY ARCHITECTURE NOTE: The Rule Engine Pattern
    ---------------------------------------------------
    Because this project relies on reverse-engineered RF protocols, new
    heuristics and manufacturer quirks are discovered frequently. To
    prevent this class from becoming a massive, unmaintainable
    "God Object", we register independent heuristic rules in a list.

    When a message arrives, the engine simply feeds the message to every
    rule in the list. To add a new quirk for a new device, a developer
    simply writes a new method and appends it to `self._rules`. The core
    ingestion logic never needs to be modified.
    """

    def __init__(
        self,
        emit_event_cb: Callable[[TopologyChangedEvent], None],
        enable_eavesdrop: bool = False,
    ) -> None:
        """Initialize the TopologyBuilder.

        :param emit_event_cb: Callback to emit topology events back
            onto the central event bus or directly to the registry.
        :param enable_eavesdrop: If False, heuristic class promotions
            are disabled. Explicit bindings (e.g., 000C) still process.
        """
        self._emit = emit_event_cb
        self._enable_eavesdrop = enable_eavesdrop

        # The active list of heuristic rules. Order does not matter,
        # as each rule independently yields its own isolated events.
        self._rules: list[Callable[[Message], None]] = [
            self._evaluate_evohome_rules,
            self._evaluate_zone_binding_rules,
            self._evaluate_directed_telemetry_rules,
            self._evaluate_ufh_rules,
            self._evaluate_hvac_rules,
            self._evaluate_dhw_opentherm_rules,
            self._evaluate_heating_prefix_rules,
            self._evaluate_appliance_control_sync_rules,
        ]

    async def consume(self, msg: Message) -> None:
        """Ingest a message and evaluate it against all registered rules.

        :param msg: The immutable Message L7 envelope to evaluate.
        """
        for rule in self._rules:
            try:
                rule(msg)
            except Exception as err:
                # Isolate rule execution. A crash in a new, experimental
                # quirk rule must not bring down the discovery pipeline.
                _LOGGER.error(f"Error evaluating topology rule {rule.__name__}: {err}")

    def _evaluate_evohome_rules(self, msg: Message) -> None:
        """Evaluate rules specific to the Evohome CH/DHW ecosystem.

        Historically, entities intercepted CODES_ONLY_FROM_CTL to
        dynamically promote themselves to Controllers. We now extract
        that logic into this explicit, trackable rule.
        """
        if not self._enable_eavesdrop:
            return

        if msg.verb == I_ and msg.code in CODES_ONLY_FROM_CTL:
            event = TopologyChangedEvent(
                action=TopologyAction.CREATE_CONTROLLER,
                device_id=msg.src.id,
                causation="Rule_Evohome_Controller_Broadcast",
            )
            self._emit(event)

    def _evaluate_zone_binding_rules(self, msg: Message) -> None:
        """Evaluate 000C and heuristic packets to bind actuators to zones."""

        # EXPLICIT BINDING: Controllers (01) broadcasting 000C device maps
        if msg.code == Code._000C and msg.src.type == "01":
            # Safely handle both single dicts and arrays of dicts
            payloads = msg.payload if isinstance(msg.payload, list) else [msg.payload]

            for p in payloads:
                if not isinstance(p, dict):
                    continue

                zone_idx = p.get("zone_idx")
                domain_id = p.get("domain_id")
                device_role = p.get("device_role")
                devices = p.get("devices", [])

                if not devices:
                    continue

                # Prepare the base metadata dict, correctly flagging
                # all types of sensors (e.g., 'sensor', 'dhw_sensor')
                metadata: dict[str, Any] = {}
                if device_role is not None:
                    metadata["is_sensor"] = "sensor" in str(device_role)
                    metadata["device_role"] = str(
                        device_role
                    )  # Explicit DHW preservation

                if zone_idx is not None:
                    # Clone metadata to avoid cross-iteration pollution
                    event_meta = dict(metadata)
                    event_meta["zone_idx"] = zone_idx
                    for child_id in devices:
                        event = TopologyChangedEvent(
                            action=TopologyAction.BIND_DEVICE,
                            parent_id=msg.src.id,  # The Controller
                            child_id=child_id,  # The Device
                            metadata=event_meta,
                            causation="Rule_000C_Zone_Binding",
                        )
                        self._emit(event)

                elif domain_id is not None:
                    event_meta = dict(metadata)
                    event_meta["domain_id"] = domain_id
                    for child_id in devices:
                        event = TopologyChangedEvent(
                            action=TopologyAction.BIND_DEVICE,
                            parent_id=msg.src.id,  # The Controller
                            child_id=child_id,  # The Device
                            metadata=event_meta,
                            causation="Rule_000C_Domain_Binding",
                        )
                        self._emit(event)

    def _evaluate_directed_telemetry_rules(self, msg: Message) -> None:
        """Evaluate implicit bindings from directed telemetry broadcasts.

        Devices (TRVs, Thermostats, DHW sensors) explicitly declare their
        topological relationships by broadcasting telemetry (e.g., 30C9,
        3150, 1060, 1260) directly to their parent Controller (01).
        """
        if not self._enable_eavesdrop:
            return

        # Broaden the net: Intercept ANY directed telemetry to a Controller,
        # but strictly prevent the Controller from binding to itself.
        if msg.verb == I_ and msg.dst.type == "01" and msg.src.id != msg.dst.id:
            # Safely handle both single dicts and arrays of dicts (like 1060)
            payloads = msg.payload if isinstance(msg.payload, list) else [msg.payload]

            for p in payloads:
                if not isinstance(p, dict):
                    continue

                # Strictly separate Zone routing from Domain routing
                zone_idx = p.get(SZ_ZONE_IDX)
                domain_id = p.get(SZ_DOMAIN_ID)

                if zone_idx is not None:
                    event = TopologyChangedEvent(
                        action=TopologyAction.BIND_DEVICE,
                        parent_id=msg.dst.id,
                        child_id=msg.src.id,
                        metadata={"zone_idx": str(zone_idx)},
                        causation="Rule_Directed_Telemetry_Binding_Zone",
                    )
                    self._emit(event)

                elif domain_id is not None:
                    event = TopologyChangedEvent(
                        action=TopologyAction.BIND_DEVICE,
                        parent_id=msg.dst.id,
                        child_id=msg.src.id,
                        metadata={"domain_id": str(domain_id)},
                        causation="Rule_Directed_Telemetry_Binding_Domain",
                    )
                    self._emit(event)

    def _evaluate_ufh_rules(self, msg: Message) -> None:
        """Evaluate rules specific to Underfloor Heating (UFH).

        UFCs broadcast their circuit mappings via 000C messages.
        We intercept these to bind the UFC to the Controller and map
        the individual circuits to their corresponding zones.
        Note: This is explicit configuration data, not a heuristic,
        so it is processed regardless of the enable_eavesdrop flag.
        """
        # Prefix Guard: Ensure the source is an Underfloor Heating Controller
        if msg.src.type != "02":
            return

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

        HVAC devices share prefixes (e.g., 32: can be a Fan, CO2, etc.).
        Therefore, we promote classes based purely on signature codes.
        """
        if not self._enable_eavesdrop:
            return

        if msg.code in (Code._31D9, Code._31DA):
            event = TopologyChangedEvent(
                action=TopologyAction.PROMOTE_CLASS,
                device_id=msg.src.id,
                metadata={"device_class": DevType.FAN},
                causation="Rule_HVAC_Fan_Signature",
            )
            self._emit(event)

        elif msg.code == Code._1298:
            event = TopologyChangedEvent(
                action=TopologyAction.PROMOTE_CLASS,
                device_id=msg.src.id,
                metadata={"device_class": DevType.CO2},
                causation="Rule_HVAC_CO2_Signature",
            )
            self._emit(event)

        elif msg.code == Code._12A0:
            event = TopologyChangedEvent(
                action=TopologyAction.PROMOTE_CLASS,
                device_id=msg.src.id,
                metadata={"device_class": DevType.HUM},
                causation="Rule_HVAC_HUM_Signature",
            )
            self._emit(event)

        elif msg.code in (Code._22F1, Code._22F3):
            event = TopologyChangedEvent(
                action=TopologyAction.PROMOTE_CLASS,
                device_id=msg.src.id,
                metadata={"device_class": DevType.REM},
                causation="Rule_HVAC_REM_Signature",
            )
            self._emit(event)

    def _evaluate_dhw_opentherm_rules(self, msg: Message) -> None:
        """Evaluate rules specific to DHW and OpenTherm Bridges.

        OpenTherm Bridges exclusively use 3220. DHW sensors are deduced
        via 1260 and 10A0 packets.
        """
        if not self._enable_eavesdrop:
            return

        # Prefix Guard: Prevent cross-promotion (e.g., OTB sending 1260)
        if msg.code == Code._3220 and msg.src.type == "10":
            event = TopologyChangedEvent(
                action=TopologyAction.PROMOTE_CLASS,
                device_id=msg.src.id,
                metadata={"device_class": DevType.OTB},
                causation="Rule_OTB_3220_Signature",
            )
            self._emit(event)

        elif msg.code in (Code._1260, Code._10A0) and msg.src.type == "07":
            event = TopologyChangedEvent(
                action=TopologyAction.PROMOTE_CLASS,
                device_id=msg.src.id,
                metadata={"device_class": DevType.DHW},
                causation="Rule_DHW_Signature",
            )
            self._emit(event)

    def _evaluate_heating_prefix_rules(self, msg: Message) -> None:
        """Evaluate passive heuristics based purely on hardware prefixes.

        Legacy architecture automatically promoted generic devices into specific
        heating domain subtypes (e.g., TRV, UFC, BDR) the moment their address
        was observed anywhere in the packet (src, dst, or embedded in payload).
        """
        if not self._enable_eavesdrop:
            return

        prefix_map = {
            "02": DevType.UFC,
            "03": DevType.HCW,
            "04": DevType.TRV,
            "12": DevType.THM,
            "13": DevType.BDR,
            "22": DevType.THM,
            "34": DevType.THM,
        }

        # The `_addrs` tuple contains the header addresses (src, dst) AND any
        # addresses deeply embedded in the raw payload (e.g. 000C arrays).
        addrs = getattr(msg._pkt, "_addrs", [])

        # Fallback to src/dst if _addrs is somehow missing
        if not addrs:
            addrs = [msg.src]
            if msg.dst:
                addrs.append(msg.dst)

        for addr in addrs:
            if getattr(addr, "type", None) in prefix_map:
                event = TopologyChangedEvent(
                    action=TopologyAction.PROMOTE_CLASS,
                    device_id=addr.id,
                    metadata={"device_class": prefix_map[addr.type]},
                    causation="Rule_Heating_Prefix_Heuristic",
                )
                self._emit(event)

    def _evaluate_appliance_control_sync_rules(self, msg: Message) -> None:
        """Evaluate direct configuration syncs to map the System Relay.

        :param msg: The immutable Message L7 envelope to evaluate.
        :type msg: Message
        :return: None
        :rtype: None
        """
        if not self._enable_eavesdrop:
            return

        # Guard: Catch direct commands from the Controller (01) to a Relay (13)
        if msg.src.type == "01" and msg.dst and msg.dst.type == "13":
            # 1100 (Boiler Params) or 10E0/1FC9 (Binding) are direct links
            if msg.code in (Code._1100, Code._10E0, Code._1FC9):
                event = TopologyChangedEvent(
                    action=TopologyAction.BIND_DEVICE,
                    parent_id=msg.src.id,
                    child_id=msg.dst.id,
                    metadata={"domain_id": "FC", "device_role": "appliance_control"},
                    causation="Rule_Direct_Relay_Sync",
                )
                self._emit(event)
