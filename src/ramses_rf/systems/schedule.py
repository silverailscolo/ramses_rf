#!/usr/bin/env python3
"""RAMSES RF - Expose an 0404 schedule (is a stateful process)."""

from __future__ import annotations

import asyncio
import logging
import zlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import time as dtm_time
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final, Self

from ramses_rf import exceptions as exc
from ramses_rf.const import (
    SZ_FRAGMENT,
    SZ_FRAGMENT_NUMBER,
    SZ_SCHEDULE,
    SZ_TOTAL_FRAGMENTS,
    SZ_ZONE_IDX,
    SZ_ZONE_INDEX,
)
from ramses_rf.messages import Message
from ramses_rf.models import ScheduleState, StateUpdatedEvent
from ramses_rf.payloads.heating import ScheduleSwitchpointPayload
from ramses_rf.typing import (
    DayOfWeek,
    EmptyDictT,
    EmptySchedule,
    FragmentSetT,
    FragmentT,
    PayloadSetT,
    PayloadT,
    SwitchPointDhw,
    SwitchPointT,
    SwitchPointZon,
    WeeklySchedule,
    WeeklyScheduleDict,
)
from ramses_tx.exceptions import ProtocolSendFailed

from ..enums import Action
from .helpers import send_system_intent

if TYPE_CHECKING:
    from ramses_rf.systems.zones import DhwZone, Zone


# Constants
SZ_DAY_OF_WEEK: Final = "day_of_week"

SZ_HEAT_SETPOINT: Final = "heat_setpoint"
SZ_SWITCHPOINTS: Final = "switchpoints"
SZ_TIME_OF_DAY: Final = "time_of_day"
SZ_ENABLED: Final = "enabled"

SWITCHPOINT_STRUCT_SIZE: Final = 20
FRAGMENT_HEX_LENGTH: Final = 82


_LOGGER = logging.getLogger(__name__)


# Base retry constants for exponential backoff
BASE_FETCH_RETRY_DELAY_SECS: Final[float] = 0.5
MAX_FETCH_ATTEMPTS: Final[int] = 5


class ScheduleStateEnum(StrEnum):
    """Enumeration of schedule finite state machine states."""

    IDLE = "idle"
    FETCHING = "fetching"
    UPDATING = "updating"
    SYNCHRONISED = "synchronised"
    STALE = "stale"
    FAULTED = "faulted"


class ScheduleStateBase:
    """Base class for schedule finite state machine phases."""

    state_enum: ScheduleStateEnum = ScheduleStateEnum.IDLE

    def __init__(self, schedule: Schedule) -> None:
        """Initialise the schedule state phase.

        :param schedule: The parent Schedule state manager.
        :type schedule: Schedule
        """
        self._schedule = schedule

    def __str__(self) -> str:
        """Return the string representation of the state phase."""
        return self.state_enum.value


class ScheduleIsIdle(ScheduleStateBase):
    """Schedule is idle and not interacting with the network."""

    state_enum = ScheduleStateEnum.IDLE


class ScheduleIsFetching(ScheduleStateBase):
    """Schedule is actively fetching missing fragments from network."""

    state_enum = ScheduleStateEnum.FETCHING


class ScheduleIsUpdating(ScheduleStateBase):
    """Schedule is actively writing fragments to the controller."""

    state_enum = ScheduleStateEnum.UPDATING


class ScheduleIsSynchronised(ScheduleStateBase):
    """Schedule is fully cached and synchronised with controller."""

    state_enum = ScheduleStateEnum.SYNCHRONISED


class ScheduleIsStale(ScheduleStateBase):
    """Schedule cache is stale following a version change."""

    state_enum = ScheduleStateEnum.STALE


class ScheduleIsFaulted(ScheduleStateBase):
    """Schedule subsystem encountered a timeout or fetch error."""

    state_enum = ScheduleStateEnum.FAULTED


