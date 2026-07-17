"""RAMSES RF - Outbound Command Dispatcher."""

from ramses_rf.commands.builders import build_dto
from ramses_rf.commands.core import Command
from ramses_rf.interfaces import GatewayInterface
from ramses_tx import Command as LegacyCommand, Packet, Priority
from ramses_tx.dtos import CommandDTO
from ramses_tx.typing import PayloadT


class CommandDispatcher:
    """Dispatches L7 Command intents to the L3 modem.

    Implements CQRS pattern by separating intent generation from payload
    construction and modem dispatch.
    """

    def __init__(self, gwy: GatewayInterface) -> None:
        """Initialize the dispatcher with a reference to the Gateway.

        :param gwy: The main gateway instance for sending L3 payloads.
        """
        self._gwy = gwy

    async def send(self, intent: Command) -> Packet:
        """Translate and send a high-level intent over the RF network.

        :param intent: The high-level intent to execute.
        :return: The resulting Packet from the modem (or an RP if requested).
        """
        dto: CommandDTO = build_dto(intent)

        # TEMPORARY SHIM: We must construct a legacy `ramses_tx.Command`
        # from the DTO because Gateway.async_send_cmd currently only
        # accepts `ramses_tx.Command`.
        # In PR 2, Gateway will accept CommandDTO directly.
        legacy_cmd = LegacyCommand._from_attrs(
            dto.verb,
            dto.code,
            PayloadT(dto.payload),
            addr0=dto.addr1,
            addr1=dto.addr2,
            addr2=dto.addr3,
        )

        return await self._gwy.async_send_cmd(
            legacy_cmd,
            priority=Priority(dto.priority),
        )
