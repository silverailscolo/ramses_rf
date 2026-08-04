"""RAMSES RF - CQRS Ventilation & HVAC Topology Handler."""

from __future__ import annotations

from ramses_rf.const import DevType
from ramses_rf.enums import TopologyAction
from ramses_rf.messages.core import Message
from ramses_rf.models import TopologyChangedEvent
from ramses_rf.pipeline.topology_handlers.base import TopologyHandler
from ramses_rf.protocol.ramses import HVAC_KLASS_BY_VC_PAIR


class HvacTopologyHandler(TopologyHandler):
    """CQRS Topology Handler for Ventilation and HVAC devices."""

    def consume(self, msg: Message) -> None:
        """Evaluate HVAC class promotion rules.

        :param msg: The incoming message envelope.
        :type msg: Message
        """
        if not self._enable_eavesdrop:
            return

        msg_verb = msg.header.verb
        msg_code = str(msg.header.code)

        dev_class = None
        for (schema_verb, schema_code), dev_class_name in HVAC_KLASS_BY_VC_PAIR.items():
            if (schema_verb is None or schema_verb == msg_verb) and str(
                schema_code
            ) == msg_code:
                dev_class = dev_class_name
                break

        if dev_class:
            if msg.src.id != "--:------" and getattr(msg.src, "type", None) not in (
                "01",
                DevType.CTL,
            ):
                self._emit(
                    TopologyChangedEvent(
                        action=TopologyAction.UPDATE_DEVICE_CLASS,
                        device_id=msg.src.id,
                        metadata={"device_class": dev_class},
                        causation="Rule_HVAC_Signature_Source",
                    )
                )

            if (
                msg.dst.id != "--:------"
                and msg.dst.id != msg.src.id
                and getattr(msg.dst, "type", None) not in ("01", DevType.CTL)
            ):
                self._emit(
                    TopologyChangedEvent(
                        action=TopologyAction.UPDATE_DEVICE_CLASS,
                        device_id=msg.dst.id,
                        metadata={"device_class": dev_class},
                        causation="Rule_HVAC_Signature_Target",
                    )
                )