@dataclass(frozen=True, slots=True)
class Switchpoint:
    """Individual schedule switchpoint.

    :param time_of_day: 24-hour time string in 'HH:MM' format.
    :type time_of_day: str
    :param heat_setpoint: Target temperature in °C (for zone schedules).
    :type heat_setpoint: float | None
    :param enabled: DHW state flag (for DHW schedules).
    :type enabled: bool | None
    """

    time_of_day: str
    heat_setpoint: float | None = None
    enabled: bool | None = None

    def __post_init__(self) -> None:
        """Validate switchpoint attributes upon instantiation."""
        try:
            t = dtm_time.fromisoformat(self.time_of_day)
        except (ValueError, TypeError) as err:
            raise ValueError(
                f"Invalid time format {self.time_of_day!r}, expected 'HH:MM'"
            ) from err

        if t.minute % 5 != 0 or t.second != 0 or t.microsecond != 0:
            raise ValueError(f"Time {self.time_of_day!r} must be in 5-minute intervals")

        if self.heat_setpoint is not None:
            if not (5.0 <= self.heat_setpoint <= 35.0):
                raise ValueError(f"Out of range heat_setpoint: {self.heat_setpoint}")
        elif self.enabled is None:
            raise ValueError("Switchpoint must define 'heat_setpoint' or 'enabled'")


@dataclass(frozen=True, slots=True)
class DaySchedule:
    """Daily schedule containing switchpoints.

    :param day_of_week: Day of week integer (0-6).
    :type day_of_week: int
    :param switchpoints: Tuple of switchpoints for this day.
    :type switchpoints: tuple[Switchpoint, ...]
    """

    day_of_week: int
    switchpoints: tuple[Switchpoint, ...]

    def __post_init__(self) -> None:
        """Validate day of week and switchpoint array."""
        if not (0 <= self.day_of_week <= 6):
            raise ValueError(f"Invalid day_of_week: {self.day_of_week}")
        if not self.switchpoints:
            raise ValueError("DaySchedule switchpoints list cannot be empty")


@dataclass(frozen=True, slots=True)
class ScheduleData:
    """Complete 7-day schedule for a zone or DHW.

    :param zone_index: Zone or domain index ('00'-'0F' or 'HW').
    :type zone_index: str
    :param days: Tuple of daily schedules.
    :type days: tuple[DaySchedule, ...]
    """

    zone_index: str
    days: tuple[DaySchedule, ...]

    def __post_init__(self) -> None:
        """Validate zone index and day array bounds."""
        if self.zone_index != "HW" and not (
            len(self.zone_index) == 2 and 0 <= int(self.zone_index, 16) <= 15
        ):
            raise ValueError(f"Invalid zone_index: {self.zone_index!r}")
        if len(self.days) > 7:
            raise ValueError(f"Schedule cannot exceed 7 days: {len(self.days)}")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        """Parse raw dictionary into typed ScheduleData dataclass.

        :param data: Raw schedule dictionary representation.
        :type data: Mapping[str, Any]
        :returns: Parsed ScheduleData dataclass instance.
        :rtype: Self
        :raises ValueError: If dictionary structures or values are invalid.
        """
        zone_index = str(
            data.get(SZ_ZONE_INDEX, data.get(SZ_ZONE_IDX, data.get("zone_idx", "")))
        )
        raw_schedule = data.get(SZ_SCHEDULE)
        if not isinstance(raw_schedule, (list, tuple)):
            raise ValueError(f"Invalid schedule structure: {raw_schedule}")

        days: list[DaySchedule] = []
        for day in raw_schedule:
            if not isinstance(day, dict):
                continue
            day_of_week = int(day[SZ_DAY_OF_WEEK])
            raw_switchpoints = day.get(SZ_SWITCHPOINTS)
            if not isinstance(raw_switchpoints, (list, tuple)):
                continue

            switchpoints: list[Switchpoint] = []
            for sp in raw_switchpoints:
                if not isinstance(sp, dict):
                    continue
                time_of_day = str(sp[SZ_TIME_OF_DAY])
                heat_setpoint = sp.get(SZ_HEAT_SETPOINT)
                enabled = sp.get(SZ_ENABLED)
                setpoint_val = (
                    float(heat_setpoint)
                    if isinstance(heat_setpoint, (int, float))
                    else None
                )
                enabled_val = bool(enabled) if isinstance(enabled, bool) else None
                switchpoints.append(
                    Switchpoint(
                        time_of_day=time_of_day,
                        heat_setpoint=setpoint_val,
                        enabled=enabled_val,
                    )
                )

            days.append(
                DaySchedule(day_of_week=day_of_week, switchpoints=tuple(switchpoints))
            )

        return cls(zone_index=zone_index, days=tuple(days))

    def to_dict(self) -> WeeklyScheduleDict:
        """Serialize ScheduleData dataclass back into dictionary layout.

        :returns: Dictionary representation of full schedule.
        :rtype: WeeklyScheduleDict
        """
        schedule: WeeklySchedule = []
        for day in self.days:
            switchpoints: list[SwitchPointDhw | SwitchPointZon] = []
            for sp in day.switchpoints:
                if sp.heat_setpoint is not None:
                    sp_zon: SwitchPointZon = {
                        SZ_TIME_OF_DAY: sp.time_of_day,
                        SZ_HEAT_SETPOINT: sp.heat_setpoint,
                    }
                    switchpoints.append(sp_zon)
                elif sp.enabled is not None:
                    sp_dhw: SwitchPointDhw = {
                        SZ_TIME_OF_DAY: sp.time_of_day,
                        SZ_ENABLED: sp.enabled,
                    }
                    switchpoints.append(sp_dhw)
            day_dict: DayOfWeek = {
                SZ_DAY_OF_WEEK: day.day_of_week,
                SZ_SWITCHPOINTS: switchpoints,
            }
            schedule.append(day_dict)

        return {
            SZ_ZONE_INDEX: self.zone_index,
            SZ_ZONE_IDX: self.zone_index,
            SZ_SCHEDULE: schedule,
        }


