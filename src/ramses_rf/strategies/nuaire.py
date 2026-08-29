"""RAMSES RF - Nuaire HVAC strategy.

Vendor-specific behaviour for Nuaire DRI-ECO ventilation systems.
"""

from __future__ import annotations

from ramses_rf.strategies.base import HvacStrategyBase
from ramses_tx.const import Code


class NuaireStrategy(HvacStrategyBase):
    """Strategy for Nuaire DRI-ECO ventilation systems.

    Nuaire uses a single binding code (22F1 only, no 22F3).
    """

    scheme = "nuaire"
    _mode_map = {
        "02": "normal",
        "03": "boost",
        "09": "heater_off",
        "0A": "heater_auto",
    }
    _mode_max = "0A"
    # Nuaire binds with 22F1 only (no 22F3)
    _binding_codes = (Code._22F1,)
