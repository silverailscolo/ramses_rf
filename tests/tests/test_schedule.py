#!/usr/bin/env python3
"""RAMSES RF - Test the Schedule functions and FSM state machine."""

import json
from copy import deepcopy
from pathlib import Path, PurePath
from typing import Final
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ramses_rf import exceptions as exc
from ramses_rf.const import SZ_SCHEDULE
from ramses_rf.messages import Message
from ramses_rf.models import ScheduleState, StateUpdatedEvent
from ramses_rf.systems.schedule import (
    SCHEMA_SCHEDULE_DHW_OUTER,
    SCHEMA_SCHEDULE_ZONE_OUTER,
    SZ_ENABLED,
    SZ_HEAT_SETPOINT,
    SZ_SWITCHPOINTS,
    SZ_TIME_OF_DAY,
    Schedule,
    ScheduleIsFaulted,
    ScheduleIsIdle,
    ScheduleIsStale,
    ScheduleIsSynchronised,
    ScheduleStateEnum,
    fragments_to_full_schedule,
    full_schedule_to_fragments,
)
from ramses_rf.typing import OuterSchedule
from ramses_tx.const import SZ_ZONE_IDX

from .helpers import TEST_DIR

WORK_DIR = f"{TEST_DIR}/schedules"

VALID_FULL_SCHEDULE: Final[OuterSchedule] = {
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
    if schedule[SZ_ZONE_IDX] == "HW":
        SCHEMA_SCHEDULE_DHW_OUTER(schedule)
        schedule[SZ_ZONE_IDX] = "00"
    else:
        SCHEMA_SCHEDULE_ZONE_OUTER(schedule)

    assert schedule == fragments_to_full_schedule(full_schedule_to_fragments(schedule))

    if new_schedule[SZ_ZONE_IDX] == "HW":
        new_schedule[SZ_ZONE_IDX] = "00"
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
    sched._sched_ver = 1

    mock_msg = MagicMock(spec=Message)
    mock_msg.code = "0006"
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
