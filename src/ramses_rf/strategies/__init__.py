"""RAMSES RF - HVAC vendor strategies.

Vendor-specific behaviour for HVAC ventilation systems.  Each
strategy owns its vendor's fan mode maps, payload quirks, binding
codes, and classification heuristics.

See :doc:`roadmap item 5 <https://github.com/ramses-rf/ramses_rf/issues/1093>`.
"""

from __future__ import annotations

from ramses_rf.strategies.base import HvacStrategy, HvacStrategyBase
from ramses_rf.strategies.itho import IthoStrategy
from ramses_rf.strategies.nuaire import NuaireStrategy
from ramses_rf.strategies.orcon import OrconStrategy
from ramses_rf.strategies.vasco import VascoStrategy

__all__ = [
    "HvacStrategy",
    "HvacStrategyBase",
    "IthoStrategy",
    "NuaireStrategy",
    "OrconStrategy",
    "VascoStrategy",
]

#: Strategy classes indexed by scheme name
_STRATEGY_BY_SCHEME: dict[str, type[HvacStrategyBase]] = {
    "orcon": OrconStrategy,
    "itho": IthoStrategy,
    "nuaire": NuaireStrategy,
    "vasco": VascoStrategy,
}
