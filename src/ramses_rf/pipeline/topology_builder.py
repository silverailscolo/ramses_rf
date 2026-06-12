"""RAMSES RF - The Asynchronous Topology Builder Engine."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, cast

from ramses_rf.const import (
    I_,
    RQ,
    SZ_DEVICES,
    SZ_DOMAIN_ID,
    SZ_TEMPERATURE,
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
from ramses_tx import DeviceIdT

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

        # FIXME: LEGACY DEBT - State Cache for Flawed Temporal Rules
        # The legacy architecture relied on comparing current packets
        # against previously observed packets to deduce bindings
        # (e.g., 30C9 temperature matching, 3B00 sequential matching).
        # This cache isolates that fragile state until Phase 3 rewrites.
        self._legacy_debt_cache: dict[str, Any] = {
            "prev_3b00": None,
            "trv_temps": {},
            "zone_temps": {},
        }

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
            self._evaluate_appliance_eavesdrop_rules,
            self._evaluate_zone_sensor_matching_rules,
            self._evaluate_zone_type_eavesdrop_rules,
        ]

    async def consume(self, msg: Message) -> None:
        """Ingest a message and evaluate it against all registered rules.

        :param msg: The immutable Message L7 envelope to evaluate.
        """
        for rule in self._rules:
            try:
                rule(msg)
            except Exception as err:
                # Do not spam the logs with topology rejection errors when
                # enforcing strict schemas or ignoring missing/poison devices.
                if "changed app_cntrl" in str(err) or "Can't create" in str(err):
                    _LOGGER.debug("Topology rule %s bypassed: %s", rule.__name__, err)
                else:
                    _LOGGER.error(
                        "Error evaluating topology rule %s: %s", rule.__name__, err
                    )

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

    def _evaluate_appliance_eavesdrop_rules(self, msg: Message) -> None:
        """Evaluate the legacy passive eavesdropping of the System Relay.

        # TODO: PARITY FLAW - This replicates legacy `eavesdrop_appliance_control`.
        It relies on fragile assumptions regarding typical message flows
        (e.g., 3220, 3EF0, 3B00) between the Controller and the Heat Relay.
        """
        if not self._enable_eavesdrop:
            return

        if msg.code not in (Code._3220, Code._3B00, Code._3EF0):
            return

        app_cntrl_id: DeviceIdT | None = None

        if msg.code == Code._3220 and msg.verb == RQ:
            if msg.src.type == "01" and msg.dst and msg.dst.type == "10":
                app_cntrl_id = msg.dst.id

        elif msg.code == Code._3EF0 and msg.verb == RQ:
            if msg.src.type == "01" and msg.dst and msg.dst.type in ("10", "13"):
                app_cntrl_id = msg.dst.id

        elif msg.code == Code._3B00 and msg.verb == I_:
            # Sequence matching: 13: broadcasts 3B00, followed by 01: broadcasting 3B00
            if msg.src.type == "13":
                self._legacy_debt_cache["prev_3b00"] = msg
            elif msg.src.type == "01":
                prev = self._legacy_debt_cache.get("prev_3b00")
                if prev and prev.payload == msg.payload:
                    app_cntrl_id = prev.src.id

        if app_cntrl_id is not None:
            event = TopologyChangedEvent(
                action=TopologyAction.BIND_DEVICE,
                parent_id=msg.src.id,  # Assume src is the Controller
                child_id=app_cntrl_id,
                metadata={"domain_id": "FC", "device_role": "appliance_control"},
                causation="Rule_Legacy_Appliance_Eavesdrop",
            )
            self._emit(event)

    def _evaluate_zone_sensor_matching_rules(self, msg: Message) -> None:
        """Evaluate the legacy collision-abstention temperature matching.

        # TODO: PARITY FLAW - This replicates `_eavesdrop_zone_sensors`.
        It binds TRVs to Zones by matching random temperature telemetry.
        It is highly prone to race conditions and false positives.
        """
        if not self._enable_eavesdrop or msg.code != Code._30C9:
            return

        # 1. TRV Temp Cache Population
        if getattr(msg.src, "type", None) == "04" and isinstance(msg.payload, dict):
            temp = msg.payload.get(SZ_TEMPERATURE)
            if temp is not None:
                self._legacy_debt_cache["trv_temps"][msg.src.id] = temp

        # 2. Controller Zone Temp Cache Population
        if getattr(msg, "_has_array", False) and msg.src.type == "01":
            payloads = msg.payload if isinstance(msg.payload, list) else [msg.payload]
            ctl_id = msg.src.id
            ctl_cache = self._legacy_debt_cache["zone_temps"].setdefault(ctl_id, {})

            for z in payloads:
                z_idx = z.get(SZ_ZONE_IDX)
                z_tmp = z.get(SZ_TEMPERATURE)
                if z_idx is not None and z_tmp is not None:
                    ctl_cache[z_idx] = z_tmp

        # 3. Collision Abstention Cross-Match
        # This intentionally mimics the legacy logic: if exactly one TRV matches
        # exactly one Zone temperature, we bind them.
        trvs = cast(dict[DeviceIdT, float], self._legacy_debt_cache["trv_temps"])
        ctls = cast(
            dict[DeviceIdT, dict[str, float]], self._legacy_debt_cache["zone_temps"]
        )

        for cache_ctl_id, zones in ctls.items():
            for z_idx, z_tmp in zones.items():
                matching_trvs = [t_id for t_id, t_tmp in trvs.items() if t_tmp == z_tmp]
                # Flawed logic: only bind if exactly ONE TRV shares this temperature
                if len(matching_trvs) == 1:
                    trv_id = matching_trvs[0]
                    event = TopologyChangedEvent(
                        action=TopologyAction.BIND_DEVICE,
                        parent_id=cache_ctl_id,
                        child_id=trv_id,
                        metadata={"zone_idx": str(z_idx), "is_sensor": True},
                        causation="Rule_Legacy_Temperature_Matching",
                    )
                    self._emit(event)

    def _evaluate_zone_type_eavesdrop_rules(self, msg: Message) -> None:
        """Evaluate the legacy passive promotion of zone classes.

        # TODO: PARITY FLAW - This replicates `eavesdrop_zone_type` from `zones.py`.
        It arbitrarily maps zones to VAL, ELE, RAD, or UFH based purely on
        telemetry packet signatures.
        """
        if not self._enable_eavesdrop:
            return

        payloads = msg.payload if isinstance(msg.payload, list) else [msg.payload]

        for p in payloads:
            if not isinstance(p, dict):
                continue

            zone_idx = p.get(SZ_ZONE_IDX)
            if zone_idx is None:
                continue

            zone_class: str | None = None

            # 0008/0009 packets denote Electric or Valve configurations
            if msg.code in (Code._0008, Code._0009):
                zone_class = ZON_ROLE_MAP["ELE"]

            # 3150 Demand mappings denote specific actuator types
            elif msg.code == Code._3150:
                src_type = getattr(msg.src, "type", None)
                if src_type == "04":
                    zone_class = ZON_ROLE_MAP["RAD"]
                elif src_type == "13":
                    zone_class = ZON_ROLE_MAP["VAL"]
                elif src_type == "02":
                    zone_class = ZON_ROLE_MAP["UFH"]

            if zone_class is not None:
                # We emit a BIND_DEVICE action targeting the controller,
                # passing the deduced zone_class as metadata for the projection.
                event = TopologyChangedEvent(
                    action=TopologyAction.BIND_DEVICE,
                    parent_id=msg.src.id,  # Typically the Controller
                    child_id=msg.src.id,  # Self-referential to update the zone metadata
                    metadata={
                        "zone_idx": str(zone_idx),
                        "zone_class": zone_class,
                    },
                    causation="Rule_Legacy_Zone_Type_Eavesdrop",
                )
                self._emit(event)