def fragments_to_full_schedule(fragments: Iterable[FragmentT]) -> WeeklyScheduleDict:
    """Convert a tuple of fragments strs (a blob) into a schedule.

    :param fragments: An iterable of hexadecimal string fragments.
    :type fragments: Iterable[FragmentT]
    :returns: A parsed WeeklyScheduleDict dictionary representation.
    :rtype: WeeklyScheduleDict
    :raises zlib.error: On invalid payload compression stream.
    """
    raw_schedule = zlib.decompress(bytearray.fromhex("".join(fragments)))

    current_day_of_week = 0
    zone_index = 0
    schedule: WeeklySchedule = []
    switchpoints: list[SwitchPointT] = []

    for i in range(0, len(raw_schedule), SWITCHPOINT_STRUCT_SIZE):
        switchpoint_payload = ScheduleSwitchpointPayload.from_bytes(
            raw_schedule[i : i + SWITCHPOINT_STRUCT_SIZE]
        )
        if not isinstance(switchpoint_payload, ScheduleSwitchpointPayload):
            raise ValueError(
                f"Invalid schedule switchpoint binary block: {raw_schedule[i : i + SWITCHPOINT_STRUCT_SIZE]!r}"
            )

        zone_index = switchpoint_payload.zone_index
        day_of_week = switchpoint_payload.day_of_week
        time_of_day = switchpoint_payload.time_of_day_mins
        value = switchpoint_payload.setpoint_value

        if day_of_week > current_day_of_week:
            schedule.append(
                {SZ_DAY_OF_WEEK: current_day_of_week, SZ_SWITCHPOINTS: switchpoints}
            )
            current_day_of_week, switchpoints = day_of_week, []

        hours, mins = divmod(time_of_day, 60)
        time_str = dtm_time(hour=hours, minute=mins).isoformat(timespec="minutes")
        if value in (0, 1):
            switchpoint_dhw: SwitchPointDhw = {
                SZ_TIME_OF_DAY: time_str,
                SZ_ENABLED: bool(value),
            }
            switchpoints.append(switchpoint_dhw)
        else:
            switchpoint_zone: SwitchPointZon = {
                SZ_TIME_OF_DAY: time_str,
                SZ_HEAT_SETPOINT: value / 100,
            }
            switchpoints.append(switchpoint_zone)

    schedule.append(
        {SZ_DAY_OF_WEEK: current_day_of_week, SZ_SWITCHPOINTS: switchpoints}
    )
    return {
        SZ_ZONE_INDEX: f"{zone_index:02X}",
        SZ_ZONE_IDX: f"{zone_index:02X}",
        SZ_SCHEDULE: schedule,
    }


