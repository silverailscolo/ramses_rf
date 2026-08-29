"""RAMSES RF - Orcon HVAC strategy."""

from __future__ import annotations

from ramses_rf.models.hvac_schemas import _22F1_MODE_MAX, _22F1_MODE_ORCON
from ramses_rf.strategies.base import HvacStrategyBase
from ramses_tx.const import Code


class OrconStrategy(HvacStrategyBase):
    """Strategy for Orcon ventilation systems."""

    scheme = "orcon"
    _mode_map = _22F1_MODE_ORCON
    _mode_max = _22F1_MODE_MAX[scheme]
    _binding_codes = (Code._22F1, Code._22F3)
    _aliases = {
        "afwezig": "away",
        "laag": "low",
        "hoog": "high",
        "uit": "off",
    }
