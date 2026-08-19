"""RAMSES RF - CQRS Ventilation & HVAC Topology Handler."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ramses_rf.const import DevType
from ramses_rf.enums import TopologyAction
from ramses_rf.messages.core import Message
from ramses_rf.models import TopologyChangedEvent
from ramses_rf.pipeline.topology_handlers.base import TopologyHandler
from ramses_rf.protocol.ramses import HVAC_KLASS_BY_VC_PAIR
from ramses_tx.const import Code, Verb

_LOGGER = logging.getLogger(__name__)

# VC pairs that are strong evidence a device is a FAN (broadcasts/responds
# with ventilation status).  A real FAN sends these as src.
_FAN_EVIDENCE: frozenset[tuple[Verb, Code]] = frozenset(
    {
        (Verb.I_, Code._31D9),
        (Verb.I_, Code._31DA),
        (Verb.RP, Code._31DA),
        (Verb.RP, Code._2411),  # FAN responds to 2411 parameter requests
    }
)

# VC pairs that are strong evidence a device is NOT a FAN but a
# remote/display (DIS/REM):
# - RQ 31DA: a DIS/REM requests fan status from the FAN (a FAN never
#   sends RQ 31DA as src).
# - RQ 2411: a DIS/REM requests 2411 parameters from the FAN (a FAN
#   never sends RQ 2411 as src — it responds with RP 2411).
# - I 22F1: a DIS/REM sends fan-mode commands to the FAN (a FAN never
#   sends I 22F1 as src — it receives them).
_NON_FAN_EVIDENCE: frozenset[tuple[Verb, Code]] = frozenset(
    {
        (Verb.RQ, Code._31DA),
        (Verb.RQ, Code._2411),
        (Verb.I_, Code._22F1),
    }
)

# Minimum number of contradictory packets before reclassifying.
_RECLASSIFY_THRESHOLD: int = 3


class HvacTopologyHandler(TopologyHandler):
    """CQRS Topology Handler for Ventilation and HVAC devices."""

    def __init__(
        self,
        emit_event_cb: Callable[[TopologyChangedEvent], None],
        enable_eavesdrop: bool = False,
        device_class_lookup_cb: Callable[[str], dict[str, Any] | None]
        | None = None,
    ) -> None:
        """Initialize the handler with per-device evidence tracking.

        :param emit_event_cb: Callback to emit topology events.
        :param enable_eavesdrop: If True, heuristic class promotions are enabled.
        :param device_class_lookup_cb: Optional callback to look up the
            current device traits (dict with "class", "locked", etc.)
            by device_id.  Used to detect contradictions between the
            known_list class and observed message patterns.
        """
        super().__init__(
            emit_event_cb,
            enable_eavesdrop=enable_eavesdrop,
            device_class_lookup_cb=device_class_lookup_cb,
        )
        # Per-device evidence: {device_id: {"fan": int, "non_fan": int}}
        self._evidence: dict[str, dict[str, int]] = {}

    def consume(self, msg: Message) -> None:
        """Evaluate HVAC class promotion rules.

        :param msg: The incoming message envelope.
        :type msg: Message
        """
        msg_verb = msg.header.verb
        msg_code = str(msg.header.code)

        # --- Standard promotion via VC pair lookup ---
        # Only run heuristic promotions when eavesdrop is enabled.
        if self._enable_eavesdrop:
            dev_class = None
            for (
                schema_verb,
                schema_code,
            ), dev_class_name in HVAC_KLASS_BY_VC_PAIR.items():
                if (schema_verb is None or schema_verb == msg_verb) and str(
                    schema_code
                ) == msg_code:
                    dev_class = dev_class_name
                    break

            if dev_class:
                if msg.src.id != "--:------" and getattr(
                    msg.src, "type", None
                ) not in (
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
                    and getattr(msg.dst, "type", None)
                    not in ("01", DevType.CTL)
                ):
                    self._emit(
                        TopologyChangedEvent(
                            action=TopologyAction.UPDATE_DEVICE_CLASS,
                            device_id=msg.dst.id,
                            metadata={"device_class": dev_class},
                            causation="Rule_HVAC_Signature_Target",
                        )
                    )

        # --- Contradiction detection: FAN misclassified as DIS/REM ---
        # Track evidence for the src device.  If a device currently typed
        # as FAN only sends RQ 31DA (non-FAN behavior) and never sends
        # I/RP 31DA or I 31D9 (FAN behavior), it is likely a DIS or REM
        #
        # TODO: The reclassification target is always DIS, but we cannot
        # reliably distinguish DIS from REM yet.  A DIS (Orcon RF15
        # Display) sends RQ 2411 and RQ 31DA as normal behavior, while a
        # bound REM only sends 2411 when prompted by a VMI.  The protocol
        # table (_DEV_KLASSES_HVAC) lists 2411 for both REM and DIS with
        # "VMI only?" caveats for REM.  When the strategy pattern arrives
        # (issue 939), a DisStrategy could use 2411 frequency or the
        # presence of 1470/042F (DIS-only codes) to distinguish.
        # See also: discovery_scan.py _classify,
        # protocol/ramses.py _HVAC_VC_PAIR_BY_CLASS.
        # that was wrongly promoted to FAN.
        if msg.src.id != "--:------":
            src_id = msg.src.id
            vc = (msg_verb, msg.header.code)
            ev = self._evidence.setdefault(src_id, {"fan": 0, "non_fan": 0})
            if vc in _FAN_EVIDENCE:
                ev["fan"] += 1
            elif vc in _NON_FAN_EVIDENCE:
                ev["non_fan"] += 1

            # Check for contradiction: device is typed FAN but behaves
            # like a DIS/REM.  We look up the current device traits via
            # the callback (msg.src.type is only the address prefix,
            # not the device class).
            traits = (
                self._device_class_lookup_cb(src_id)
                if self._device_class_lookup_cb
                else None
            )
            current_class = traits.get("class") if traits else None
            is_locked = bool(traits.get("locked")) if traits else False

            if (
                current_class == DevType.FAN
                and ev["non_fan"] >= _RECLASSIFY_THRESHOLD
                and ev["fan"] == 0
            ):
                if is_locked:
                    # User has explicitly locked this device's class.
                    # Log once at INFO level and do not emit a
                    # reclassification event — _locked means "don't
                    # touch this".
                    if not ev.get("warned_locked", False):
                        _LOGGER.info(
                            "Device %s is typed as FAN but behaves as "
                            "a DIS/REM (%d non-FAN packets, 0 FAN "
                            "packets) — class is locked by user, "
                            "not reclassifying",
                            src_id,
                            ev["non_fan"],
                        )
                        ev["warned_locked"] = True
                else:
                    # Emit the reclassification event every time (the
                    # SSOT update is idempotent, and this ensures the
                    # discovery/config flow sees the suggestion even
                    # if it was missed on the first emit).
                    self._emit(
                        TopologyChangedEvent(
                            action=TopologyAction.UPDATE_DEVICE_CLASS,
                            device_id=src_id,
                            metadata={"device_class": DevType.DIS},
                            causation="Rule_HVAC_Contradiction_FAN_to_DIS",
                        )
                    )
                    # Warn only once per session to avoid log spam.
                    # The device object stays as FAN (notify-only
                    # strategy) so the class lookup keeps returning
                    # FAN — the warned flag prevents repeat warnings
                    # until the user accepts the change via the config
                    # flow (which reloads the integration and resets
                    # the handler).
                    if not ev.get("warned", False):
                        _LOGGER.warning(
                            "Device %s is typed as FAN but has only "
                            "sent RQ 31DA / I 22F1 (%d packets) and "
                            "never I/RP 31DA or I 31D9 — suggesting "
                            "reclassification to DIS (likely a "
                            "display/remote, not a ventilator).  Run "
                            "the discovery/config flow to accept this "
                            "change, or add '_locked: true' to "
                            "suppress this warning.",
                            src_id,
                            ev["non_fan"],
                        )
                        ev["warned"] = True
