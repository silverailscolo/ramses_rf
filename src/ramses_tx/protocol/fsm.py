#!/usr/bin/env python3
"""RAMSES RF - RAMSES-II compatible packet protocol finite state machine.

This module manages the state transitions, command queuing, and QoS
retry mechanisms for the RAMSES-II protocol.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import datetime as dt, timedelta as td
from queue import Empty, Full, PriorityQueue
from threading import Lock
from time import perf_counter
from typing import TYPE_CHECKING, Any, Final, TypeAlias

from ..address import HGI_DEVICE_ID
from ..command import Command
from ..const import (
    DEFAULT_BUFFER_SIZE,
    DEFAULT_ECHO_TIMEOUT,
    DEFAULT_RPLY_TIMEOUT,
    MAX_RETRY_LIMIT,
    MAX_SEND_TIMEOUT,
    Code,
    Priority,
)
from ..exceptions import (
    ProtocolError,
    ProtocolFsmError,
    ProtocolSendFailed,
    TransportError,
)
from ..helpers import dt_now
from ..interfaces import StateMachineInterface, TransportInterface
from ..packet import Packet
from ..typing import HeaderT, QosParams

if TYPE_CHECKING:
    from .core import RamsesProtocolT


_DBG_MAINTAIN_STATE_CHAIN: Final[bool] = False
_DBG_USE_STRICT_TRANSITIONS: Final[bool] = False

_LOGGER = logging.getLogger(__name__)

_FutureT: TypeAlias = asyncio.Future[Packet]
_QueueEntryT: TypeAlias = tuple[Priority, dt, Command, QosParams, _FutureT]


class ProtocolContext(StateMachineInterface):
    """The context for the protocol finite state machine."""

    SEND_TIMEOUT_LIMIT = MAX_SEND_TIMEOUT

    def __init__(
        self,
        protocol: RamsesProtocolT,
        /,
        *,
        echo_timeout: float = DEFAULT_ECHO_TIMEOUT,
        reply_timeout: float = DEFAULT_RPLY_TIMEOUT,
        max_retry_limit: int = MAX_RETRY_LIMIT,
        max_buffer_size: int = DEFAULT_BUFFER_SIZE,
    ) -> None:
        """Initialize the protocol state machine context.

        :param protocol: The protocol instance using this context.
        :type protocol: RamsesProtocolT
        :param echo_timeout: Timeout for an echo response.
        :type echo_timeout: float
        :param reply_timeout: Timeout for a full reply response.
        :type reply_timeout: float
        :param max_retry_limit: Maximum number of times to retry a send.
        :type max_retry_limit: int
        :param max_buffer_size: Maximum size of the command queue.
        :type max_buffer_size: int
        """
        self._protocol = protocol
        self.echo_timeout = echo_timeout
        self.reply_timeout = reply_timeout
        self.max_retry_limit = min(max_retry_limit, MAX_RETRY_LIMIT)
        self.max_buffer_size = min(max_buffer_size, DEFAULT_BUFFER_SIZE)

        self._loop = protocol._loop
        self._lock = Lock()
        self._fut: _FutureT | None = None
        self._que: PriorityQueue[_QueueEntryT] = PriorityQueue(
            maxsize=self.max_buffer_size
        )

        self._expiry_timer: asyncio.Task[None] | None = None
        self._multiplier = 0
        self._state: _ProtocolStateT = None  # type: ignore[assignment]

        self._send_fnc: Callable[[Command], Coroutine[Any, Any, None]] = None  # type: ignore[assignment]

        self._cmd: Command | None = None
        self._qos: QosParams | None = None
        self._cmd_tx_count: int = 0
        self._cmd_tx_limit: int = 0

        self.set_state(Inactive)

    def __repr__(self) -> str:
        """Return an unambiguous string representation of this object."""
        msg = f"<ProtocolContext state={repr(self._state)[21:-1]}"
        if self._cmd is None:
            return msg + ">"
        if self._cmd_tx_count == 0:
            return msg + ", tx_count=0/0>"
        return msg + f", tx_count={self._cmd_tx_count}/{self._cmd_tx_limit}>"

    @property
    def is_sending(self) -> bool:
        """Return True if the context is currently sending a command."""
        return isinstance(self._state, WantEcho | WantRply)

    @property
    def state(self) -> _ProtocolStateT:
        """Return the current state of the FSM."""
        return self._state

    def set_state(
        self,
        state_class: _ProtocolStateClassT,
        expired: bool = False,
        timed_out: bool = False,
        exception: Exception | None = None,
        result: Packet | None = None,
    ) -> None:
        """Transition the state machine to a new state.

        :param state_class: The new state class to transition to.
        :type state_class: _ProtocolStateClassT
        :param expired: Whether the state transition is due to a full expiry.
        :type expired: bool
        :param timed_out: Whether the state transition is due to a timeout.
        :type timed_out: bool
        :param exception: Any exception that caused the state transition.
        :type exception: Exception | None
        :param result: Any resulting packet associated with the transition.
        :type result: Packet | None
        """

        async def expire_state_on_timeout() -> None:
            if isinstance(self._state, WantEcho):
                delay = self.echo_timeout * (2**self._multiplier)
            else:
                delay = self.reply_timeout * (2**self._multiplier)

            self._multiplier, old_val = max(0, self._multiplier - 1), self._multiplier
            await asyncio.sleep(delay)
            self._multiplier = min(3, old_val + 1)

            level = (
                logging.DEBUG
                if self._cmd_tx_count < 3
                else logging.INFO
                if self._cmd_tx_count == 3
                else logging.WARNING
            )
            state_str = "echo" if isinstance(self._state, WantEcho) else "reply"
            _LOGGER.log(
                level,
                f"Timeout expired waiting for {state_str}: {self} (delay={delay})",
            )

            if self._cmd_tx_count < self._cmd_tx_limit:
                self.set_state(WantEcho, timed_out=True)
            else:
                self.set_state(IsInIdle, expired=True)

        def effect_state(timed_out: bool) -> None:
            if timed_out and self._cmd is not None:
                self._send_cmd(self._cmd, is_retry=True)

            if isinstance(self._state, IsInIdle):
                self._loop.call_soon_threadsafe(self._check_buffer_for_cmd)
            elif isinstance(self._state, WantRply) and not self._qos.wait_for_reply:  # type: ignore[union-attr]
                self.set_state(IsInIdle, result=self._state._echo_pkt)
            elif isinstance(self._state, WantEcho | WantRply):
                self._expiry_timer = self._loop.create_task(expire_state_on_timeout())

        if self._expiry_timer is not None:
            self._expiry_timer.cancel("Changing state")
            self._expiry_timer = None

        current_state_name = self._state.__class__.__name__
        new_state_name = state_class.__name__
        transition = f"{current_state_name}->{new_state_name}"

        if self._fut is None:
            _LOGGER.debug(
                f"FSM state changed {transition}: no active future (ctx={self})"
            )
        elif self._fut.cancelled() and not isinstance(self._state, IsInIdle):
            _LOGGER.debug(
                f"FSM state changed {transition}: future cancelled (expired={expired}, ctx={self})"
            )
        elif exception:
            _LOGGER.debug(
                f"FSM state changed {transition}: exception occurred (error={exception}, ctx={self})"
            )
            if not self._fut.done():
                self._fut.set_exception(exception)
        elif result:
            _LOGGER.debug(
                f"FSM state changed {transition}: result received (result={result._hdr}, ctx={self})"
            )
            if not self._fut.done():
                self._fut.set_result(result)
        elif expired:
            _LOGGER.debug(f"FSM state changed {transition}: timer expired (ctx={self})")
            if not self._fut.done():
                self._fut.set_exception(
                    ProtocolSendFailed(f"{self}: Exceeded maximum retries")
                )
        else:
            _LOGGER.debug(f"FSM state changed {transition}: successful (ctx={self})")

        prev_state = self._state
        self._state = state_class(self)

        if _DBG_MAINTAIN_STATE_CHAIN:
            setattr(self._state, "_prev_state", prev_state)  # noqa: B010

        if timed_out:
            self._cmd_tx_count += 1
        elif isinstance(self._state, WantEcho):
            self._cmd_tx_count = 1
        elif not isinstance(self._state, WantRply):
            self._cmd = self._qos = None
            self._cmd_tx_count = 0

        self._loop.call_soon_threadsafe(effect_state, timed_out)

    def connection_made(self, transport: TransportInterface) -> None:
        """Handle the transport connection being made."""
        self._state.connection_made()

    def connection_lost(self, err: Exception | None) -> None:
        """Handle the transport connection being lost."""
        self._state.connection_lost()

    def pkt_received(self, pkt: Packet) -> None:
        """Process a received packet (echo or reply)."""
        self._state.pkt_rcvd(pkt)

    def pause_writing(self) -> None:
        """Handle the transport pausing writing."""
        self._state.writing_paused()

    def resume_writing(self) -> None:
        """Handle the transport resuming writing."""
        self._state.writing_resumed()

    async def send_cmd(
        self,
        send_fnc: Callable[[Command], Coroutine[Any, Any, None]],
        cmd: Command,
        priority: Priority,
        qos: QosParams,
    ) -> Packet:
        """Send a Command with QoS (retries, until success or Exception).

        :param send_fnc: The function used to actually transmit the command.
        :type send_fnc: Callable[[Command], Coroutine[Any, Any, None]]
        :param cmd: The command to send.
        :type cmd: Command
        :param priority: The transmission priority.
        :type priority: Priority
        :param qos: Quality of Service parameters.
        :type qos: QosParams
        :return: The received response packet, or the echo if no response is expected.
        :rtype: Packet
        :raises ProtocolSendFailed: If the send times out or retries are exhausted.
        """
        self._send_fnc = send_fnc

        if isinstance(self._state, Inactive):
            raise ProtocolSendFailed(f"{self}: Send failed (no active transport?)")

        fut: _FutureT = self._loop.create_future()
        try:
            self._que.put_nowait((priority, dt.now(), cmd, qos, fut))
        except Full as err:
            fut.cancel("Send buffer overflow")
            raise ProtocolSendFailed(f"{self}: Send buffer overflow") from err

        if isinstance(self._state, IsInIdle):
            self._loop.call_soon_threadsafe(self._check_buffer_for_cmd)

        timeout = min(qos.timeout, self.SEND_TIMEOUT_LIMIT)
        try:
            await asyncio.wait_for(fut, timeout=timeout)
        except TimeoutError as err:
            msg = f"{self}: Expired global timer after {timeout} sec"
            _LOGGER.warning(
                "TOUT.. = %s: send_timeout=%s (%s)", self, timeout, self._cmd is cmd
            )
            if self._cmd is cmd:
                self.set_state(IsInIdle, expired=True)
            raise ProtocolSendFailed(msg) from err

        try:
            return fut.result()
        except ProtocolSendFailed:
            raise
        except (ProtocolError, TransportError) as err:
            raise ProtocolSendFailed(f"{self}: Send failed: {err}") from err

    def _check_buffer_for_cmd(self) -> None:
        """Check the queue buffer and send the next command if available."""
        self._lock.acquire()

        if self._fut is not None and not self._fut.done():
            self._lock.release()
            return

        while True:
            try:
                *_, self._cmd, self._qos, self._fut = self._que.get_nowait()
            except Empty:
                self._cmd = self._qos = self._fut = None
                self._lock.release()
                return

            self._cmd_tx_count = 0
            self._cmd_tx_limit = min(self._qos.max_retries, self.max_retry_limit) + 1

            assert isinstance(self._fut, asyncio.Future)
            if self._fut.done():
                self._que.task_done()
                continue
            break

        self._lock.release()

        try:
            assert self._cmd is not None
            self._send_cmd(self._cmd)
        finally:
            self._que.task_done()

    def _send_cmd(self, cmd: Command, is_retry: bool = False) -> None:
        """Wrapper to send a command with retries, until success or exception.

        :param cmd: The command to transmit.
        :type cmd: Command
        :param is_retry: Flag indicating if this is a retry attempt.
        :type is_retry: bool
        """

        async def send_fnc_wrapper(cmd: Command) -> None:
            # Native Sync Collision Avoidance incorporated into FSM queue processing
            def is_imminent(p: Packet) -> bool:
                lower = td(seconds=0.010 * 0.8)
                upper = lower + td(seconds=0.084)
                return bool(
                    lower
                    < (p.dtm + td(seconds=int(p.payload[2:6], 16) / 10) - dt_now())
                    < upper
                )

            start = perf_counter()
            # Wait, self._protocol._tracked_sync_cycles is populated in base.py
            while any(
                is_imminent(p)
                for p in getattr(self._protocol, "_tracked_sync_cycles", [])
            ):
                await asyncio.sleep(0.010)
            if perf_counter() - start > 0.010:
                await asyncio.sleep(0.084)

            try:
                await self._send_fnc(cmd)
            except TransportError as err:
                self.set_state(IsInIdle, exception=err)

        try:
            self._state.cmd_sent(cmd, is_retry=is_retry)
        except ProtocolFsmError as err:
            self.set_state(IsInIdle, exception=err)
        else:
            self._loop.create_task(send_fnc_wrapper(cmd))


class ProtocolStateBase:
    """The base class for the protocol finite state machine states."""

    def __init__(self, context: ProtocolContext) -> None:
        """Initialize the state with the protocol context."""
        self._context = context
        self._sent_cmd: Command | None = None
        self._echo_pkt: Packet | None = None
        self._rply_pkt: Packet | None = None

    def __repr__(self) -> str:
        """Return an unambiguous string representation of this state."""
        msg = f"<ProtocolState state={self.__class__.__name__}"
        if self._rply_pkt:
            return msg + f" rply={self._rply_pkt._hdr}>"
        if self._echo_pkt:
            return msg + f" echo={self._echo_pkt._hdr}>"
        if self._sent_cmd:
            return msg + f" cmd_={self._sent_cmd._hdr}>"
        return msg + ">"

    def connection_made(self) -> None:
        """Do nothing, as (except for InActive) we're already connected."""
        pass

    def connection_lost(self) -> None:
        """Transition to Inactive, regardless of current state."""
        if isinstance(self._context._state, Inactive):
            return

        if isinstance(self._context._state, IsInIdle):
            self._context.set_state(Inactive)
            return

        self._context.set_state(Inactive, exception=TransportError("Connection lost"))

    def pkt_rcvd(self, pkt: Packet) -> None:
        """Raise a NotImplementedError."""
        raise NotImplementedError("Invalid state to receive a packet")

    def writing_paused(self) -> None:
        """Do nothing."""
        pass

    def writing_resumed(self) -> None:
        """Do nothing."""
        pass

    def cmd_sent(self, cmd: Command, is_retry: bool | None = None) -> None:
        """Raise an error as default states cannot send commands."""
        raise ProtocolFsmError(f"Invalid state to send a command: {self._context}")


