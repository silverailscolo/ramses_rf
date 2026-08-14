"""RAMSES RF - Dataclass to Legacy Dictionary Adapter.

This module provides serialization utilities to convert typed PayloadBase instances
into legacy dictionary formats for parity testing and backward compatibility.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from .base import PayloadBase


# Map internal Pythonic dataclass field names to legacy dictionary schema keys
_FIELD_TO_LEGACY_KEY: dict[str, str] = {
    "dhw_index": "dhw_idx",
    "zone_index": "zone_idx",
    "zone_index_raw": "zone_idx_raw",
    "sub_index": "sub_idx",
    "domain_index": "domain_idx",
    "domain_or_zone_index": "domain_or_zone_idx",
    "ot_index": "ot_idx",
    "opentherm_index": "ot_idx",
    "mod_index": "mod_idx",
    "modulation_index": "mod_idx",
    "capacity_index": "capacity_idx",
    "capacity_value": "capacity_val",
    "fault_index": "fault_idx",
    "mode_index": "mode_idx",
    "day_index": "day_idx",
    "setpoint_index": "setpoint_idx",
    "log_index": "log_idx",
    "config_index": "config_idx",
    "config_value": "config_val",
    "flag_value": "flag_val",
    "mode_value": "mode_val",
    "parameter_index": "param_idx",
    "parameter_value": "param_val",
    "parameter_id": "param_id",
    "min_value_scaled": "min_val_scaled",
    "max_value_scaled": "max_val_scaled",
    "request_reason": "req_reason",
    "is_daylight_saving": "is_dst",
    "_hvac_index": "_hvac_idx",
    "ufh_index": "ufh_idx",
}


def payload_to_dict(payload: PayloadBase, *, legacy: bool = False) -> dict[str, Any]:
    """Convert a PayloadBase instance into a dictionary structure.

    :param payload: The payload dataclass instance to convert.
    :type payload: PayloadBase
    :param legacy: If True, translate field names to legacy abbreviated keys.
    :type legacy: bool
    :returns: Dictionary representation of the payload attributes.
    :rtype: dict[str, Any]
    :raises TypeError: If the input is not a dataclass instance.
    """
    if not is_dataclass(cast(object, payload)):
        err_msg = f"Expected dataclass instance, got {type(payload).__name__}"
        raise TypeError(err_msg)
    if legacy:
        return {
            _FIELD_TO_LEGACY_KEY.get(k, k): v
            for k, v in asdict(payload).items()
            if not k.startswith("_")
        }
    return {k: v for k, v in asdict(payload).items() if not k.startswith("_")}
