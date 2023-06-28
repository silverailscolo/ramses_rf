#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""RAMSES RF - RAMSES-II compatible packet protocol finite state machine."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime as dt
from datetime import timedelta as td
from queue import Empty, PriorityQueue
from threading import BoundedSemaphore
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from typing import Callable

    from .command import Command
    from .packet import Packet


_TransportT = TypeVar("_TransportT", bound=asyncio.BaseTransport)


_LOGGER = logging.getLogger(__name__)


TIMEOUT_FOR_ECHO = 0.05
TIMEOUT_FOR_WAIT = 0.20  # incl. wait for echo
MAX_RETRIES_ECHO = 3
MAX_RETRIES_WAIT = 3  # incl. echo retries

DEFAULT_PRIORITY = 1


class ProtocolContext:  # asyncio.Protocol):  # mixin for tracking state
    """A mixin is to add state to a Protocol."""

    DEFAULT_MAX_WAIT: int = 3
    MAX_BUFFER_SIZE: int = 5

    _state: _StateT = None

    def __init__(self, protocol, *args, **kwargs) -> None:
        # super().__init__(*args, **kwargs)
        self._protocol = protocol

        self._loop = asyncio.get_running_loop()
        self._cmd: None | Command = None
        self._que = PriorityQueue(maxsize=self.MAX_BUFFER_SIZE)
        self._sem = BoundedSemaphore(value=1)

        self._set_state(IsInactive)  # set initial state

    def _set_state(self, state: type[_StateT]) -> None:
        """Set the State of the Protocol (context)."""

        assert state != self._state  # there should be a transition to a different state

        if state == IsIdle:
            self._state = state(self)

        elif state == HasFailed:  # FailedRetryLimit?
            # TODO: do something about the fail (see self._state)
            self._state = IsIdle(self)  # drop old_state, if any

        else:
            self._state = state(self, prev_state=self._state)

        if not self.is_sending:
            self._cmd = None
            self._get_next_to_send()

    def connection_made(self, transport: _TransportT) -> None:
        self._state.made_connection(transport)

    def connection_lost(self, exc: None | Exception) -> None:
        self._state.lost_connection(exc)

    def pause_writing(self) -> None:  # not required?
        self._state.writing_paused()

    def resume_writing(self) -> None:
        self._state.writing_resumed()

    async def send_cmd(self, cmd: Command) -> None:
        dt_sent = dt.now()
        dt_expires = dt_sent + td(seconds=self.DEFAULT_MAX_WAIT)
        fut: asyncio.Future = self._set_ready_to_send(cmd, dt_sent, dt_expires)

        while not fut.done():
            if dt_expires <= dt.now():
                fut.set_exception(asyncio.TimeoutError)
                break
            await asyncio.sleep(0.001)
            # self._get_next_to_send()

        try:
            fut.result()
        except asyncio.TimeoutError:
            _LOGGER.debug("!!! expired")
            raise asyncio.TimeoutError("The send did not start before expiring.")
        else:
            _LOGGER.debug("!!! sending...")

        self._state.sent_cmd(cmd)

    def pkt_received(self, pkt: Packet) -> None:
        self._state.rcvd_pkt(pkt)

    @property
    def is_sending(self) -> bool:
        """Return True if the protocol is sending a packet/waiting for a response."""
        return not isinstance(self._state, IsIdle)

    def _set_ready_to_send(self, cmd: Command, sent: dt, expires: dt) -> asyncio.Future:
        """Return a Future that will be done when the protocol is ready to send."""

        fut = self._loop.create_future()

        if self._sem.acquire():
            self._cmd = self._cmd or cmd
            self._sem.release()

        if self._cmd is cmd:
            fut.set_result(None)
        else:
            self._que.put_nowait((DEFAULT_PRIORITY, sent, cmd, expires, fut))

        return fut

    def _get_next_to_send(self) -> None:  # called by context
        """If there are cmds waiting to be sent, inform the next Future in the queue.

        WIll recursively removed all expired cmds.
        """
        fut: asyncio.Future

        try:
            (_, _, cmd, expires, fut) = self._que.get_nowait()
        except Empty:
            return

        if fut.cancelled():
            _LOGGER.debug("--- cancelled")
            self._get_next_to_send()

        elif expires <= dt.now():
            _LOGGER.debug("--- expired")
            fut.set_exception(asyncio.TimeoutError)  # TODO: make a ramses Exception
            self._get_next_to_send()

        else:
            _LOGGER.debug("--- good to go")
            fut.set_result(None)


_ContextT = ProtocolContext  # TypeVar("_ContextT", bound=ProtocolContext)


class ProtocolStateBase:
    # state attrs
    cmd: None | Command
    cmd_sends: int

    def __init__(self, context: _ContextT, prev_state: None | _StateT = None) -> None:
        self._context = context  # a Protocol
        self._set_context_state: Callable = context._set_state  # pylint: disable=W0212

        self.cmd: None | Command = getattr(prev_state, "cmd", None)
        self.cmd_sends: None | int = getattr(prev_state, "cmd_sends", 0)

        _LOGGER.error(f"*** State changed from {prev_state!r} to {self!r}")

    def __repr__(self) -> str:
        # assert self.cmd is None, self.cmd  # AA
        return f"{self.__class__.__name__}()"

    def __str__(self) -> str:
        return self.__class__.__name__

    def _retry_limit_exceeded(self):
        self._set_context_state(HasFailedRetries)

    def made_connection(self, transport: _TransportT) -> None:  # FIXME: may be paused
        self._set_context_state(IsIdle)  # initial state (assumes not paused)

    def lost_connection(self, exc: None | Exception) -> None:
        self._set_context_state(IsInactive)

    def writing_paused(self) -> None:
        self._set_context_state(IsInactive)

    def writing_resumed(self) -> None:
        self._set_context_state(IsIdle)

    def rcvd_pkt(self, pkt: Packet) -> None:
        pass

    def sent_cmd(self, cmd: Command) -> None:
        raise NotImplementedError


