"""Hardware-specific quirks, overrides, and quarantine lists."""

from __future__ import annotations

from typing import Final

from ramses_rf.const import DevType
from ramses_tx.const import MsgId

# Map of device types to sets of OpenTherm MsgIds that are known to be unreliable
QUARANTINED_OT_MSG_IDS: Final[dict[str, set[MsgId]]] = {
    DevType.OTB: {MsgId._0E, MsgId._11},
}
