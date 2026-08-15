"""RAMSES RF - CQRS OpenTherm Bridge (OTB) Topology Handler."""

from __future__ import annotations

from ramses_rf.const import DevType
from ramses_rf.enums import TopologyAction
from ramses_rf.messages.core import Message
from ramses_rf.models import TopologyChangedEvent
from ramses_rf.pipeline.topology_handlers.base import TopologyHandler
from ramses_tx.const import Code


class OtbTopologyHandler(TopologyHandler):
    """CQRS Topology Handler for OpenTherm Bridge (OTB / 10:)."""

    def consume(self, msg: Message) -> None:
        """Evaluate OpenTherm Bridge topology discovery rules.

        :param msg: The incoming message envelope.
        :type msg: Message
        """
        if not self._enable_eavesdrop:
            return

        if (
            msg.header.code == Code._3220
            and getattr(msg.src, "type", None) == "10"
        ):
            event = TopologyChangedEvent(
                action=TopologyAction.UPDATE_DEVICE_CLASS,
                device_id=msg.src.id,
                metadata={"device_class": DevType.OTB},
                causation="Rule_OTB_3220_Signature",
            )
            self._emit(event)
