"""RAMSES RF - Vasco HVAC strategy.

Vendor-specific behaviour for Vasco D60 and ClimaRad Minibox
ventilation systems.
"""

from __future__ import annotations

from ramses_rf.strategies.base import HvacStrategyBase
from ramses_tx.const import Code


class VascoStrategy(HvacStrategyBase):
    """Strategy for Vasco D60 and ClimaRad Minibox remotes."""

    scheme = "vasco"
    _mode_map = {
        "00": "off",
        "01": "away",
        "02": "low",
        "03": "medium",
        "04": "high",
        "05": "auto",
    }
    _mode_max = "06"
    _binding_codes = (Code._22F1, Code._22F3)
