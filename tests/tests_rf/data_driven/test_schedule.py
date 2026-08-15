#!/usr/bin/env python3
"""RAMSES RF - Test the Schedule functions and FSM state machine."""

import json
from copy import deepcopy
from pathlib import Path, PurePath
from typing import Final
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ramses_rf import exceptions as exc
from ramses_rf.const import SZ_SCHEDULE, SZ_ZONE_IDX, SZ_ZONE_INDEX, Code
from ramses_rf.messages import Message
from ramses_rf.models import ScheduleState, StateUpdatedEvent
from ramses_rf.payloads.heating import ScheduleSwitchpointPayload
from ramses_rf.systems.schedule import (
    SZ_ENABLED,
    SZ_HEAT_SETPOINT,
    SZ_SWITCHPOINTS,
    SZ_TIME_OF_DAY,
    DaySchedule,
    Schedule,
    ScheduleData,
    ScheduleIsFaulted,
    ScheduleIsIdle,
    ScheduleIsStale,
    ScheduleIsSynchronised,
    ScheduleStateEnum,
    Switchpoint,
    fragments_to_full_schedule,
    full_schedule_to_fragments,
)
from ramses_rf.typing import WeeklyScheduleDict

from .helpers import TEST_DIR

WORK_DIR = f"{TEST_DIR}/schedules"

VALID_FULL_SCHEDULE: Final[WeeklyScheduleDict] = {
    SZ_ZONE_IDX: "00",
    SZ_SCHEDULE: [
        {
            "day_of_week": 0,
            SZ_SWITCHPOINTS: [{SZ_TIME_OF_DAY: "06:00", SZ_HEAT_SETPOINT: 21.0}],
        }
    ],
}
VALID_FRAGMENT_HEX: Final[str] = full_schedule_to_fragments(VALID_FULL_SCHEDULE)[0]


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    def id_fnc(param: Path) -> str:
        return PurePath(param).name

    if "dir_name" in metafunc.fixturenames:
        folders = [
            f for f in Path(WORK_DIR).iterdir() if f.is_dir() and f.name[:1] != "_"
        ]
        metafunc.parametrize("dir_name", folders, ids=id_fnc)


async def test_schedule_helpers(dir_name: Path) -> None:
    """Compare the schedule helpers are consistent and have symmetry."""

    # Arrange
    with open(f"{dir_name}/schedule.json") as f:
        schedule = json.load(f)

    new_schedule = deepcopy(schedule)

    # Act & Assert
    if "zone_idx" in schedule:
        schedule[SZ_ZONE_INDEX] = schedule.pop("zone_idx")
    if "zone_idx" in new_schedule:
        new_schedule[SZ_ZONE_INDEX] = new_schedule.pop("zone_idx")

    ScheduleData.from_dict(schedule)
    if schedule[SZ_ZONE_INDEX] == "HW":
        schedule[SZ_ZONE_INDEX] = "00"

    assert schedule == fragments_to_full_schedule(full_schedule_to_fragments(schedule))

    if new_schedule[SZ_ZONE_INDEX] == "HW":
        new_schedule[SZ_ZONE_INDEX] = "00"
        new_schedule[SZ_SCHEDULE][-1][SZ_SWITCHPOINTS][-1][SZ_ENABLED] = not (
            schedule[SZ_SCHEDULE][-1][SZ_SWITCHPOINTS][-1][SZ_ENABLED]
        )
    else:
        new_schedule[SZ_SCHEDULE][-1][SZ_SWITCHPOINTS][-1][SZ_HEAT_SETPOINT] = (
            schedule[SZ_SCHEDULE][-1][SZ_SWITCHPOINTS][-1][SZ_HEAT_SETPOINT] + 1
        )

    # The schedule code relies upon the following inequality...
    # i.e. if the schedule has changed, then the first fragment will be different
    assert (
        full_schedule_to_fragments(new_schedule)[0]
        != (full_schedule_to_fragments(schedule)[0])
    )


@pytest.mark.asyncio
async def test_schedule_fsm_initial_state() -> None:
    """Verify that Schedule initializes in ScheduleIsIdle state."""

    # Arrange
    mock_zone = MagicMock()
    mock_zone.id = "01:123456_00"
    mock_zone.idx = "00"

    # Act
    sched = Schedule(mock_zone)

    # Assert
    assert sched.state == ScheduleStateEnum.IDLE
    assert isinstance(sched._state, ScheduleIsIdle)


