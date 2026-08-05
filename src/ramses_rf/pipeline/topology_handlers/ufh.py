"""RAMSES RF - CQRS Underfloor Heating (UFH) Topology Handler."""

from __future__ import annotations

from typing import Any

from ramses_rf.const import ZON_ROLE_MAP, DevType
from ramses_rf.enums import TopologyAction
from ramses_rf.messages.core import Message
from ramses_rf.models import TopologyChangedEvent
from ramses_rf.pipeline.topology_handlers.base import TopologyHandler
from ramses_tx.const import SZ_UFH_IDX, SZ_ZONE_IDX, SZ_ZONE_TYPE, Code


class UfhTopologyHandler(TopologyHandler):
    """CQRS Topology Handler for Underfloor Heating Controllers (UFC / 02:)."""

    def consume(self, msg: Message) -> None:
        """Evaluate rules specific to Underfloor Heating (UFH).

        UFCs broadcast their circuit mappings via 000C messages.
        We intercept these to bind the UFC to the Controller and map
        the individual circuits to their corresponding zones.
        Note: This is explicit configuration data, not a heuristic,
        so it is processed regardless of the enable_eavesdrop flag.

        :param msg: The immutable Message L7 envelope to evaluate.
        :type msg: Message
        :returns: None
        :rtype: None
        """
        is_ufc_src = getattr(msg.src, "type", None) in ("02", DevType.UFC)
        is_ufc_dst = getattr(msg.dst, "type", None) in ("02", DevType.UFC)

        if not (is_ufc_src or is_ufc_dst):
            return

        ufc_id = msg.src.id if is_ufc_src else msg.dst.id

        # Identify the Controller ID if present in the conversation
        ctl_id = None
        if getattr(msg.src, "type", None) in ("01", DevType.CTL):
            ctl_id = msg.src.id
        elif getattr(msg.dst, "type", None) in ("01", DevType.CTL):
            ctl_id = msg.dst.id
        elif getattr(msg.addr3, "type", None) in ("01", DevType.CTL):
            ctl_id = msg.addr3.id

        # 1. Conversational Binding: Promote and bind if communicating with a Controller
        if ctl_id and ctl_id != ufc_id:
            # Explicitly promote to UFC, This prevents HVAC devices from being
            # falsely flagged and dropped by the strict parser before they can
            # be routed.
            event_promote = TopologyChangedEvent(
                action=TopologyAction.UPDATE_DEVICE_CLASS,
                device_id=ufc_id,
                metadata={"device_class": DevType.UFC},
                causation="Rule_UFH_Communication_Promotion",
            )
            self._emit(event_promote)

            # Bind the UFC to the parent Controller
            event_bind = TopologyChangedEvent(
                action=TopologyAction.BIND_DEVICE,
                parent_id=ctl_id,
                child_id=ufc_id,
                metadata={"device_role": "ufc"},
                causation="Rule_UFH_Communication_Binding",
            )
            self._emit(event_bind)

        # 2. Extract specific circuit topology from 000C configuration packets
        if is_ufc_src and msg.header.code == Code._000C:
            # Fallback to direct property check first for legacy compatibility
            # Bypassing strict typing evaluation by casting to Any
            raw_data: Any = msg.data
            zone_type = (
                raw_data.get(SZ_ZONE_TYPE) if isinstance(raw_data, dict) else None
            )
            if zone_type and zone_type not in (ZON_ROLE_MAP.ACT, ZON_ROLE_MAP.UFH):
                return

            for p in self._get_payloads(msg):
                if not isinstance(p, dict):
                    continue

                ufh_idx = p.get(SZ_UFH_IDX)
                zone_idx = p.get(SZ_ZONE_IDX)

                if ufh_idx is not None:
                    event_circuit = TopologyChangedEvent(
                        action=TopologyAction.CREATE_CIRCUIT,
                        device_id=ufc_id,
                        metadata={
                            "ufh_idx": str(ufh_idx),
                            "zone_idx": str(zone_idx) if zone_idx else "None",
                            "child_id": str(zone_idx) if zone_idx else "None",
                        },
                        causation="Rule_UFH_000C_Circuit",
                    )
                    self._emit(event_circuit)
