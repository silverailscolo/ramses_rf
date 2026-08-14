"""RAMSES RF - Outbound Command Dispatcher."""

from ramses_rf.commands.builders import build_dto
from ramses_rf.commands.core import Command
from ramses_rf.interfaces import GatewayInterface
from ramses_rf.messages import Message
from ramses_tx import Priority
from ramses_tx.const import DEFAULT_WAIT_FOR_REPLY
from ramses_tx.dtos import CommandDTO


class CommandDispatcher:
    """Dispatches L7 Command intents to the L3 modem.

    Implements CQRS pattern by separating intent generation from payload
    construction and modem dispatch.
    """

    def __init__(self, gateway: GatewayInterface) -> None:
        """Initialize the dispatcher with a reference to the Gateway.

        :param gateway: The main gateway instance for sending L3 payloads.
        """
        self._gateway = gateway

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
        dto: CommandDTO = build_dto(intent)
        conv_mgr = self._gateway.conversation_manager

        if wait_for_reply and conv_mgr is not None:
            rply_fut = await conv_mgr.track_intent(intent, dto)
            await self._gateway.async_send_cmd(
                dto,
                priority=priority if priority is not None else Priority(dto.priority),
            )
            return await rply_fut

        packet = await self._gateway.async_send_cmd(
            dto,
            priority=priority if priority is not None else Priority(dto.priority),
        )
        return Message._from_pkt(packet)
