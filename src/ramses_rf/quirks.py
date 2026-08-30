"""Hardware-specific quirks, overrides, and quarantine lists.

RAMSES RF - Protocol Quirks and Schema Exceptions.

This file documents hard-won reverse-engineering knowledge where real-world
Honeywell/Resideo hardware violates its own protocol schemas.
These rules were historically hard-coded into the L3 transport dispatcher.

KNOWN EXCEPTIONS:
1. Cross-Domain Routing:
   Devices matching `msg.src.type == msg.dst.type` where both are HEAT_DEVICES
   can sometimes legally communicate in the HVAC domain (e.g., 22F3 codes).

2. Controller Promotions:
   `DEV_TYPE_MAP.PROMOTABLE_SLUGS` is required because devices will occasionally
   transmit packets outside their standard verb schemas, requiring L7 to
   "promote" their device class dynamically.

3. Verb/Code Schema Violations:
   - CTL / RQ / 3EF1: Controllers are known to illegally request 3EF1.
   - BDR / RQ / 3EF0: BDR91 relays are known to illegally request 3EF0.
   - W_  / 0001: General exception to the rule where W_ is transmitted unexpectedly.

"""

from __future__ import annotations

from typing import Any

from ramses_rf.models import HvacState
from ramses_rf.strategies import _STRATEGY_BY_SCHEME
from ramses_rf.strategies.climarad import ClimaRadStrategy
from ramses_rf.strategies.itho import IthoStrategy
from ramses_tx.const import Code

_CLIMARAD = ClimaRadStrategy()
_ITHO = IthoStrategy()


def apply_hvac_quirks(
    payload: dict[str, Any],
    current_state: HvacState | None,
    msg_code: Code | str,
    scheme: str | None = None,
) -> dict[str, Any]:
    """Resolve stateful FSM conflicts and structural anomalies for HVAC packets.

    Stateful quirks cannot be resolved by stateless parsers. They must be
    intercepted by comparing the incoming packet payload to the existing
    CQRS state immediately prior to hydration.

    When ``scheme`` is ``None`` (the default), all vendor-specific quirks
    are applied.  This preserves the historical behaviour where the caller
    did not know the vendor.  When ``scheme`` is provided, only the
    matching strategy's quirks are applied.

    :param payload: The flattened, canonical telemetry dictionary.
    :type payload: dict[str, Any]
    :param current_state: The existing Read-Model for the device, if any.
    :type current_state: HvacState | None
    :param msg_code: The hex opcode of the incoming message.
    :type msg_code: Code | str
    :param scheme: The vendor scheme (``"orcon"``, ``"itho"``, etc.).
    :type scheme: str | None
    :return: The safely mutated telemetry dictionary.
    :rtype: dict[str, Any]
    """
    if strategy_cls := _STRATEGY_BY_SCHEME.get(scheme or ""):
        return strategy_cls().apply_quirk(payload, current_state, msg_code)

    # Preserve the historical scheme-agnostic behavior until Step 3 wires
    # the device scheme into both call sites. ClimaRad owns the 12A0
    # structural transformation; Itho adds its 31DA guard after applying
    # the shared normalizations.
    if msg_code == Code._12A0:
        return _CLIMARAD.apply_quirk(payload, current_state, msg_code)
    return _ITHO.apply_quirk(payload, current_state, msg_code)