def full_schedule_to_fragments(
    full_schedule: WeeklyScheduleDict,
) -> list[FragmentT]:
    """Convert a schedule into a set of fragments (a blob).

    :param full_schedule: The WeeklyScheduleDict dictionary representation.
    :type full_schedule: WeeklyScheduleDict
    :returns: A list of hexadecimal string fragments.
    :rtype: list[FragmentT]
    :raises KeyError: If expected keys are missing from the structure.
    """
    compressor = zlib.compressobj(level=9, wbits=14)
    fragments: list[bytes] = []

    schedule_data = ScheduleData.from_dict(full_schedule)
    zone_index = (
        int(schedule_data.zone_index, 16) if schedule_data.zone_index != "HW" else 0xFA
    )
    for day in schedule_data.days:
        for switchpoint in day.switchpoints:
            parsed_time = dtm_time.fromisoformat(switchpoint.time_of_day)
            time_of_day_mins = parsed_time.hour * 60 + parsed_time.minute
            setpoint = (
                switchpoint.heat_setpoint
                if switchpoint.heat_setpoint is not None
                else switchpoint.enabled
            )
            switchpoint_payload = ScheduleSwitchpointPayload.from_switchpoint(
                zone_index=zone_index,
                day_of_week=day.day_of_week,
                time_of_day_mins=time_of_day_mins,
                setpoint=setpoint,
            )
            fragments.append(switchpoint_payload.to_bytes())

    blob = (
        (
            b"".join(compressor.compress(fragment) for fragment in fragments)
            + compressor.flush()
        )
        .hex()
        .upper()
    )

    return [
        blob[i : i + FRAGMENT_HEX_LENGTH]
        for i in range(0, len(blob), FRAGMENT_HEX_LENGTH)
    ]


def _to_protocol_zone_idx(zone_index: str) -> str:
    """Translate domain zone index string to RAMSES RF protocol index.

    DHW uses domain identifier 'HW' externally, which translates to '00' in protocol.

    :param zone_index: Domain zone index string ('HW' or '00'-'0F').
    :type zone_index: str
    :returns: RAMSES RF protocol zone index ('00'-'0F').
    :rtype: str
    """
    return "00" if zone_index == "HW" else zone_index


