"""RAMSES RF - Opentherm command intent to L3 payload translation."""

from ramses_rf.commands.builders.helpers import resolve_addrs
from ramses_rf.commands.core import Command
from ramses_rf.protocol.opentherm import parity
from ramses_tx.const import DEFAULT_NUM_REPEATS, RQ, Code, Priority
from ramses_tx.dtos import CommandDTO


def build_get_opentherm_data(intent: Command) -> CommandDTO:
    """Translate a GET_OPENTHERM_DATA intent into a CommandDTO.

    :param intent: The GET_OPENTHERM_DATA intent. It is expected to
        contain the `msg_id` key (int | str) in its data dictionary.
    :return: A populated CommandDTO.
    """
    msg_id = intent.get("msg_id")

    if msg_id is None:
        raise ValueError("Missing 'msg_id' in intent data")

    msg_id_int = msg_id if isinstance(msg_id, int) else int(msg_id, 16)
    payload = (
        f"0080{msg_id_int:02X}0000"
        if parity(msg_id_int)
        else f"0000{msg_id_int:02X}0000"
    )
    addr1, addr2, addr3 = resolve_addrs(intent.src, intent.dst)

    return CommandDTO(
        verb=RQ,
        addr1=addr1,
        addr2=addr2,
        addr3=addr3,
        code=Code._3220,
        payload=payload,
        priority=Priority.DEFAULT,
        num_repeats=DEFAULT_NUM_REPEATS,
    )
