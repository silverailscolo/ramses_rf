"""RAMSES RF - Base classes for CQRS Subsystem Topology Handlers."""

from __future__ import annotations

import abc
from collections.abc import Callable
from typing import Any

from ramses_rf.messages.core import Message
from ramses_rf.models import TopologyChangedEvent


class TopologyHandler(abc.ABC):
    """Abstract base class for subsystem-specific topology handlers."""

    def __init__(
        self,
        emit_event_cb: Callable[[TopologyChangedEvent], None],
        enable_eavesdrop: bool = False,
        device_class_lookup_cb: Callable[[str], dict[str, Any] | None]
        | None = None,
    ) -> None:
        """Initialize the subsystem topology handler.

        :param emit_event_cb: Callback to emit topology events onto CQRS event bus.
        :type emit_event_cb: Callable[[TopologyChangedEvent], None]
        :param enable_eavesdrop: If True, heuristic class promotions are enabled.
        :type enable_eavesdrop: bool
        :param device_class_lookup_cb: Optional callback to look up the
            current device traits (dict with keys like "class",
            "locked") by device_id.  Used by handlers that need to
            detect contradictions between the known_list class and
            observed message patterns.
        :type device_class_lookup_cb: Callable[[str], dict[str, Any] | None] | None
        """
        self._emit: Callable[[TopologyChangedEvent], None] = emit_event_cb
        self._enable_eavesdrop: bool = enable_eavesdrop
        self._device_class_lookup_cb: (
            Callable[[str], dict[str, Any] | None] | None
        ) = device_class_lookup_cb

    @abc.abstractmethod
    def consume(self, msg: Message) -> None:
        """Process an incoming message for subsystem topology extraction.

        :param msg: The immutable L7 Message envelope.
        :type msg: Message
        """
        ...

    @staticmethod
    def _get_payloads(msg: Message) -> list[Any]:
        """Safely extract the array or standard dictionary payload.

        :param msg: The message containing payload data.
        :type msg: Message
        :returns: List of extracted payload dictionaries or items.
        :rtype: list[Any]
        """
        raw: Any = msg.data
        if not raw:
            raw = getattr(msg, "payload", None)
        if isinstance(raw, dict):
            result = raw.get("_array", [raw])
            return result if isinstance(result, list) else [result]
        if isinstance(raw, list):
            return raw
        if raw is not None:
            return [raw]
        return []
