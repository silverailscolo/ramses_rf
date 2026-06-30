#!/usr/bin/env python3
"""RAMSES RF - Polling Service Component.

This module provides the PollingService component, which orchestrates
background polling commands for an entity.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from datetime import datetime as dt, timedelta as td
from typing import TYPE_CHECKING, Any

from ramses_tx import Command, Packet

from . import exceptions as exc
from .helpers import schedule_task

if TYPE_CHECKING:
    from ramses_tx.typing import HeaderT

    from .gateway import Gateway

_LOGGER = logging.getLogger(__name__)

_SZ_LAST_PKT: str = "last_msg"
_SZ_NEXT_DUE: str = "next_due"
_SZ_TIMEOUT: str = "timeout"
_SZ_FAILURES: str = "failures"
_SZ_INTERVAL: str = "interval"
_SZ_COMMAND: str = "command"

MAX_CYCLE_SECS: int = 30
MIN_CYCLE_SECS: int = 3


class PollingService:
    """Manages discovery orchestration and polling loops for an entity.

    This class is intended to be composed into Entity classes. It tracks
    which commands an entity supports and periodically polls them.
    """

    MAX_CYCLE_SECS: int = 30
    MIN_CYCLE_SECS: int = 3

    def __init__(self, entity: Any, gwy: Gateway) -> None:
        """Initialize the PollingService.

        :param entity: The entity this service represents.
        :type entity: Any
        :param gwy: The gateway orchestrator providing I/O access.
        :type gwy: Gateway
        """
        self._entity = entity
        self._gwy = gwy

        self.cmds: dict[HeaderT, dict[str, Any]] = {}
        self._poller: asyncio.Task[None] | None = None

        self._supported_cmds: dict[str, bool | None] = {}
        self._supported_cmds_ctx: dict[str, bool | None] = {}

        if not gwy.config.disable_discovery:
            try:
                _LOGGER.debug("DiscoveryService init start_poller")
                asyncio.get_running_loop().call_soon(self.start_poller)
            except RuntimeError:
                # Fallback if instantiated outside of a running event loop context
                _LOGGER.debug(
                    "No running event loop; discovery poller must be started manually."
                )

    def add_cmd(
        self,
        cmd: Command,
        interval: float,
        *,
        delay: float = 0,
        timeout: float | None = None,
    ) -> None:
        """Schedule a command to run periodically.

        :param cmd: The command to poll.
        :type cmd: Command
        :param interval: The polling interval in seconds.
        :type interval: float
        :param delay: The initial delay before the first poll, defaults to 0.
        :type delay: float, optional
        :param timeout: The request timeout, defaults to None.
        :type timeout: float | None, optional
        :raises CommandInvalid: If the header is missing.
        """
        if cmd.rx_header is None:
            raise exc.CommandInvalid(
                f"cmd({cmd}): invalid (null) header not added to discovery"
            )

        if cmd.rx_header in self.cmds:
            _LOGGER.info("cmd(%s): duplicate header not added to discovery", cmd)
            return

        if delay:
            delay += random.uniform(0.05, 0.45)

        _LOGGER.debug(
            "FilterChange add_cmd(cmd: %s, interval: %s, delay: %s) hdr: %s",
            cmd,
            interval,
            delay,
            cmd.rx_header,
        )

        self.cmds[cmd.rx_header] = {
            _SZ_COMMAND: cmd,
            _SZ_INTERVAL: td(seconds=max(interval, MAX_CYCLE_SECS)),
            _SZ_LAST_PKT: None,
            _SZ_NEXT_DUE: dt.now() + td(seconds=delay),
            _SZ_TIMEOUT: timeout,
            _SZ_FAILURES: 0,
        }

    def start_poller(self) -> None:
        """
        Start polling a fan.
        Messages are cleaned up every 12h.
        """
        """Start the filter poller (if it is not already running)."""
        _LOGGER.debug("start_poller()")
        if self._poller and not self._poller.done():
            return

        self._poller = schedule_task(self.poll_cmds)
        _LOGGER.debug("start_poller task created %s", self._poller.get_name())
        # this takes action just once if no period given, so it might have 0 tasks
        self._poller.set_name(f"{self._entity.id}_hvac_poller")
        self._gwy.add_task(self._poller)  # just for housekeeping

    async def stop_poller(self) -> None:
        """Stop the filter poller (only if it is running)."""
        if not self._poller or self._poller.done():
            return

        self._poller.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._poller

    async def poll_cmds(self) -> None:
        """Send any outstanding commands that are past due."""
        _LOGGER.debug("FilterChange poll_cmds()")
        while True:
            _LOGGER.debug("poll_cmds poll() loop")
            await self.poll()

            if self.cmds:
                next_due = min(t[_SZ_NEXT_DUE] for t in self.cmds.values())
                delay = max((next_due - dt.now()).total_seconds(), MIN_CYCLE_SECS)
            else:
                delay = MAX_CYCLE_SECS

            await asyncio.sleep(min(delay, MAX_CYCLE_SECS))

    async def poll(self) -> None:
        """Process the outstanding commands."""
        # method is based on discovery.py

        async def send_poll_cmd(
            hdr: HeaderT, task: dict[str, Any], timeout: float = 15
        ) -> Packet | None:
            """Send a scheduled command and wait for/return the response."""
            try:
                _LOGGER.debug("poll_cmds > poll() send_poll_cmd(%s)", hdr)

                pkt: Packet | None = await asyncio.wait_for(
                    self._gwy.async_send_cmd(task[_SZ_COMMAND]),
                    timeout=timeout,
                )
            except exc.ProtocolError as err:
                _LOGGER.warning(
                    f"{self._entity.id}: Failed to send poll cmd: {hdr}: {err}"
                )
            except TimeoutError as err:
                _LOGGER.warning(
                    f"{self._entity.id}: Failed to send poll cmd: {hdr} within {timeout} secs: {err}"
                )
            else:
                return pkt
            return None

        _LOGGER.debug("poller started")
        for hdr, task in self.cmds.items():
            _LOGGER.debug("polling for %s", hdr)
            dt_now = dt.now()

            if task[_SZ_NEXT_DUE] > dt_now:
                continue

            task[_SZ_NEXT_DUE] = dt_now + task[_SZ_INTERVAL]

            _LOGGER.debug("hvac.send_poll_cmd(hdr: %s, task: %s)", hdr, task)
            if pkt := await send_poll_cmd(hdr, task):
                task[_SZ_FAILURES] = 0
                task[_SZ_LAST_PKT] = pkt
                task[_SZ_NEXT_DUE] = pkt.dtm + task[_SZ_INTERVAL]
            else:
                task[_SZ_FAILURES] += 1
                task[_SZ_LAST_PKT] = None
                task[_SZ_NEXT_DUE] = dt_now