class Inactive(ProtocolStateBase):
    """The Protocol is not connected to the transport layer."""

    def connection_made(self) -> None:
        """Transition to IsInIdle."""
        self._context.set_state(IsInIdle)

    def pkt_rcvd(self, pkt: Packet) -> None:
        """Raise an exception, as a packet is not expected in this state."""
        if pkt.code != Code._PUZZ:
            _LOGGER.warning("%s: Invalid state to receive a packet", self._context)


class IsInIdle(ProtocolStateBase):
    """The Protocol is not in the process of sending a Command."""

    def pkt_rcvd(self, pkt: Packet) -> None:
        """Do nothing as we're not expecting an echo, nor a reply."""
        pass

    def cmd_sent(self, cmd: Command, is_retry: bool | None = None) -> None:
        """Transition to WantEcho."""
        self._sent_cmd = cmd

        if HGI_DEVICE_ID in cmd.tx_header:
            assert cmd._hdr_ is not None
            cmd._hdr_ = HeaderT(
                cmd._hdr_.replace(HGI_DEVICE_ID, self._context._protocol.hgi_id)
            )
        self._context.set_state(WantEcho)


class WantEcho(ProtocolStateBase):
    """The Protocol is waiting to receive an echo Packet."""

    def __init__(self, context: ProtocolContext) -> None:
        """Initialize the state from the previous context state."""
        super().__init__(context)
        self._sent_cmd = context._state._sent_cmd

    def pkt_rcvd(self, pkt: Packet) -> None:
        """If the pkt is the expected Echo, transition to IsInIdle, or WantRply."""
        assert self._sent_cmd is not None

        if (
            self._sent_cmd.rx_header
            and pkt._hdr == self._sent_cmd.rx_header
            and (
                pkt.dst.id == self._sent_cmd.src.id
                or (
                    self._sent_cmd.src.id == HGI_DEVICE_ID
                    and pkt.dst.id == self._context._protocol.hgi_id
                )
            )
        ):
            level = (
                logging.DEBUG
                if self._context._cmd_tx_count < 3
                else logging.INFO
                if self._context._cmd_tx_count == 3
                else logging.WARNING
            )
            _LOGGER.log(
                level,
                "%s: Invalid state to receive a reply (expecting echo)",
                self._context,
            )
            self._rply_pkt = pkt
            self._context.set_state(IsInIdle, result=pkt)
            return

        if HGI_DEVICE_ID in pkt._hdr:
            assert pkt._hdr_ is not None
            pkt__hdr = HeaderT(
                pkt._hdr_.replace(HGI_DEVICE_ID, self._context._protocol.hgi_id)
            )
        else:
            pkt__hdr = pkt._hdr

        if pkt__hdr != self._sent_cmd.tx_header:
            return

        self._echo_pkt = pkt
        if self._sent_cmd.rx_header:
            self._context.set_state(WantRply)
        else:
            self._context.set_state(IsInIdle, result=pkt)

    def cmd_sent(self, cmd: Command, is_retry: bool | None = None) -> None:
        """Transition to WantEcho (i.e. a retransmit)."""
        pass


