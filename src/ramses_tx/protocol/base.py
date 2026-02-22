#!/usr/bin/env python3
"""RAMSES RF - RAMSES-II compatible packet protocol base classes.

This module provides the foundational protocol layers, handling transport
binding, basic message dispatching, regex-based payload manipulation,
and device ID filtering mechanisms.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import deque
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime as dt, timedelta as td
from typing import TYPE_CHECKING, Final

from ..address import ALL_DEV_ADDR, HGI_DEV_ADDR, NON_DEV_ADDR
from ..command import Command
from ..const import (
    DEFAULT_GAP_DURATION,
    DEFAULT_NUM_REPEATS,
    DEV_TYPE_MAP,
    I_,
    MAX_GAP_DURATION,
    MAX_NUM_REPEATS,
    SZ_ACTIVE_HGI,
    Code,
    DevType,
    Priority,
)
from ..exceptions import ProtocolError, ProtocolSendFailed, TransportError
from ..helpers import dt_now
from ..interfaces import ProtocolInterface, TransportInterface
from ..message import Message
from ..packet import Packet
from ..schemas import SZ_BLOCK_LIST, SZ_CLASS, SZ_INBOUND, SZ_KNOWN_LIST, SZ_OUTBOUND
from ..typing import (
    DeviceIdT,
    DeviceListT,
    ExceptionT,
    MsgFilterT,
    MsgHandlerT,
    QosParams,
)

if TYPE_CHECKING:
    from .fsm import ProtocolContext


TIP: Final[str] = f", configure the {SZ_KNOWN_LIST}/{SZ_BLOCK_LIST} as required"

_DBG_FORCE_LOG_PACKETS: Final[bool] = False

_LOGGER = logging.getLogger(__name__)

DEFAULT_QOS = QosParams()


class _BaseProtocol(ProtocolInterface, asyncio.Protocol):
    """Base class for RAMSES II protocols."""

    WRITER_TASK: Final[str] = "writer_task"

    def __init__(self, msg_handler: MsgHandlerT, /) -> None:
        """Initialize the base protocol.

        :param msg_handler: The callback invoked when a valid message is processed.
        :type msg_handler: MsgHandlerT
        """
        self._msg_handler = msg_handler
        self._msg_handlers: list[tuple[MsgHandlerT, MsgFilterT | None]] = []

        self._transport: TransportInterface | None = None
        self._loop = asyncio.get_running_loop()

        self._pause_writing: bool = (
            False  # FIXME: Start in R/O mode as no connection yet?
        )
        self._wait_connection_lost: asyncio.Future[None] | None = None
        self._wait_connection_made: asyncio.Future[TransportInterface] = (
            self._loop.create_future()
        )

        self._this_msg: Message | None = None
        self._prev_msg: Message | None = None

        self._is_evofw3: bool | None = None

        self._active_hgi: DeviceIdT | None = None
        self._context: ProtocolContext | None = None

        # regex rules and sync trackers
        self._inbound_regex: dict[str, str] = {}
        self._outbound_regex: dict[str, str] = {}
        self._tracked_sync_cycles: deque[Packet] = deque(maxlen=3)

    @property
    def hgi_id(self) -> DeviceIdT:
        """Get the Hardware Gateway Interface ID."""
        return HGI_DEV_ADDR.id

    def set_regex_rules(self, rules: dict[str, dict[str, str]]) -> None:
        """Set regex rules for inbound/outbound payload manipulation."""
        self._inbound_regex = rules.get(SZ_INBOUND, {})
        self._outbound_regex = rules.get(SZ_OUTBOUND, {})

    def _apply_regex(self, frame: str, rules: dict[str, str]) -> str:
        """Apply regex hacks to a frame string."""
        if not rules:
            return frame
        result = frame
        for k, v in rules.items():
            try:
                result = re.sub(k, v, result)
            except re.error as err:
                _LOGGER.warning(f"{frame} < issue with regex ({k}, {v}): {err}")
        return result

    def add_handler(
        self,
        msg_handler: MsgHandlerT,
        /,
        *,
        msg_filter: MsgFilterT | None = None,
    ) -> Callable[[], None]:
        """Add a Message handler to the list of such callbacks.

        Returns a callback that can be used to subsequently remove the Message handler.

        :param msg_handler: The handler function to add.
        :type msg_handler: MsgHandlerT
        :param msg_filter: An optional filter to apply before calling the handler.
        :type msg_filter: MsgFilterT | None
        :return: A callable to remove the handler.
        :rtype: Callable[[], None]
        """
        entry = (msg_handler, msg_filter)

        def del_handler() -> None:
            if entry in self._msg_handlers:
                self._msg_handlers.remove(entry)

        if entry not in self._msg_handlers:
            self._msg_handlers.append(entry)

        return del_handler

    def connection_made(self, transport: TransportInterface) -> None:  # type: ignore[override]
        """Called when the connection to the Transport is established.

        The argument is the transport representing the pipe connection. To receive data,
        wait for pkt_received() calls. When the connection is closed, connection_lost()
        is called.
        """
        if self._wait_connection_made.done():
            return

        self._wait_connection_lost = self._loop.create_future()
        self._wait_connection_made.set_result(transport)
        self._transport = transport

    async def wait_for_connection_made(
        self, timeout: float = 1.0
    ) -> TransportInterface:
        """A courtesy function to wait until connection_made() has been invoked.

        Will raise TransportError if isn't connected within timeout seconds.
        """
        try:
            return await asyncio.wait_for(self._wait_connection_made, timeout)
        except TimeoutError as err:
            raise TransportError(
                f"Transport did not bind to Protocol within {timeout} secs"
            ) from err

    def connection_lost(self, err: Exception | None) -> None:
        """Called when the connection to the Transport is lost or closed.

        The argument is an exception object or None (the latter meaning a regular EOF is
        received or the connection was aborted or closed).
        """
        if not self._wait_connection_lost:
            _LOGGER.debug(
                "connection_lost called but no connection was established (ignoring)"
            )
            # Reset the connection made future for next attempt
            if self._wait_connection_made.done():
                self._wait_connection_made = self._loop.create_future()
            return

        if self._wait_connection_lost.done():
            return

        self._wait_connection_made = self._loop.create_future()
        if err:
            self._wait_connection_lost.set_exception(err)
        else:
            self._wait_connection_lost.set_result(None)

    async def wait_for_connection_lost(self, timeout: float = 1.0) -> ExceptionT | None:
        """A courtesy function to wait until connection_lost() has been invoked.

        Includes scenarios where neither connection_made() nor connection_lost() were
        invoked.

        Will raise TransportError if isn't disconnect within timeout seconds.
        """
        if not self._wait_connection_lost:
            return None

        try:
            return await asyncio.wait_for(self._wait_connection_lost, timeout)
        except TimeoutError as err:
            raise TransportError(
                f"Transport did not unbind from Protocol within {timeout} secs"
            ) from err

    def pause_writing(self) -> None:
        """Called when the transport's buffer goes over the high-water mark."""
        self._pause_writing = True

    def resume_writing(self) -> None:
        """Called when the transport's buffer drains below the low-water mark."""
        self._pause_writing = False

    async def _send_impersonation_alert(self, cmd: Command) -> None:
        """Allow the Protocol to send an impersonation alert (stub)."""
        return

    def _patch_cmd_if_needed(self, cmd: Command) -> Command:
        """Patch the command with the actual HGI ID if it uses the default placeholder.

        Legacy HGI80s (TI 3410) require the default ID (18:000730), or they will
        silent-fail. However, evofw3 devices prefer the real ID.
        """
        # NOTE: accessing private member cmd._addrs to safely patch the source address
        if (
            self.hgi_id
            and self._is_evofw3  # Only patch if using evofw3 (not HGI80)
            and cmd._addrs[0].id == HGI_DEV_ADDR.id
            and self.hgi_id != HGI_DEV_ADDR.id
        ):
            _LOGGER.debug(
                f"Patching command with active HGI ID: swapped {HGI_DEV_ADDR.id} "
                f"-> {self.hgi_id} for {cmd._hdr}"
            )

            # Get current addresses as strings
            new_addrs = [a.id for a in cmd._addrs]

            # ONLY patch the Source Address (Index 0).
            # Leave Dest (Index 1/2) alone to avoid breaking tests that expect 18:000730.
            new_addrs[0] = self.hgi_id

            # Reconstruct the command string with the correct address
            new_frame = (
                f"{cmd.verb} {cmd.seqn} {new_addrs[0]} {new_addrs[1]} {new_addrs[2]} "
                f"{cmd.code} {int(cmd.len_):03d} {cmd.payload}"
            )
            return Command(new_frame)

        return cmd

    async def send_cmd(
        self,
        cmd: Command,
        /,
        *,
        gap_duration: float = DEFAULT_GAP_DURATION,
        num_repeats: int = DEFAULT_NUM_REPEATS,
        priority: Priority = Priority.DEFAULT,
        qos: QosParams | None = None,
    ) -> Packet:
        """Send a Command with Qos (with retries, until success or ProtocolError).

        Returns the Command's response Packet or the Command echo if a response is not
        expected (e.g. sending an RP).

        If wait_for_reply is True, return the RQ's RP (or W's I), or raise an exception
        if one doesn't arrive. If it is False, return the echo of the Command only. If
        it is None (the default), act as True for RQs, and False for all other Commands.

        num_repeats is # of times to send the Command, in addition to the fist transmit,
        with gap_duration seconds between each transmission. If wait_for_reply is True,
        then num_repeats is ignored.

        Commands are queued and sent FIFO, except higher-priority Commands are always
        sent first.

        Will raise:
            ProtocolSendFailed: tried to Tx Command, but didn't get echo/reply
            ProtocolError:      didn't attempt to Tx Command for some reason
        """
        assert 0 <= gap_duration <= MAX_GAP_DURATION, "Out of range: gap_duration"
        assert 0 <= num_repeats <= MAX_NUM_REPEATS, "Out of range: num_repeats"

        # Patch command with actual HGI ID if it uses the default placeholder
        cmd = self._patch_cmd_if_needed(cmd)

        if qos and not self._context:
            _LOGGER.warning(f"{cmd} < QoS is currently disabled by this Protocol")

        if cmd.src.id != self.hgi_id:  # Was HGI_DEV_ADDR.id
            await self._send_impersonation_alert(cmd)

        if qos and qos.wait_for_reply and num_repeats:
            _LOGGER.warning(f"{cmd} < num_repeats set to 0, as wait_for_reply is True")
            num_repeats = 0  # the lesser crime over wait_for_reply=False

        pkt = await self._send_cmd(  # may: raise ProtocolError/ProtocolSendFailed
            cmd,
            gap_duration=gap_duration,
            num_repeats=num_repeats,
            priority=priority,
            qos=qos or DEFAULT_QOS,
        )

        if not pkt:  # HACK: temporary workaround for returning None
            raise ProtocolSendFailed(f"Failed to send command: {cmd} (REPORT THIS)")

        return pkt

    async def _send_cmd(
        self,
        cmd: Command,
        /,
        *,
        gap_duration: float = DEFAULT_GAP_DURATION,
        num_repeats: int = DEFAULT_NUM_REPEATS,
        priority: Priority = Priority.DEFAULT,
        qos: QosParams = DEFAULT_QOS,
    ) -> Packet:  # only cmd, no args, kwargs
        raise NotImplementedError(f"{self}: Unexpected error")

    async def _send_frame(
        self, frame: str, num_repeats: int = 0, gap_duration: float = 0.0
    ) -> None:
        """Write to the transport."""
        if self._transport is None:
            raise ProtocolSendFailed("Transport is not connected")

        # apply outbound regex
        frame = self._apply_regex(frame, self._outbound_regex)

        await self._transport.write_frame(frame)
        for _ in range(num_repeats - 1):
            await asyncio.sleep(gap_duration)
            await self._transport.write_frame(frame)

    def pkt_received(self, pkt: Packet) -> None:
        """A wrapper for self._pkt_received(pkt).

        Applies inbound regex modifications and tracks synchronization cycles
        before passing the packet to the internal receiver.

        :param pkt: The received Packet object to process.
        """
        # Use pkt._frame and prepend RSSI so from_port can correctly parse it
        raw_frame = pkt._frame
        hacked_frame = self._apply_regex(raw_frame, self._inbound_regex)

        if hacked_frame != raw_frame:
            with suppress(Exception):
                # Packet.from_port strictly expects the 3-character RSSI + space prefix
                pkt = Packet.from_port(
                    pkt.dtm, f"{pkt.rssi} {hacked_frame}"
                )  # Fallback to original packet if regex broke it

        # Track Sync Cycles
        if pkt.code == Code._1F09 and pkt.verb == I_ and pkt._len == 3:

            def is_pending(p: Packet) -> bool:
                """Check if a packet's sync cycle is still pending.

                :param p: The packet to evaluate.
                :return: True if the packet is within the pending window.
                """
                return bool(p.dtm + td(seconds=int(p.payload[2:6], 16) / 10) > dt_now())

            self._tracked_sync_cycles = deque(
                p
                for p in self._tracked_sync_cycles
                if p.src != pkt.src and is_pending(p)
            )
            self._tracked_sync_cycles.append(pkt)

        if _DBG_FORCE_LOG_PACKETS:
            _LOGGER.warning(f"Recv'd: {pkt._rssi} {pkt}")
        elif _LOGGER.getEffectiveLevel() > logging.DEBUG:
            _LOGGER.info(f"Recv'd: {pkt._rssi} {pkt}")
        else:
            _LOGGER.debug(f"Recv'd: {pkt._rssi} {pkt}")

        self._pkt_received(pkt)

    def _pkt_received(self, pkt: Packet) -> None:
        """Called by the Transport when a Packet is received."""
        try:
            msg = Message(pkt)  # should log all invalid msgs appropriately
        except Exception as exc:
            # We catch generic Exception here because validation failures
            # like PacketPayloadInvalid should never crash the reader loop.
            _LOGGER.debug(f"Dropped invalid packet during parsing: {exc}")
            return

        self._this_msg, self._prev_msg = msg, self._this_msg
        self._msg_received(msg)

    def _msg_received(self, msg: Message) -> None:
        """Pass any valid/wanted Messages to the client's callbacks.

        Also maintain _prev_msg, _this_msg attrs.
        """
        if self._msg_handler is not None:
            _LOGGER.debug(f"Dispatching valid message to handler: {msg}")
            self._msg_handler(msg)
        for callback, msg_filter in self._msg_handlers:
            if msg_filter is None or msg_filter(msg):
                callback(msg)


