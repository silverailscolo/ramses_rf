#!/usr/bin/env python3
"""RAMSES RF - RAMSES-II compatible packet protocol QoS management.

This module provides the QosManager class, responsible for handling
command queuing, priority, retry limits, and dynamic timeouts.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime as dt, timedelta as td
from typing import TYPE_CHECKING, Any, TypeAlias

from ..command import Command
from ..const import (
    DEFAULT_BUFFER_SIZE,
    DEFAULT_ECHO_TIMEOUT,
    DEFAULT_RPLY_TIMEOUT,
    MAX_RETRY_LIMIT,
    MAX_SEND_TIMEOUT,
    Priority,
)
from ..exceptions import ProtocolSendFailed
from ..packet import Packet
from ..typing import QosParams

if TYPE_CHECKING:
    from ..const import Code, VerbT

_LOGGER = logging.getLogger(__name__)

_FutureT: TypeAlias = asyncio.Future[Packet]
_QueueEntryT: TypeAlias = tuple[Priority, dt, Command, QosParams, _FutureT]


class QosManager:
    """Manages the Quality of Service (QoS) queue and retry limits."""

    SEND_TIMEOUT_LIMIT = MAX_SEND_TIMEOUT

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        *,
        echo_timeout: float = DEFAULT_ECHO_TIMEOUT,
        reply_timeout: float = DEFAULT_RPLY_TIMEOUT,
        max_retry_limit: int = MAX_RETRY_LIMIT,
        max_buffer_size: int = DEFAULT_BUFFER_SIZE,
    ) -> None:
        """Initialize the QoS manager.

        :param loop: The asyncio event loop.
        :type loop: asyncio.AbstractEventLoop
        :param echo_timeout: Timeout for an echo response.
        :type echo_timeout: float
        :param reply_timeout: Timeout for a full reply response.
        :type reply_timeout: float
        :param max_retry_limit: Maximum number of times to retry a send.
        :type max_retry_limit: int
        :param max_buffer_size: Maximum size of the command queue.
        :type max_buffer_size: int
        """
        self._loop = loop
        self.echo_timeout = echo_timeout
        self.reply_timeout = reply_timeout
        self.max_retry_limit = min(max_retry_limit, MAX_RETRY_LIMIT)
        self.max_buffer_size = min(max_buffer_size, DEFAULT_BUFFER_SIZE)

        self._que: asyncio.PriorityQueue[_QueueEntryT] = asyncio.PriorityQueue(
            maxsize=self.max_buffer_size
        )

        self._multiplier: int = 0
        self.cmd: Command | None = None
        self.qos: QosParams | None = None
        self.fut: _FutureT | None = None
        self.tx_count: int = 0
        self.tx_limit: int = 0

    @property
    def is_active(self) -> bool:
        """Return True if a command is currently being processed."""
        return self.cmd is not None

    @property
    def qsize(self) -> int:
        """Return the number of commands currently in the queue."""
        return self._que.qsize()

    def enqueue(self, priority: Priority, cmd: Command, qos: QosParams) -> _FutureT:
        """Add a command to the queue and return its future.

        :param priority: The transmission priority.
        :type priority: Priority
        :param cmd: The command to transmit.
        :type cmd: Command
        :param qos: Quality of Service parameters.
        :type qos: QosParams
        :return: The future representing the expected response.
        :rtype: _FutureT
        :raises ProtocolSendFailed: If the send buffer is full.
        """
        fut: _FutureT = self._loop.create_future()
        try:
            self._que.put_nowait((priority, dt.now(), cmd, qos, fut))
        except asyncio.QueueFull as err:
            fut.cancel("Send buffer overflow")
            raise ProtocolSendFailed("Send buffer overflow") from err
        return fut

    def get_next(self) -> bool:
        """Retrieve the next command from the queue.

        :return: True if a new command was successfully loaded.
        :rtype: bool
        """
        if self.fut is not None and not self.fut.done():
            return False

        while True:
            try:
                *_, self.cmd, self.qos, self.fut = self._que.get_nowait()
            except asyncio.QueueEmpty:
                self.reset_active()
                return False

            assert self.qos is not None
            self.tx_count = 0
            self.tx_limit = min(self.qos.max_retries, self.max_retry_limit) + 1

            if self.fut is not None and self.fut.done():
                self._que.task_done()
                continue
            break

        return True

    def task_done(self) -> None:
        """Mark the active queued task as done."""
        self._que.task_done()

    def reset_active(self) -> None:
        """Reset the currently active command state."""
        self.cmd = self.qos = self.fut = None
        self.tx_count = 0

    def get_and_update_delay(self, is_echo: bool) -> tuple[float, int]:
        """Calculate delay and update the multiplier.

        :param is_echo: True if waiting for an echo, False for a reply.
        :type is_echo: bool
        :return: A tuple of the calculated delay and the old multiplier value.
        :rtype: tuple[float, int]
        """
        if is_echo:
            delay = self.echo_timeout * (2**self._multiplier)
        else:
            delay = self.reply_timeout * (2**self._multiplier)

        old_val = self._multiplier
        self._multiplier = max(0, self._multiplier - 1)
        return delay, old_val

    def restore_multiplier(self, old_val: int) -> None:
        """Restore and increment the multiplier after a timeout sleep.

        :param old_val: The previous multiplier value.
        :type old_val: int
        """
        self._multiplier = min(3, old_val + 1)


class Qos:
    """The QoS class - this is a mess - it is the first step in cleaning up QoS."""

    # TODO: this needs work

    POLL_INTERVAL = 0.002

    TX_PRIORITY_DEFAULT = Priority.DEFAULT

    # tx (from sent to gwy, to get back from gwy) seems to takes approx. 0.025s
    TX_RETRIES_DEFAULT = 2
    TX_RETRIES_MAX = 5
    TX_TIMEOUT_DEFAULT = td(seconds=0.2)  # 0.20 OK, but too high?

    RX_TIMEOUT_DEFAULT = td(seconds=0.50)  # 0.20 seems OK, 0.10 too low sometimes

    TX_BACKOFFS_MAX = 2  # i.e. tx_timeout 2 ** MAX_BACKOFF

    QOS_KEYS = ("priority", "max_retries", "timeout")
    # priority, max_retries, rx_timeout, backoff
    DEFAULT_QOS = (Priority.DEFAULT, TX_RETRIES_DEFAULT, TX_TIMEOUT_DEFAULT, True)
    DEFAULT_QOS_TABLE = {
        "RQ|0016": (Priority.HIGH, 5, None, True),
        "RQ|0006": (Priority.HIGH, 5, None, True),
        " I|0404": (Priority.HIGH, 3, td(seconds=0.30), True),
        "RQ|0404": (Priority.HIGH, 3, td(seconds=1.00), True),
        " W|0404": (Priority.HIGH, 3, td(seconds=1.00), True),
        "RQ|0418": (Priority.LOW, 3, None, None),
        "RQ|1F09": (Priority.HIGH, 5, None, True),
        " I|1FC9": (Priority.HIGH, 2, td(seconds=1), False),
        "RQ|3220": (Priority.DEFAULT, 1, td(seconds=1.2), False),
        " W|3220": (Priority.HIGH, 3, td(seconds=1.2), False),
    }  # The long timeout for the OTB is for total RTT to slave (boiler)

    def __init__(
        self,
        *,
        priority: Priority | None = None,  # TODO: deprecate
        max_retries: int | None = None,  # TODO:   deprecate
        timeout: td | None = None,  # TODO:        deprecate
        backoff: bool | None = None,  # TODO:      deprecate
    ) -> None:
        self.priority = self.DEFAULT_QOS[0] if priority is None else priority
        self.retry_limit = self.DEFAULT_QOS[1] if max_retries is None else max_retries
        self.tx_timeout = self.TX_TIMEOUT_DEFAULT
        self.rx_timeout = self.DEFAULT_QOS[2] if timeout is None else timeout
        self.disable_backoff = not (self.DEFAULT_QOS[3] if backoff is None else backoff)

        self.retry_limit = min(self.retry_limit, Qos.TX_RETRIES_MAX)

    @classmethod  # constructor from verb|code pair
    def verb_code(cls, verb: VerbT, code: str | Code, **kwargs: Any) -> Qos:
        """Constructor to create a QoS based upon the defaults for a verb|code pair."""

        default_qos = cls.DEFAULT_QOS_TABLE.get(f"{verb}|{code}", cls.DEFAULT_QOS)
        return cls(
            **{k: kwargs.get(k, default_qos[i]) for i, k in enumerate(cls.QOS_KEYS)}
        )