@pytest.mark.asyncio
async def test_schedule_fsm_fetch_state_transitions() -> None:
    """Verify state transitions during a successful schedule fetch."""

    # Arrange
    mock_zone = MagicMock()
    mock_zone.id = "01:123456_00"
    mock_zone.idx = "00"

    sched = Schedule(mock_zone)

    # Act & Assert
    with (
        patch.object(
            sched.tcs, "_schedule_version", new=AsyncMock(return_value=(1, True))
        ),
        patch.object(
            sched,
            "_fetch_fragment",
            new=AsyncMock(
                return_value={
                    "zone_idx": "00",
                    "frag_number": 1,
                    "total_frags": 1,
                    "fragment": VALID_FRAGMENT_HEX,
                }
            ),
        ),
    ):
        await sched.get_schedule(force_io=True)

    assert sched.state == ScheduleStateEnum.SYNCHRONISED
    assert isinstance(sched._state, ScheduleIsSynchronised)


@pytest.mark.asyncio
async def test_schedule_fsm_fetch_exponential_backoff() -> None:
    """Verify exponential backoff sleep occurs on fragment fetch retries."""

    # Arrange
    mock_zone = MagicMock()
    mock_zone.id = "01:123456_00"
    mock_zone.idx = "00"

    sched = Schedule(mock_zone)

    # Fail once with TimeoutError, then succeed with a valid fragment
    mock_fetch = AsyncMock(
        side_effect=[
            TimeoutError("Mock timeout"),
            {
                "zone_idx": "00",
                "frag_number": 1,
                "total_frags": 1,
                "fragment": VALID_FRAGMENT_HEX,
            },
        ]
    )

    # Act & Assert
    with (
        patch.object(
            sched.tcs, "_schedule_version", new=AsyncMock(return_value=(1, True))
        ),
        patch.object(sched, "_fetch_fragment", new=mock_fetch),
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        await sched.get_schedule(force_io=True)

    mock_sleep.assert_called_once_with(0.5)
    assert sched.state == ScheduleStateEnum.SYNCHRONISED


@pytest.mark.asyncio
async def test_schedule_fsm_max_attempts_fault() -> None:
    """Verify transition to ScheduleIsFaulted when max attempts fail."""

    # Arrange
    mock_zone = MagicMock()
    mock_zone.id = "01:123456_00"
    mock_zone.idx = "00"

    sched = Schedule(mock_zone)

    # Act & Assert
    with (
        patch.object(
            sched.tcs, "_schedule_version", new=AsyncMock(return_value=(1, True))
        ),
        patch.object(
            sched,
            "_fetch_fragment",
            new=AsyncMock(side_effect=TimeoutError("Mock timeout")),
        ),
        patch("asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(exc.ScheduleFlowError),
    ):
        await sched.get_schedule(force_io=True)

    assert sched.state == ScheduleStateEnum.FAULTED
    assert isinstance(sched._state, ScheduleIsFaulted)


@pytest.mark.asyncio
async def test_schedule_handle_msg_version_change() -> None:
    """Verify version 0006 packet transitions state from SYNCHRONISED to STALE."""

    # Arrange
    mock_zone = MagicMock()
    mock_zone.id = "01:123456_00"
    mock_zone.idx = "00"

    sched = Schedule(mock_zone)
    sched._set_state(ScheduleIsSynchronised)
    sched._schedule_version = 1

    mock_msg = MagicMock(spec=Message)
    mock_msg.code = Code._0006
    mock_msg.payload = {"change_counter": 2}

    # Act
    sched.process_schedule_msg(mock_msg)

    # Assert
    assert sched.state == ScheduleStateEnum.STALE
    assert isinstance(sched._state, ScheduleIsStale)


@pytest.mark.asyncio
async def test_schedule_apply_state_update_cqrs() -> None:
    """Verify state update event hydrates zone.schedule_state directly."""

    # Arrange
    mock_zone = MagicMock()
    mock_zone.id = "01:123456_00"
    mock_zone.idx = "00"
    mock_zone.schedule_state = None

    sched = Schedule(mock_zone)
    mock_state = MagicMock(spec=ScheduleState)
    mock_event = MagicMock(spec=StateUpdatedEvent)
    mock_event.state = mock_state

    # Act
    sched.apply_state_update(mock_event)

    # Assert
    assert mock_zone.schedule_state == mock_state


def test_switchpoint_dataclass_valid() -> None:
    """Verify valid Switchpoint dataclass creation and invariants."""
    # Arrange & Act
    sp1 = Switchpoint(time_of_day="06:00", heat_setpoint=21.0)
    sp2 = Switchpoint(time_of_day="22:30", enabled=True)

    # Assert
    assert sp1.time_of_day == "06:00"
    assert sp1.heat_setpoint == 21.0
    assert sp1.enabled is None

    assert sp2.time_of_day == "22:30"
    assert sp2.heat_setpoint is None
    assert sp2.enabled is True

    # Immutability
    with pytest.raises(AttributeError):
        sp1.heat_setpoint = 22.0  # type: ignore[misc]


def test_switchpoint_dataclass_invalid() -> None:
    """Verify Switchpoint validation errors for invalid times and setpoints."""
    # Invalid time formats
    with pytest.raises(ValueError, match="Invalid time format"):
        Switchpoint(time_of_day="25:00", heat_setpoint=21.0)

    with pytest.raises(ValueError, match="Invalid time format"):
        Switchpoint(time_of_day="6:00", heat_setpoint=21.0)

    # 5-minute quantization constraint
    with pytest.raises(ValueError, match="must be in 5-minute intervals"):
        Switchpoint(time_of_day="06:03", heat_setpoint=21.0)

    # Out of range setpoint
    with pytest.raises(ValueError, match="Out of range heat_setpoint"):
        Switchpoint(time_of_day="06:00", heat_setpoint=4.0)

    with pytest.raises(ValueError, match="Out of range heat_setpoint"):
        Switchpoint(time_of_day="06:00", heat_setpoint=36.0)


def test_day_schedule_dataclass_validation() -> None:
    """Verify DaySchedule validation for day of week and switchpoint array."""
    sp = Switchpoint(time_of_day="06:00", heat_setpoint=21.0)

    # Valid DaySchedule
    day_sched = DaySchedule(day_of_week=0, switchpoints=(sp,))
    assert day_sched.day_of_week == 0

    # Invalid day of week (< 0 or > 6)
    with pytest.raises(ValueError, match="Invalid day_of_week"):
        DaySchedule(day_of_week=7, switchpoints=(sp,))

    with pytest.raises(ValueError, match="Invalid day_of_week"):
        DaySchedule(day_of_week=-1, switchpoints=(sp,))

    # Empty switchpoints
    with pytest.raises(ValueError, match="cannot be empty"):
        DaySchedule(day_of_week=0, switchpoints=())


def test_schedule_data_dataclass_validation_and_dict_conversion() -> None:
    """Verify ScheduleData validation, from_dict parsing, and to_dict serialization."""
    raw_schedule = {
        SZ_ZONE_IDX: "HW",
        SZ_SCHEDULE: [
            {
                "day_of_week": 0,
                SZ_SWITCHPOINTS: [{SZ_TIME_OF_DAY: "06:00", SZ_ENABLED: True}],
            }
        ],
    }

    # Act
    sched_data = ScheduleData.from_dict(raw_schedule)

    # Assert
    assert sched_data.zone_index == "HW"
    assert len(sched_data.days) == 1
    assert sched_data.days[0].day_of_week == 0
    assert sched_data.days[0].switchpoints[0].enabled is True

    # Round-trip serialization
    serialized = sched_data.to_dict()
    assert serialized[SZ_ZONE_IDX] == "HW"
    sp_dict = serialized[SZ_SCHEDULE][0][SZ_SWITCHPOINTS][0]
    assert isinstance(sp_dict, dict)
    assert sp_dict.get(SZ_ENABLED) is True

    # Invalid zone index
    with pytest.raises(ValueError, match="Invalid zone_index"):
        ScheduleData(zone_index="INVALID", days=sched_data.days)


def test_schedule_switchpoint_payload_from_switchpoint() -> None:
    """Verify ScheduleSwitchpointPayload.from_switchpoint factory method."""
    # Zone switchpoint
    sp1 = ScheduleSwitchpointPayload.from_switchpoint(
        zone_index="01",
        day_of_week=0,
        time_of_day_mins=360,
        setpoint=21.0,
    )
    assert sp1.zone_index == 1
    assert sp1.day_of_week == 0
    assert sp1.time_of_day_mins == 360
    assert sp1.setpoint_value == 2100

    # DHW switchpoint
    sp2 = ScheduleSwitchpointPayload.from_switchpoint(
        zone_index="HW",
        day_of_week=1,
        time_of_day_mins=480,
        setpoint=True,
    )
    assert sp2.zone_index == 0xFA
    assert sp2.day_of_week == 1
    assert sp2.time_of_day_mins == 480
    assert sp2.setpoint_value == 1