class IsInactive(ProtocolStateBase):
    """Protocol has no active connection with a Transport."""

    def rcvd_pkt(self, pkt: Packet) -> None:  # raise an exception
        raise RuntimeError(f"Shouldn't rcvd whilst not connected: {pkt._hdr}")

    async def sent_cmd(self, cmd: Command) -> None:  # raise an exception
        raise RuntimeError(f"Shouldn't send whilst not connected: {cmd._hdr}")


class IsPaused(ProtocolStateBase):
    """Protocol has active connection with a Transport, but should not send."""

    async def sent_cmd(self, cmd: Command) -> None:  # raise an exception
        raise RuntimeError(f"Shouldn't send whilst paused: {cmd._hdr}")


class IsIdle(ProtocolStateBase):
    """Protocol is available to send a Command (has no outstanding Commands)."""

    def __repr__(self) -> str:
        # this is the cmd moved that caused state to move from IsIdle to WantEcho
        hdr = self.cmd._hdr if self.cmd else None
        return f"{self.__class__.__name__}(hdr={hdr})"

    def sent_cmd(self, cmd: Command) -> None:
        # these two are required, so to pass on to next state (via old_state)
        _LOGGER.error(f"...  - sending command: {cmd._hdr}")
        self.cmd = cmd
        self.cmd_sends += 1
        self._set_context_state(WantEcho)


class WantEcho(ProtocolStateBase):
    """Protocol is waiting for the local echo (has sent a Command)."""

    def __init__(self, context: _ContextT, prev_state: None | _StateT = None) -> None:
        super().__init__(context, prev_state=prev_state)

        if self.cmd_sends > self.cmd._qos.retry_limit:  # first send was not a retry
            self._retry_limit_exceeded()

    def __repr__(self) -> str:
        hdr = self.cmd.tx_header if self.cmd else None
        return f"{self.__class__.__name__}(hdr={hdr}, tx={self.cmd_sends})"

    def rcvd_pkt(self, pkt: Packet) -> None:
        """The Transport has received a Packet, possibly the expected echo."""

        if self.cmd.rx_header and pkt._hdr == self.cmd.rx_header:  # expected pkt
            raise RuntimeError(f"Response received before echo: {pkt}")

        if pkt._hdr != self.cmd.tx_header:
            _LOGGER.error(f"Ignoring an unexpected pkt: {pkt}")
        elif self.cmd.rx_header:
            _LOGGER.error(f"... - received echo (& expecting response): {pkt._hdr}")
            self._set_context_state(WantResponse)
        else:
            _LOGGER.error(f"...  - received echo (no response expected): {pkt._hdr}")
            self._set_context_state(IsIdle)

    def sent_cmd(self, cmd: Command) -> None:  # raise an exception
        if (
            cmd._hdr == self.cmd._hdr
            and cmd._addrs == self.cmd._addrs
            and cmd.payload == self.cmd.payload
        ):
            self.cmd_sends += 1
            return

        raise RuntimeError(f"Shouldn't send whilst expecting an echo: {cmd._hdr}")


class WantResponse(ProtocolStateBase):
    """Protocol is now waiting for a response (has received the Command echo)."""

    def __repr__(self) -> str:
        hdr = self.cmd.rx_header if self.cmd else None
        return f"{self.__class__.__name__}(hdr={hdr}, tx={self.cmd_sends})"

    def rcvd_pkt(self, pkt: Packet) -> None:
        """The Transport has received a Packet, possibly the expected response."""

        if pkt._hdr == self.cmd.tx_header:  # expected pkt
            raise RuntimeError(f"Echo received, not response: {pkt}")

        if pkt._hdr != self.cmd.rx_header:
            _LOGGER.error(f"Ignoring an unexpected pkt: {pkt}")
        elif pkt._hdr == self.cmd.rx_header:  # expected pkt
            _LOGGER.error(f"...  - received expected response: {pkt._hdr}")
            self._set_context_state(IsIdle)

    def sent_cmd(self, cmd: Command) -> None:  # raise an exception
        if (
            cmd._hdr == self.cmd._hdr
            and cmd._addrs == self.cmd._addrs
            and cmd.payload == self.cmd.payload
        ):
            self.cmd_sends += 1
            return
        raise RuntimeError(f"Shouldn't send whilst expecting a response: {cmd._hdr}")


class HasFailed(ProtocolStateBase):
    """Protocol has rcvd the Command echo and is waiting for a response to be Rx'd."""

    def sent_cmd(self, cmd: Command) -> None:  # raise an exception
        raise RuntimeError(f"Shouldn't send whilst in a failed state: {cmd._hdr}")


class HasFailedRetries(HasFailed):
    pass


_StateT = ProtocolStateBase  # TypeVar("_StateT", bound=ProtocolStateBase)


class ProtocolState:
    DEAD = IsInactive  # #      #
    IDLE = IsIdle  # ##
    ECHO = WantEcho  # #     #
    WAIT = WantResponse  # #
