"""RAMSES RF - Layer 7 SSOT-Driven Polling Manager.

Orchestrates periodic polling schedules for network devices based on
Layer 7 Schema-as-Source-of-Truth (SSOT) traits and fallback defaults.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime as dt, timedelta as td
from typing import TYPE_CHECKING, Final

from ramses_rf.const import Code, DevType
from ramses_rf.devices.helpers import build_rq_cmd
from ramses_rf.exceptions import RamsesException
from ramses_rf.helpers import schedule_task
from ramses_rf.typing import DeviceIdT, PollingIntervalsT

if TYPE_CHECKING:
    from ramses_rf.devices.dev_base import DeviceBase
    from ramses_rf.gateway import Gateway

_LOGGER = logging.getLogger(__name__)

INTERVAL_HOURLY: Final[int] = 3600  # 1 hour in seconds
INTERVAL_EVERY_6_HOURS: Final[int] = 21600  # 6 hours in seconds
INTERVAL_EVERY_12_HOURS: Final[int] = 43200  # 12 hours in seconds
INTERVAL_DAILY: Final[int] = 86400  # 24 hours in seconds

# Master default polling schedules table for all device classes.
# Battery-powered devices (TRV, THM, DHW, REM, HUM) set intervals to None
# to explicitly indicate that polling is disabled for those command codes.
DEFAULT_POLLING_SCHEDULES: Final[dict[str, dict[Code | str, int | None]]] = {
    # Evohome Controller
    DevType.CTL: {
        Code._10E0: INTERVAL_DAILY,  # Device Specification / Info
        Code._1F41: INTERVAL_HOURLY,  # DHW System Mode / Operating State
        Code._2E04: INTERVAL_DAILY,  # Evohome System Mode
        Code._313F: INTERVAL_EVERY_12_HOURS,  # System Time & Date Sync
        # 0004 (zone name) is polled per-zone, not per-device — see
        # update_device_tasks for the zone-level expansion.  The interval
        # here is a marker; actual tasks are keyed by (device_id, "0004",
        # zone_idx).  Issue 947: zone names lost after cache clear because
        # the CTL does not broadcast 0004 unless queried.
        Code._0004: INTERVAL_EVERY_6_HOURS,  # Zone Name (per-zone, expanded below)
    },
    # Boiler Relay / Switch
    DevType.BDR: {
        Code._10E0: INTERVAL_DAILY,  # Device Specification / Info
    },
    # OpenTherm Bridge
    DevType.OTB: {
        Code._10E0: INTERVAL_DAILY,  # Device Specification / Info
        Code._3EF0: INTERVAL_HOURLY,  # OpenTherm Modulation State
        Code._3220: INTERVAL_HOURLY,  # OpenTherm Data ID Query
    },
    # Underfloor Heating Controller
    DevType.UFC: {
        Code._10E0: INTERVAL_DAILY,  # Device Specification / Info
        Code._1F09: INTERVAL_HOURLY,  # UFH Controller Status
    },
    # HVAC Ventilation Fan
    DevType.FAN: {
        Code._10E0: INTERVAL_DAILY,  # Device Specification / Info
        Code._10D0: INTERVAL_DAILY,  # Filter Change Sensor Status
        Code._3150: INTERVAL_HOURLY,  # Fan Speed / Airflow Status
    },
    # HVAC Carbon Dioxide Sensor (mains-powered)
    DevType.CO2: {
        Code._10E0: INTERVAL_DAILY,  # Device Specification / Info
    },
    # Battery-Powered Devices - Polling disabled to preserve battery life
    DevType.TRV: {Code._10E0: None, Code._1060: None},
    DevType.THM: {Code._10E0: None, Code._1060: None},
    DevType.DHW: {Code._10E0: None, Code._1060: None},
    DevType.REM: {Code._10E0: None, Code._1060: None},
    DevType.HUM: {Code._10E0: None, Code._1060: None},
    # Fallback Default
    "DEFAULT": {
        Code._10E0: INTERVAL_DAILY,  # Device Specification / Info
    },
}

POLL_INTER_CMD_GAP: Final[float] = (
    0.5  # Rate limit gap between consecutive TX commands
)
DEFAULT_POLL_CYCLE_SECS: Final[float] = 300.0  # 5 minutes maximum idle sleep


def _ensure_aware(dtm: dt) -> dt:
    """Ensure a datetime object is timezone-aware, defaulting to UTC if naive.

    :param dtm: The input datetime instance.
    :type dtm: dt
    :returns: A timezone-aware datetime instance.
    :rtype: dt
    """
    if dtm.tzinfo is None:
        return dtm.replace(tzinfo=UTC)
    return dtm


@dataclass
class PollingTask:
    """Represents a scheduled polling task for a device command.

    :param device_id: The ID of the target device.
    :type device_id: DeviceIdT
    :param code: The command code string (e.g., '10E0').
    :type code: str
    :param interval: Interval between polls in seconds.
    :type interval: int
    :param next_due: Datetime when the next poll is scheduled.
    :type next_due: dt
    :param last_polled: Datetime when the last poll occurred.
    :type last_polled: dt | None
    :param failures: Count of consecutive polling failures.
    :type failures: int
    :param payload: Optional payload suffix (e.g., zone_idx for 0004).
    :type payload: str | None
    """

    device_id: DeviceIdT
    code: str
    interval: int
    next_due: dt
    last_polled: dt | None = None
    failures: int = 0
    payload: str | None = None


class PollingManager:
    """SSOT-driven polling engine for Layer 7 device entities.

    Evaluates device traits from the schema to determine scheduled command
    polling intervals, falling back to class defaults where necessary.
    Battery-powered devices are strictly excluded from polling.
    """

    def __init__(
        self,
        gateway: Gateway,
        *,
        shadow_mode: bool = True,
        cycle_interval: float = DEFAULT_POLL_CYCLE_SECS,
    ) -> None:
        """Initialize the PollingManager.

        :param gateway: The Gateway instance managing the device registry.
        :type gateway: Gateway
        :param shadow_mode: If True, log schedules without dispatching RF commands.
        :type shadow_mode: bool
        :param cycle_interval: Maximum loop sleep interval in seconds.
        :type cycle_interval: float
        """
        self._gateway = gateway
        self.shadow_mode: bool = shadow_mode
        self._cycle_interval: float = cycle_interval

        # Keys are (device_id, code) for device-level tasks, or
        # (device_id, code, zone_idx) for zone-level tasks (e.g., 0004).
        self._tasks: dict[tuple[str, ...], PollingTask] = {}
        self._poller_task: asyncio.Task[None] | None = None
        self._running: bool = False

    @property
    def is_running(self) -> bool:
        """Return True if the polling loop is active.

        :returns: Active running status of the polling engine.
        :rtype: bool
        """
        return (
            self._running
            and self._poller_task is not None
            and not self._poller_task.done()
        )

    @staticmethod
    def resolve_schedule_for_device(device: DeviceBase) -> PollingIntervalsT:
        """Resolve the effective polling schedule for a given device.

        Combines default device schedule tables with SSOT schema trait overrides,
        ensuring battery-powered devices always resolve to zero polling.

        :param device: The target device instance.
        :type device: DeviceBase
        :returns: A dictionary mapping active command codes to interval seconds.
        :rtype: PollingIntervalsT
        """
        # Battery devices sleep and cannot receive RF requests; never poll them
        if device.is_battery:
            return {}

        slug = getattr(device, "_SLUG", "DEFAULT")
        fallback_schedule = DEFAULT_POLLING_SCHEDULES.get(
            slug, DEFAULT_POLLING_SCHEDULES["DEFAULT"]
        )

        schedule: dict[str, int | None] = dict(fallback_schedule)

        # Override with explicit SSOT schema traits if provided
        if device.polling_interval is not None:
            schedule.update(device.polling_interval)

        # Filter out disabled entries (None or <= 0) to return active intervals only
        return {
            code: interval
            for code, interval in schedule.items()
            if interval is not None and interval > 0
        }

    def update_device_tasks(self, device: DeviceBase) -> set[tuple[str, ...]]:
        """Update or register scheduled polling tasks for a device entity.

        For CTL devices with zones, the ``0004`` (zone name) code is
        expanded into one task per zone, keyed by
        ``(device_id, "0004", zone_idx)``.  This restores the per-zone
        zone-name polling that was lost when the legacy DiscoveryService
        was removed (issue 947 / ramses-rf/ramses_cc#947).

        :param device: The device entity to register or refresh.
        :type device: DeviceBase
        :returns: Set of active task keys for the device.
        :rtype: set[tuple[str, ...]]
        """
        schedule = self.resolve_schedule_for_device(device)
        now = dt.now(UTC)
        active_keys: set[tuple[str, ...]] = set()

        # Collect zone indices for per-zone code expansion (0004).
        # CTL devices have a .tcs attribute with .zones list.
        zone_idxs: list[str] = []
        if Code._0004 in schedule:
            tcs = getattr(device, "tcs", None)
            if tcs is not None:
                zones = getattr(tcs, "zones", [])
                zone_idxs = [z.idx for z in zones if hasattr(z, "idx")]

        for code, interval in schedule.items():
            if code == Code._0004 and zone_idxs:
                # Expand into per-zone tasks
                for zone_idx in zone_idxs:
                    zkey = (device.id, code, zone_idx)
                    active_keys.add(zkey)
                    payload = f"{zone_idx}00"
                    if zkey not in self._tasks:
                        self._tasks[zkey] = PollingTask(
                            device_id=device.id,
                            code=code,
                            interval=interval,
                            next_due=now + td(seconds=interval),
                            payload=payload,
                        )
                    else:
                        self._tasks[zkey].interval = interval
                        self._tasks[zkey].payload = payload
            else:
                dkey = (device.id, code)
                active_keys.add(dkey)
                if dkey not in self._tasks:
                    self._tasks[dkey] = PollingTask(
                        device_id=device.id,
                        code=code,
                        interval=interval,
                        next_due=now + td(seconds=interval),
                    )
                else:
                    self._tasks[dkey].interval = interval

        return active_keys

    def get_scheduled_cmds(self) -> list[PollingTask]:
        """Return a list of all currently tracked polling tasks.

        :returns: A list of active PollingTask objects.
        :rtype: list[PollingTask]
        """
        return list(self._tasks.values())

    def start(self) -> None:
        """Start the background polling loop if not disabled in config."""
        if self._running:
            return

        if getattr(self._gateway.config, "disable_polling", False):
            _LOGGER.info("PollingManager: Polling disabled by GatewayConfig.")
            return

        self._running = True
        self._poller_task = schedule_task(self._poll_loop)
        self._poller_task.set_name("l7_polling_manager")
        self._gateway.add_task(self._poller_task)
        _LOGGER.info(
            "PollingManager started (shadow_mode=%s)", self.shadow_mode
        )

    async def stop(self) -> None:
        """Stop the background polling loop gracefully."""
        self._running = False
        if self._poller_task and not self._poller_task.done():
            self._poller_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poller_task
        self._poller_task = None
        _LOGGER.info("PollingManager stopped.")

    def _calculate_next_sleep_interval(self) -> float:
        """Calculate dynamic sleep delay in seconds based on next due task.

        :returns: Dynamic sleep interval in seconds bounded between 1s and cycle_interval.
        :rtype: float
        """
        if not self._tasks:
            return self._cycle_interval

        now = dt.now(UTC)
        next_due = min(task.next_due for task in self._tasks.values())
        delay = (next_due - now).total_seconds()
        return max(1.0, min(delay, self._cycle_interval))

    async def _poll_loop(self) -> None:
        """Evaluate and execute scheduled tasks in the background."""
        while self._running:
            try:
                await self.poll_due_commands()
            except (RamsesException, TimeoutError) as err:
                _LOGGER.error("Error in PollingManager loop: %s", err)

            sleep_secs = self._calculate_next_sleep_interval()
            await asyncio.sleep(sleep_secs)

    async def poll_due_commands(self) -> int:
        """Evaluate tracked tasks and process commands that are due.

        :returns: Number of tasks processed during this cycle.
        :rtype: int
        """
        if getattr(self._gateway.config, "disable_polling", False):
            return 0

        # Refresh tasks for all devices currently in registry and prune stale tasks
        active_keys: set[tuple[str, ...]] = set()
        for device in list(self._gateway.device_registry.devices):
            active_keys.update(self.update_device_tasks(device))

        for key in list(self._tasks):
            if key not in active_keys:
                del self._tasks[key]

        now = dt.now(UTC)
        processed_count = 0

        for task in list(self._tasks.values()):
            if task.next_due > now:
                continue

            if processed_count > 0 and not self.shadow_mode:
                await asyncio.sleep(POLL_INTER_CMD_GAP)

            processed_count += 1
            if self.shadow_mode:
                _LOGGER.debug(
                    "[SHADOW POLLING] Device %s command %s due (interval=%ss, payload=%s)",
                    task.device_id,
                    task.code,
                    task.interval,
                    task.payload or "00",
                )
                task.last_polled = now
                task.next_due = now + td(seconds=task.interval)
            else:
                _LOGGER.info(
                    "Polling device %s command %s", task.device_id, task.code
                )
                task.last_polled = now
                task.next_due = now + td(seconds=task.interval)
                cmd_dto = build_rq_cmd(
                    task.device_id, task.code, payload=task.payload or "00"
                )
                try:
                    await self._gateway.async_send_cmd(cmd_dto)
                except (RamsesException, TimeoutError) as err:
                    _LOGGER.warning(
                        "PollingManager failed to send command %s to %s: %s",
                        task.code,
                        task.device_id,
                        err,
                    )

        return processed_count
