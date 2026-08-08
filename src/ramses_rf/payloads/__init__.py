"""RAMSES RF - Dataclass Payload Layer package.

This package provides the unified strongly-typed dataclass layer for RAMSES-II
packet payloads.
"""

from .adapters import payload_to_dict
from .base import PayloadBase
from .heating import (
    BindingPayload,
    DhwTemperaturePayload,
    HeatDemandPayload,
    ScheduleSwitchpointPayload,
    SystemSyncPayload,
    TemperaturePayload,
    ZoneConfigPayload,
)
from .hvac import (
    Co2Payload,
    FanModePayload,
    HvacFanParamPayload,
    RelativeHumidityPayload,
)
from .opentherm import OpenThermMsgPayload
from .registry import (
    PAYLOAD_REGISTRY,
    PayloadRegistry,
    get_payload_class,
    register_payload,
)

__all__ = [
    "PAYLOAD_REGISTRY",
    "BindingPayload",
    "Co2Payload",
    "DhwTemperaturePayload",
    "FanModePayload",
    "HeatDemandPayload",
    "HvacFanParamPayload",
    "OpenThermMsgPayload",
    "PayloadBase",
    "PayloadRegistry",
    "RelativeHumidityPayload",
    "ScheduleSwitchpointPayload",
    "SystemSyncPayload",
    "TemperaturePayload",
    "ZoneConfigPayload",
    "get_payload_class",
    "payload_to_dict",
    "register_payload",
]