class WantRply(ProtocolStateBase):
    """The Protocol is waiting to receive an reply Packet."""

    def __init__(self, context: ProtocolContext) -> None:
        """Initialize the state with the echo that triggered it."""
        super().__init__(context)
        self._sent_cmd = context._state._sent_cmd
        self._echo_pkt = context._state._echo_pkt

    def pkt_rcvd(self, pkt: Packet) -> None:
        """If the pkt is the expected reply, transition to IsInIdle."""
        assert self._sent_cmd is not None
        assert self._echo_pkt is not None

        if pkt._hdr == self._sent_cmd.tx_header and pkt.src == self._echo_pkt.src:
            level = (
                logging.DEBUG
                if self._context._cmd_tx_count < 3
                else logging.INFO
                if self._context._cmd_tx_count == 3
                else logging.WARNING
            )
            _LOGGER.log(
                level,
                "%s: Invalid state to receive an echo (expecting reply)",
                self._context,
            )
            return

        if (
            self._sent_cmd.rx_header[:8] == "0418|RP|"  # type: ignore[index]
            and self._sent_cmd.rx_header[:-2] == pkt._hdr[:-2]  # type: ignore[index]
            and pkt.payload == "000000B0000000000000000000007FFFFF7000000000"
        ):
            self._rply_pkt = pkt
        elif pkt._hdr != self._sent_cmd.rx_header:
            return
        else:
            self._rply_pkt = pkt

        self._context.set_state(IsInIdle, result=pkt)


_ProtocolStateT: TypeAlias = Inactive | IsInIdle | WantEcho | WantRply
_ProtocolStateClassT: TypeAlias = (
    type[Inactive] | type[IsInIdle] | type[WantEcho] | type[WantRply]
)
