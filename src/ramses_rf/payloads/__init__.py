"""RAMSES RF - Dataclass Payload Layer package.

This package provides the unified strongly-typed dataclass layer for RAMSES-II
packet payloads.
"""

from .adapters import payload_to_dict
from .base import PayloadBase
from .registry import (
    PAYLOAD_REGISTRY,
    PayloadRegistry,
    get_payload_class,
    register_payload,
)

__all__ = [
    "PAYLOAD_REGISTRY",
    "PayloadBase",
    "PayloadRegistry",
    "get_payload_class",
    "payload_to_dict",
    "register_payload",
]
