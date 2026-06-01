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

from typing import Final

from ramses_rf.const import DevType
from ramses_tx.const import MsgId

# Map of device types to sets of OpenTherm MsgIds that are known to be unreliable
QUARANTINED_OT_MSG_IDS: Final[dict[str, set[MsgId]]] = {
    DevType.OTB: {MsgId._0E, MsgId._11},
}
