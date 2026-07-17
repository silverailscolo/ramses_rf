"""RAMSES RF - Faultlog command intent to L3 payload translation."""

from ramses_rf.commands.builders.helpers import resolve_addrs
from ramses_rf.commands.core import Command
from ramses_tx.const import DEFAULT_NUM_REPEATS, RQ, Code, Priority
from ramses_tx.dtos import CommandDTO


def build_get_faultlog_entry(intent: Command) -> CommandDTO:
    """Translate a GET_FAULTLOG_ENTRY intent into a CommandDTO.

    :param intent: The GET_FAULTLOG_ENTRY intent. It is expected to
        contain the `log_idx` key (int | str) in its data dictionary.
    :return: A populated CommandDTO.
    """
    log_idx = intent.get("log_idx")

    if log_idx is None:
        raise ValueError("Missing 'log_idx' in intent data")

    log_idx_int = log_idx if isinstance(log_idx, int) else int(log_idx, 16)
    payload = f"{log_idx_int:06X}"
    addr1, addr2, addr3 = resolve_addrs(intent.src, intent.dst)

    return CommandDTO(
        verb=RQ,
        addr1=addr1,
        addr2=addr2,
        addr3=addr3,
        code=Code._0418,
        payload=payload,
        priority=Priority.DEFAULT,
        num_repeats=DEFAULT_NUM_REPEATS,
    )