class _DeviceIdFilterMixin(_BaseProtocol):
    """Filter out any unwanted (but otherwise valid) packets via device ids."""

    def __init__(
        self,
        msg_handler: MsgHandlerT,
        /,
        *,
        enforce_include_list: bool = False,
        exclude_list: DeviceListT | None = None,
        include_list: DeviceListT | None = None,
    ) -> None:
        _BaseProtocol.__init__(self, msg_handler)

        exclude_list = exclude_list or {}
        include_list = include_list or {}

        self.enforce_include = enforce_include_list
        self._exclude = list(exclude_list.keys())
        self._include = list(include_list.keys())
        self._include += [ALL_DEV_ADDR.id, NON_DEV_ADDR.id]

        self._active_hgi: DeviceIdT | None = None
        # HACK: to disable_warnings if pkt source is static (e.g. a file/dict)
        # HACK: but a dynamic source (e.g. a port/MQTT) should warn if needed
        self._known_hgi = self._extract_known_hgi_id(
            include_list, disable_warnings=self.__class__.__name__ == "ReadProtocol"
        )

        self._foreign_gwys_lst: list[DeviceIdT] = []
        self._foreign_last_run = dt.now().date()

    @property
    def hgi_id(self) -> DeviceIdT:
        """Get the ID of the HGI handling the comms."""
        if not self._transport:
            return self._known_hgi or HGI_DEV_ADDR.id
        hgi = self._transport.get_extra_info(SZ_ACTIVE_HGI)
        return hgi or self._known_hgi or HGI_DEV_ADDR.id

    @staticmethod
    def _extract_known_hgi_id(
        include_list: DeviceListT,
        /,
        *,
        disable_warnings: bool = False,
        strict_checking: bool = False,
    ) -> DeviceIdT | None:
        """Return the device_id of the gateway specified in the include_list, if any.

        The 'Known' gateway is the predicted Active gateway, given the known_list.
        The 'Active' gateway is the USB device that is actually Tx/Rx-ing frames.

        The Known gateway ID should be the Active gateway ID, but does not have to
        match.

        Will send a warning if the include_list is configured incorrectly.
        """
        logger = _LOGGER.warning if not disable_warnings else _LOGGER.debug

        explicit_hgis = [
            k
            for k, v in include_list.items()
            if v.get(SZ_CLASS) in (DevType.HGI, DEV_TYPE_MAP[DevType.HGI])
        ]
        implicit_hgis = [
            k
            for k, v in include_list.items()
            if not v.get(SZ_CLASS) and k[:2] == DEV_TYPE_MAP._hex(DevType.HGI)
        ]

        if not explicit_hgis and not implicit_hgis:
            logger(
                f"The {SZ_KNOWN_LIST} SHOULD include exactly one gateway (HGI), "
                f"but does not (it should specify 'class: HGI')"
            )
            return None

        known_hgi = (explicit_hgis if explicit_hgis else implicit_hgis)[0]

        if include_list[known_hgi].get(SZ_CLASS) not in (
            DevType.HGI,
            DEV_TYPE_MAP[DevType.HGI],
        ):
            logger(
                f"The {SZ_KNOWN_LIST} SHOULD include exactly one gateway (HGI): "
                f"{known_hgi} should specify 'class: HGI', as 18: is also used for HVAC"
            )

        elif len(explicit_hgis) > 1:
            logger(
                f"The {SZ_KNOWN_LIST} SHOULD include exactly one gateway (HGI): "
                f"{known_hgi} is the chosen device id (why is there >1 HGI?)"
            )

        else:
            _LOGGER.debug(
                f"The {SZ_KNOWN_LIST} includes exactly one gateway (HGI): {known_hgi}"
            )

        if strict_checking:
            return known_hgi if [known_hgi] == explicit_hgis else None
        return known_hgi

    def _set_active_hgi(self, dev_id: DeviceIdT, by_signature: bool = False) -> None:
        """Set the Active Gateway (HGI) device_id.

        Send a warning if the include list is configured incorrectly.
        """
        assert self._active_hgi is None  # should only be called once

        msg = f"The active gateway '{dev_id}: {{ class: HGI }}' "
        msg += "(by signature)" if by_signature else "(by filter)"

        if dev_id not in self._exclude:
            self._active_hgi = dev_id

        if dev_id in self._exclude:
            _LOGGER.error(f"{msg} MUST NOT be in the {SZ_BLOCK_LIST}{TIP}")

        elif dev_id not in self._include:
            _LOGGER.warning(f"{msg} SHOULD be in the (enforced) {SZ_KNOWN_LIST}")

        elif not self.enforce_include:
            _LOGGER.info(f"{msg} is in the {SZ_KNOWN_LIST}, which SHOULD be enforced")

        else:
            _LOGGER.debug(f"{msg} is in the {SZ_KNOWN_LIST}")

    def _is_wanted_addrs(
        self, src_id: DeviceIdT, dst_id: DeviceIdT, sending: bool = False
    ) -> bool:
        """Return True if the packet is not to be filtered out.

        In any one packet, an excluded device_id 'trumps' an included device_id.
        """

        def warn_foreign_hgi(dev_id: DeviceIdT) -> None:
            current_date = dt.now().date()

            if self._foreign_last_run != current_date:
                self._foreign_last_run = current_date
                self._foreign_gwys_lst = []  # reset the list every 24h

            if dev_id in self._foreign_gwys_lst:
                return

            _LOGGER.warning(
                f"Device {dev_id} is potentially a Foreign gateway, "
                f"the Active gateway is {self._active_hgi}, "
                f"alternatively, is it a HVAC device?{TIP}"
            )
            self._foreign_gwys_lst.append(dev_id)

        for dev_id in dict.fromkeys((src_id, dst_id)):  # removes duplicates
            if dev_id in self._exclude:
                return False

            if dev_id == self._active_hgi:
                continue

            if dev_id in self._include:
                continue

            if sending and dev_id == HGI_DEV_ADDR.id:
                continue

            if self.enforce_include:
                return False

            if dev_id[:2] != DEV_TYPE_MAP.HGI:
                continue

            if self._active_hgi:
                warn_foreign_hgi(dev_id)

        return True

    def _pkt_received(self, pkt: Packet) -> None:
        if not self._is_wanted_addrs(pkt.src.id, pkt.dst.id):
            _LOGGER.debug("%s < Packet excluded by device_id filter", pkt)
            return
        super()._pkt_received(pkt)

    async def send_cmd(
        self,
        cmd: Command,
        /,
        *,
        gap_duration: float = DEFAULT_GAP_DURATION,
        num_repeats: int = DEFAULT_NUM_REPEATS,
        priority: Priority = Priority.DEFAULT,
        qos: QosParams | None = None,
    ) -> Packet:
        if not self._is_wanted_addrs(cmd.src.id, cmd.dst.id, sending=True):
            raise ProtocolError(f"Command excluded by device_id filter: {cmd}")
        return await super().send_cmd(
            cmd,
            gap_duration=gap_duration,
            num_repeats=num_repeats,
            priority=priority,
            qos=qos,
        )
