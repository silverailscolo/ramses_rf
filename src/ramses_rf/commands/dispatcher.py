"""RAMSES RF - Outbound Command Dispatcher."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from ramses_rf.commands.builders import build_dto
from ramses_rf.commands.core import Command
from ramses_rf.interfaces import GatewayInterface
from ramses_rf.messages import Message
from ramses_tx import Priority
from ramses_tx.const import DEFAULT_WAIT_FOR_REPLY
from ramses_tx.dtos import CommandDTO
from ramses_tx.exceptions import ProtocolSendFailed

if TYPE_CHECKING:
    from ramses_tx import Packet

_QOS_TX_LIMIT = 12
_LOGGER = logging.getLogger(__name__)


class CommandDispatcher:
    """Dispatches L7 Command intents to the L3 modem.

    Implements CQRS pattern by separating intent generation from payload
    construction and modem dispatch.
    """

    def __init__(self, gateway: GatewayInterface) -> None:
        """Initialize the dispatcher with a reference to the Gateway.

        :param gateway: The main gateway instance for sending L3 payloads.
        :type gateway: GatewayInterface
        """
        self._gateway = gateway

    def _check_transmission_policy(self, intent: Command) -> None:
        """Validate intent against destination device policies before transmission.

        :param intent: The command intent to evaluate.
        :type intent: Command
        :raises ProtocolSendFailed: If destination device is unreachable/deprecated.
        """
        registry = getattr(self._gateway, "device_registry", None)
        if registry is None:
            return

        target_dev = getattr(registry, "device_by_id", {}).get(intent.dst.id)
        if target_dev is None:
            return

        # 1. Check if unreachable device has exceeded transmission limit
        qos_count = getattr(target_dev, "_qos_tx_count", 0)
        if isinstance(qos_count, int) and qos_count > _QOS_TX_LIMIT:
            _LOGGER.warning(
                "%s < Sending was deprecated for %s", intent, target_dev
            )
            raise ProtocolSendFailed(
                f"Sending deprecated for {target_dev} (exceeded tx limit)"
            )

        # 2. Check if destination is a real battery-powered device
        is_faked = getattr(target_dev, "is_faked", False)
        has_battery = getattr(target_dev, "has_battery", None)
        is_battery_state = False
        if callable(has_battery):
            # Synchronous check if BatteryState is inherited
            from ramses_rf.devices.dev_base import BatteryState

            is_battery_state = isinstance(target_dev, BatteryState)

        if is_battery_state and not is_faked:
            _LOGGER.info(
                "%s < Sending inadvisable for %s (it has a battery)",
                intent,
                target_dev,
            )

    async def send(
        self,
        intent: Command,
        *,
        priority: Priority | None = None,
        wait_for_reply: bool | None = DEFAULT_WAIT_FOR_REPLY,
    ) -> Message:
        """Translate and send a high-level intent over the RF network.

        :param intent: The high-level intent to execute.
        :type intent: Command
        :param priority: Priority override for transmission.
        :type priority: Priority | None
        :param wait_for_reply: True if the L7 FSM should await a reply.
        :type wait_for_reply: bool | None
        :returns: The resulting Message domain object.
        :rtype: Message
        """
        self._check_transmission_policy(intent)
        dto: CommandDTO = build_dto(intent)
        conv_mgr = self._gateway.conversation_manager

        if wait_for_reply and conv_mgr is not None:
            rply_fut = await conv_mgr.track_intent(intent, dto)
            await self._gateway._async_send_dto(
                dto,
                priority=priority
                if priority is not None
                else Priority(dto.priority),
            )
            return await rply_fut

        packet: Packet = await self._gateway._async_send_dto(
            dto,
            priority=priority
            if priority is not None
            else Priority(dto.priority),
        )
        msg = Message._from_packet(packet)
        msg._pkt = packet  # type: ignore[attr-defined]
        return msg

    def send_background(
        self,
        intent: Command,
        *,
        priority: Priority | None = None,
        wait_for_reply: bool | None = DEFAULT_WAIT_FOR_REPLY,
    ) -> asyncio.Task[Message]:
        """Schedule command intent transmission as a background task.

        :param intent: The high-level intent to execute.
        :type intent: Command
        :param priority: Priority override for transmission.
        :type priority: Priority | None
        :param wait_for_reply: True if the L7 FSM should await a reply.
        :type wait_for_reply: bool | None
        :returns: An asyncio Task resolving to the resulting Message.
        :rtype: asyncio.Task[Message]
        """
        coro = self.send(
            intent,
            priority=priority,
            wait_for_reply=wait_for_reply,
        )
        loop = (
            getattr(self._gateway, "_loop", None) or asyncio.get_running_loop()
        )
        task = loop.create_task(coro)

        def _clear_exc(fut: asyncio.Task[Any]) -> None:
            if not fut.cancelled() and fut.exception():
                _LOGGER.debug(
                    "Background intent task failed: %s", fut.exception()
                )

        task.add_done_callback(_clear_exc)
        add_task = getattr(self._gateway, "add_task", None)
        if callable(add_task):
            add_task(task)
        return task