class Schedule:  # 0404
    """The schedule state manager for a heating or DHW zone."""

    def __init__(self, zone: DhwZone | Zone) -> None:
        """Initialize the Schedule for a specific zone.

        :param zone: The heating or DHW zone this schedule applies to.
        :type zone: DhwZone | Zone
        """
        _LOGGER.debug("Schedule(zon=%s).__init__()", zone)

        self.id = zone.id
        self._zone = zone
        self.idx = zone.idx

        self.ctl = zone.ctl
        self.tcs = zone.tcs
        self._gateway = zone._gateway

        self._full_schedule: WeeklyScheduleDict | EmptySchedule | EmptyDictT = {}

        self._payload_set: PayloadSetT = [None]  # Rx'd
        self._fragments: FragmentSetT = []  # to Tx

        self._global_version = 0  # None is a sentinel for 'dont know'
        self._schedule_version = (
            0  # the global_version when this schedule was retrieved
        )

        self._state: ScheduleStateBase = ScheduleIsIdle(self)
        self._sync_event: asyncio.Event = asyncio.Event()

    def __str__(self) -> str:
        """Return a human-readable representation of the schedule."""
        return f"{self._zone} (schedule)"

    @property
    def state(self) -> ScheduleStateEnum:
        """Return the current FSM state phase.

        :returns: Current state phase enum value.
        :rtype: ScheduleStateEnum
        """
        return self._state.state_enum

    def _set_state(self, state_cls: type[ScheduleStateBase]) -> None:
        """Transition the schedule state machine to a new phase.

        :param state_cls: State class to instantiate and transition to.
        :type state_cls: type[ScheduleStateBase]
        """
        old_state = self._state
        self._state = state_cls(self)
        _LOGGER.debug("%s: FSM transition %s -> %s", self, old_state, self._state)

        if isinstance(self._state, ScheduleIsSynchronised):
            self._sync_event.set()
        else:
            self._sync_event.clear()

    def process_schedule_msg(self, msg: Message) -> None:
        """Handle incoming 0404/0006 schedule packets reactively.

        :param msg: Incoming protocol message object.
        :type msg: Message
        """
        if msg.code == "0006":
            if isinstance(msg.payload, dict):
                change_counter = msg.payload.get("change_counter")
                if (
                    isinstance(change_counter, int)
                    and change_counter > self._schedule_version
                ):
                    self._global_version = change_counter
                    if isinstance(self._state, ScheduleIsSynchronised):
                        self._set_state(ScheduleIsStale)
            return

        if msg.code != "0404":
            return

        payload = msg.payload
        if not isinstance(payload, dict):
            return

        pkt_zone_idx = payload.get(
            SZ_ZONE_INDEX, payload.get(SZ_ZONE_IDX, payload.get("zone_idx"))
        )
        if pkt_zone_idx is not None:
            translated_idx = _to_protocol_zone_idx(self.idx)
            if pkt_zone_idx != translated_idx and pkt_zone_idx != self.idx:
                return

        try:
            self._payload_set = self._update_payload_set(self._payload_set, payload)
        except exc.ScheduleError as err:
            _LOGGER.warning(
                "%s: Dropped corrupted schedule fragments: %s",
                self,
                err,
            )
            self._payload_set = [None]
            self._set_state(ScheduleIsFaulted)

    def apply_state_update(self, event: StateUpdatedEvent) -> None:
        """Incorporate a state update event into the read-model.

        :param event: State updated event carrying new ScheduleState.
        :type event: StateUpdatedEvent
        """
        if isinstance(event.state, ScheduleState):
            if hasattr(self._zone, "schedule_state"):
                self._zone.schedule_state = event.state

    async def _is_dated(self, *, force_io: bool = False) -> tuple[bool, bool]:
        """Indicate if a more recent schedule might be available.

        If required, retrieve the latest global version (change counter)
        from the TCS.

        There may be a false positive if another zone's schedule is
        changed when this zone's schedule has not. There may be a false
        negative if this zone's schedule was changed only very recently
        and a cached global version was used.

        If `force_io`, then a true negative is guaranteed (it forces an
        RQ|0006 unless self._global_version > self._schedule_version).

        :param force_io: True to force an I/O request to check versions.
        :type force_io: bool
        :returns: A tuple of (is_dated, did_io).
        :rtype: tuple[bool, bool]
        """
        # this will not cause an I/O...
        if (
            not force_io
            and not self._schedule_version
            or (self._global_version and self._global_version > self._schedule_version)
        ):
            return True, False  # is_dated, did_io

        # this may cause an I/O...
        self._global_version, did_io = await self.tcs._schedule_version()
        if did_io or self._global_version > self._schedule_version:
            return (
                self._global_version > self._schedule_version,
                did_io,
            )  # is_dated, did_io

        if force_io:  # this will cause an I/O...
            self._global_version, did_io = await self.tcs._schedule_version(
                force_io=force_io
            )

        return (
            self._global_version > self._schedule_version,
            did_io,
        )  # is_dated, did_io

    async def get_schedule(
        self, *, force_io: bool = False, timeout: float = 15
    ) -> WeeklySchedule | None:
        """Retrieve/return the brief schedule of a zone.

        Return the cached schedule (which may have been eavesdropped)
        only if the global change counter has not increased. Otherwise,
        RQ the latest schedule from the controller and return that.

        If `force_io`, then the latest schedule is guaranteed (it forces
        an RQ|0006).

        :param force_io: Set to True to force fetching a new schedule.
        :type force_io: bool
        :param timeout: Maximum time in seconds to wait for the schedule.
        :type timeout: float
        :returns: The schedule details or None if not available.
        :rtype: WeeklySchedule | None
        :raises exc.ScheduleFlowError: If unable to obtain the schedule
            before timeout.
        """
        try:
            await asyncio.wait_for(
                self._get_schedule(force_io=force_io), timeout=timeout
            )
        except TimeoutError as err:
            self._set_state(ScheduleIsFaulted)
            raise exc.ScheduleFlowError(
                f"Failed to obtain schedule within {timeout} secs"
            ) from err
        except ProtocolSendFailed:
            # Silently drop the background request if the transport is
            # inactive (e.g., during cache restoration prior to gateway
            # startup).
            _LOGGER.debug("%s: Dropped request: gateway transport is inactive.", self)
            return None

        return self.schedule

    async def _fetch_fragment(self, frag_num: int) -> PayloadT:
        """Fetch a single schedule fragment from the controller.

        :param frag_num: The 1-based index of the fragment to fetch.
        :type frag_num: int
        :returns: The dictionary payload of the fragment response.
        :rtype: PayloadT
        """
        frag_set_size = 0 if frag_num == 1 else len(self._payload_set)
        msg: Message = await send_system_intent(
            self,
            Action.GET_SCHEDULE_FRAGMENT,
            data={
                SZ_ZONE_INDEX: self.idx,
                SZ_FRAGMENT_NUMBER: frag_num,
                SZ_TOTAL_FRAGMENTS: frag_set_size,
            },
            wait_for_reply=True,
        )
        assert isinstance(msg.payload, dict)  # mypy check
        return msg.payload  # may: TimeoutError?

    async def _fetch_schedule(self) -> None:
        """Fetch missing schedule fragments using exponential backoff retries.

        :raises exc.ScheduleFlowError: If max fetch attempts are exceeded.
        """
        self._set_state(ScheduleIsFetching)
        attempts = 0
        backoff = BASE_FETCH_RETRY_DELAY_SECS

        while None in self._payload_set:
            attempts += 1
            if attempts > MAX_FETCH_ATTEMPTS:
                self._set_state(ScheduleIsFaulted)
                raise exc.ScheduleFlowError(
                    f"Exceeded max fragment fetch attempts for zone {self.idx}"
                )

            frag_num = next(
                (i for i, f in enumerate(self._payload_set, 1) if f is None),
                1,
            )

            try:
                fragment = await self._fetch_fragment(frag_num)
                # next line also in self._handle_msg(), so protected there
                self._payload_set = self._update_payload_set(
                    self._payload_set, fragment
                )
            except (TimeoutError, exc.ScheduleError, ProtocolSendFailed) as err:
                _LOGGER.warning(
                    "%s: Fragment %s fetch retry %s failed: %s",
                    self,
                    frag_num,
                    attempts,
                    err,
                )
                await asyncio.sleep(backoff)
                backoff *= 2

        self._schedule_version = self._global_version
        self._set_state(ScheduleIsSynchronised)

    async def _get_schedule(self, *, force_io: bool = False) -> None:
        """Retrieve/return the schedule of a zone and sets `self._full_schedule`.

        :param force_io: Set to True to force network fetching.
        :type force_io: bool
        """
        is_dated, did_io = await self._is_dated(force_io=force_io)
        if is_dated:
            self._full_schedule = {}  # keep frags, maybe only other scheds have changed

        if self._full_schedule and isinstance(self._state, ScheduleIsSynchronised):
            return

        if not did_io:  # must know the version of the schedule about to be RQ'd
            self._global_version, _ = await self.tcs._schedule_version(force_io=True)

        self._payload_set[0] = None  # if 1st frag valid: schedule very likely unchanged

        await self._fetch_schedule()

    def _proc_payload_set(
        self, payload_set: PayloadSetT
    ) -> WeeklyScheduleDict | EmptySchedule | None:
        """Process a payload set and return the full schedule.

        Sets `self._full_schedule`. If the schedule is for DHW, set the
        `zone_index` key to 'HW' (to avoid confusing with zone '00').

        :param payload_set: The completed array of fragment payloads.
        :type payload_set: PayloadSetT
        :returns: The outer schedule dictionary (not `self.schedule`).
        :rtype: WeeklyScheduleDict | EmptySchedule | None

        :raises exc.ScheduleError: On failure to decompress fragment string or
            if the fragment set is incomplete.
        """
        if payload_set == [None]:
            self._full_schedule = {
                SZ_ZONE_INDEX: self.idx,
                SZ_ZONE_IDX: self.idx,
            }
            return self._full_schedule

        if None in payload_set:
            raise exc.ScheduleError(
                "Incomplete schedule fragment payload set provided for decompression"
            )

        try:
            schedule = fragments_to_full_schedule(
                str(payload[SZ_FRAGMENT])
                for payload in payload_set
                if payload and SZ_FRAGMENT in payload
            )
        except zlib.error as err:
            raise exc.ScheduleError("Failed to decompress schedule fragments") from err

        if self.idx == "HW":
            schedule[SZ_ZONE_INDEX] = "HW"
            schedule[SZ_ZONE_IDX] = "HW"
        self._full_schedule = schedule
        self._set_state(ScheduleIsSynchronised)

        return self._full_schedule  # NOTE: not self.schedule

    @staticmethod
    def _init_payload_set(payload: PayloadT) -> PayloadSetT:
        """Initialise a new payload set from a fragment payload.

        :param payload: A fragment payload dictionary.
        :type payload: PayloadT
        :returns: Initialised array for expected fragments.
        :rtype: PayloadSetT
        """
        total_frags = payload.get(SZ_TOTAL_FRAGMENTS, payload.get("total_frags"))
        frag_num = payload.get(SZ_FRAGMENT_NUMBER, payload.get("frag_number"))

        if total_frags is None or frag_num is None:
            return [None]

        new_set: PayloadSetT = [None] * total_frags
        if 0 < frag_num <= total_frags:
            new_set[frag_num - 1] = payload
        return new_set

    def _update_payload_set(
        self, payload_set: PayloadSetT, payload: PayloadT
    ) -> PayloadSetT:
        """Add a fragment to a frag set and process/return the new set.

        If the frag set is complete, check for a schedule (sets
        `self._schedule`). If required, start a new frag set with the
        fragment.

        :param payload_set: Existing fragment collection.
        :type payload_set: PayloadSetT
        :param payload: New payload dictionary to integrate.
        :type payload: PayloadT
        :returns: Updated fragment payload collection.
        :rtype: PayloadSetT
        """
        total_frags = payload.get(SZ_TOTAL_FRAGMENTS, payload.get("total_frags"))
        if total_frags is None:  # zone has no schedule
            payload_set = [None]
            self._proc_payload_set(payload_set)
            return payload_set

        if total_frags != len(payload_set):  # sched has changed
            return self._init_payload_set(payload)

        frag_num = payload.get(SZ_FRAGMENT_NUMBER, payload.get("frag_number"))
        if frag_num is not None and 0 < frag_num <= len(payload_set):
            payload_set[frag_num - 1] = payload

        if None in payload_set or self._proc_payload_set(
            payload_set
        ):  # sets self._schedule
            return payload_set

        return self._init_payload_set(payload)

    async def _send_fragment(
        self, fragment_number: int, total_fragments: int, fragment: str
    ) -> None:
        """Send a schedule fragment to the controller.

        :param fragment_number: Current fragment number (1-based).
        :type fragment_number: int
        :param total_fragments: Total fragment count.
        :type total_fragments: int
        :param fragment: Hexadecimal fragment payload string.
        :type fragment: str
        """
        await send_system_intent(
            self,
            Action.SET_SCHEDULE_FRAGMENT,
            data={
                SZ_ZONE_INDEX: self.idx,
                SZ_FRAGMENT_NUMBER: fragment_number,
                SZ_TOTAL_FRAGMENTS: total_fragments,
                "fragment": fragment,
            },
            wait_for_reply=True,
        )

    def _normalise_and_validate(self, schedule: WeeklySchedule) -> WeeklyScheduleDict:
        """Normalise and validate schedule dictionary structure.

        :param schedule: 7-day schedule array to validate.
        :type schedule: WeeklySchedule
        :returns: Validated WeeklyScheduleDict payload.
        :rtype: WeeklyScheduleDict
        :raises exc.ScheduleError: On validation failure.
        """
        full_schedule: WeeklyScheduleDict = {
            SZ_ZONE_INDEX: self.idx,
            SZ_ZONE_IDX: self.idx,
            SZ_SCHEDULE: schedule,
        }

        try:
            schedule_obj = ScheduleData.from_dict(full_schedule)
            validated = schedule_obj.to_dict()
        except (ValueError, KeyError, TypeError) as err:
            raise exc.ScheduleError(f"failed to set schedule: {err}") from err

        if self.idx == "HW":
            # Translate DHW domain index 'HW' to protocol zone index '00'
            validated[SZ_ZONE_INDEX] = _to_protocol_zone_idx(self.idx)
            validated[SZ_ZONE_IDX] = _to_protocol_zone_idx(self.idx)

        return validated

    async def set_schedule(
        self, schedule: WeeklySchedule, force_refresh: bool = False
    ) -> WeeklySchedule | None:
        """Set the schedule of a zone.

        :param schedule: The array representing the days of the week
            schedule.
        :type schedule: WeeklySchedule
        :param force_refresh: True to query and retrieve the new
            schedule directly after setting.
        :type force_refresh: bool
        :returns: The updated WeeklySchedule array.
        :rtype: WeeklySchedule | None
        :raises exc.ScheduleError: On validation or serialization failure.
        :raises exc.ScheduleFlowError: On transmission timeout.
        """
        full_schedule = self._normalise_and_validate(schedule)
        self._fragments = full_schedule_to_fragments(full_schedule)

        self._set_state(ScheduleIsUpdating)

        try:
            frag_cnt = len(self._fragments)
            for num, frag in enumerate(self._fragments, 1):
                await self._send_fragment(num, frag_cnt, frag)
        except TimeoutError as err:
            self._set_state(ScheduleIsFaulted)
            raise exc.ScheduleFlowError(f"failed to set schedule: {err}") from err
        else:
            if not force_refresh:
                self._global_version, _ = await self.tcs._schedule_version(
                    force_io=True
                )
                self._schedule_version = self._global_version
                self._set_state(ScheduleIsSynchronised)

        if force_refresh:
            await self.get_schedule(force_io=True)  # sets self._full_schedule
        else:
            self._full_schedule = full_schedule

        return self.schedule

    @property
    def schedule(self) -> WeeklySchedule | None:
        """Return the current (not full) schedule, if any.

        :returns: The 7-day schedule array or None.
        :rtype: WeeklySchedule | None
        """
        sched = self._full_schedule.get(SZ_SCHEDULE)
        return sched if isinstance(sched, list) else None

    @property
    def version(self) -> int | None:
        """Return the version associated with the current schedule, if any.

        :returns: The schedule version counter or None.
        :rtype: int | None
        """
        return self._schedule_version if self._full_schedule else None


# 16:27:56.942 000 RQ --- 18:006402 01:145038 --:------ 0006 001 00
# 16:27:56.958 038 RP --- 01:145038 18:006402 --:------ 0006 004 00050009

# 16:27:57.005 000 RQ --- 18:006402 01:145038 --:------ 0404 007 0120000800-0100
# 16:27:57.068 037 RP --- 01:145038 18:006402 --:------ 0404 048 0120000829-0103-68816DCFCB0980301045D1994C3E624916660956604596600516E1D285094112F566F5B80C072222A2
# 16:27:57.114 000 RQ --- 18:006402 01:145038 --:------ 0404 007 0120000800-0203
# 16:27:57.161 038 RP --- 01:145038 18:006402 --:------ 0404 048 0120000829-0203-52DF92C79CEA7EDA91C7F06997FDEFC620B287D6143C054FC153F01C780E3C079E03CFC033F00C3C03
# 16:27:57.202 000 RQ --- 18:006402 01:145038 --:------ 0404 007 0120000800-0303
# 16:27:57.245 038 RP --- 01:145038 18:006402 --:------ 0404 045 0120000826-0303-CF83E7C1F3E079F0CADC3E5E696BFECC944EED5BF5DEAD7AAD45F0227811BCD87937936E24CF
