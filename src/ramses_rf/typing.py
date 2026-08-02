"""RAMSES RF - Domain-specific type definitions."""

from datetime import timedelta as td
from typing import Any, NotRequired, TypeAlias, TypedDict

from ramses_tx.typing import DeviceIdT as TxDeviceIdT, DevIndexT as TxIndexT

DeviceIdT: TypeAlias = TxDeviceIdT
DevIndexT: TypeAlias = TxIndexT
IndexT: TypeAlias = TxIndexT

DeviceTraitsT: TypeAlias = dict[str, Any]
DeviceListT: TypeAlias = dict[str, DeviceTraitsT]
PollingIntervalsT: TypeAlias = dict[str, int]

# Domain Payload Type Aliases
HvacPayloadT: TypeAlias = dict[str, Any]
OpenThermPayloadT: TypeAlias = dict[str, Any]
HeatingPayloadT: TypeAlias = dict[str, Any]


# For fingerprints.py
class DeviceFingerprint(TypedDict):
    """Device fingerprint metadata for entity identification."""

    slug: str
    dev_type: str
    date: str
    desc: str


# CODES_SCHEMA entries
CodeSchemaEntry = TypedDict(
    "CodeSchemaEntry",
    {
        "name": str,
        " I": str,  # Regex
        "RQ": str,  # Regex
        "RP": str,  # Regex
        " W": str,  # Regex
        "lifespan": bool | td | None,
    },
    total=False,
)


# Schedule domain types
class EmptyDictT(TypedDict):
    """An empty typed dictionary used as a sentinel."""

    pass


class SwitchPointDhw(TypedDict):
    """A dictionary representing a DHW switchpoint."""

    time_of_day: str
    enabled: bool


class SwitchPointZon(TypedDict):
    """A dictionary representing a zone heating switchpoint."""

    time_of_day: str
    heat_setpoint: float


SwitchPointT: TypeAlias = SwitchPointDhw | SwitchPointZon
SwitchPointsT: TypeAlias = list[SwitchPointT]


class DayOfWeek(TypedDict):
    """A dictionary representing a schedule for a single day."""

    day_of_week: int
    switchpoints: SwitchPointsT


DayOfWeekT: TypeAlias = DayOfWeek
InnerScheduleT: TypeAlias = list[DayOfWeek]


class OuterSchedule(TypedDict):
    """A dictionary representing a full schedule payload."""

    zone_idx: str
    schedule: InnerScheduleT


class EmptySchedule(TypedDict):
    """A dictionary representing an empty schedule payload."""

    zone_idx: str
    schedule: NotRequired[EmptyDictT | None]


OuterScheduleT: TypeAlias = OuterSchedule | EmptySchedule

PayloadT: TypeAlias = dict[str, Any]
PayloadSetT: TypeAlias = list[PayloadT | None]

FragmentT: TypeAlias = str
FragmentSetT: TypeAlias = list[FragmentT]
