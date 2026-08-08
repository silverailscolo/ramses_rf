"""RAMSES RF - Dataclass to Legacy Dictionary Adapter.

This module provides serialization utilities to convert typed PayloadBase instances
into legacy dictionary formats for parity testing and backward compatibility.
"""

from dataclasses import asdict, is_dataclass
from typing import Any

from .base import PayloadBase


def payload_to_dict(payload: PayloadBase) -> dict[str, Any]:
    """Convert a PayloadBase instance into a dictionary structure.

    :param payload: The payload dataclass instance to convert.
    :type payload: PayloadBase
    :returns: Dictionary representation of the payload attributes.
    :rtype: dict[str, Any]
    :raises TypeError: If the input is not a dataclass instance.
    """
    if not is_dataclass(payload):
        raise TypeError(f"Expected dataclass instance, got {type(payload).__name__}")
    return asdict(payload)
