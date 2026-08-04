"""RAMSES RF - CQRS Domestic Hot Water (DHW) Topology Handler."""

from __future__ import annotations

from ramses_rf.const import Code, DevType
from ramses_rf.enums import TopologyAction
from ramses_rf.messages.core import Message
from ramses_rf.models import TopologyChangedEvent
from ramses_rf.pipeline.topology_handlers.base import TopologyHandler


class DhwTopologyHandler(TopologyHandler):
    """CQRS Topology Handler for Domestic Hot Water (DHW / 07: / 03:)."""

    def consume(self, msg: Message) -> None:
        """Evaluate DHW topology and class promotion rules.

        :param msg: The incoming message envelope.
        :type msg: Message
        """
        if not self._enable_eavesdrop:
            return

        if (
            msg.header.code in (Code._1260, Code._10A0)
            and getattr(msg.src, "type", None) == "07"
        ):
            event = TopologyChangedEvent(
                action=TopologyAction.UPDATE_DEVICE_CLASS,
                device_id=msg.src.id,
                metadata={"device_class": DevType.DHW},
                causation="Rule_DHW_Signature",
            )
            self._emit(event)
