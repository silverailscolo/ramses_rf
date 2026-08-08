"""RAMSES RF - Dataclass Payload Layer package.

This package provides the unified strongly-typed dataclass layer for RAMSES-II
packet payloads.
"""

from .adapters import payload_to_dict
from .base import PayloadBase
from .dhw import DhwConfigPayload, DhwModePayload, DhwStatePayload
from .heating import (
    BindingPayload,
    BoilerRelayDemandPayload,
    DhwTemperaturePayload,
    HeatDemandPayload,
    OutdoorTempPayload,
    ScheduleSwitchpointPayload,
    SetPointInfoPayload,
    SystemSyncPayload,
    TemperaturePayload,
    ZoneConfigPayload,
    ZoneSetpointPayload,
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
    "BoilerRelayDemandPayload",
    "Co2Payload",
    "DhwConfigPayload",
    "DhwModePayload",
    "DhwStatePayload",
    "DhwTemperaturePayload",
    "FanModePayload",
    "HeatDemandPayload",
    "HvacFanParamPayload",
    "OpenThermMsgPayload",
    "OutdoorTempPayload",
    "PayloadBase",
    "PayloadRegistry",
    "RelativeHumidityPayload",
    "ScheduleSwitchpointPayload",
    "SetPointInfoPayload",
    "SystemSyncPayload",
    "TemperaturePayload",
    "ZoneConfigPayload",
    "ZoneSetpointPayload",
    "get_payload_class",
    "payload_to_dict",
    "register_payload",
]
