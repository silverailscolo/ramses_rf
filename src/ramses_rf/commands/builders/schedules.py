"""RAMSES RF - Schedule command intent to L3 payload translation."""

from ramses_rf.commands.builders.helpers import resolve_addrs
from ramses_rf.commands.core import Command
from ramses_rf.payloads.heating import ScheduleFragmentPayload
from ramses_tx.const import DEFAULT_NUM_REPEATS, RQ, W_, Code, Priority
from ramses_tx.dtos import CommandDTO


def build_get_schedule_version(intent: Command) -> CommandDTO:
    """Translate a GET_SCHEDULE_VERSION intent into a CommandDTO.

    :param intent: The GET_SCHEDULE_VERSION intent.
    :return: A populated CommandDTO.
    """
    addr1, addr2, addr3 = resolve_addrs(intent.src, intent.dst)

    return CommandDTO(
        verb=RQ,
        addr1=addr1,
        addr2=addr2,
        addr3=addr3,
        code=Code._0006,
        payload="00",
        priority=Priority.DEFAULT,
        num_repeats=DEFAULT_NUM_REPEATS,
    )


def build_get_schedule_fragment(intent: Command) -> CommandDTO:
    """Translate a GET_SCHEDULE_FRAGMENT intent into a CommandDTO.

    :param intent: The GET_SCHEDULE_FRAGMENT intent. It is expected to
        contain `zone_index` / `zone_index` (str | int), `fragment_number` / `frag_number` (int, default 1),
        and `total_fragments` / `total_frags` (int, default 0) in its data dictionary.
    :return: A populated CommandDTO.
    """
    zone_index = intent.get("zone_index", intent.get("zone_index"))
    frag_number = intent.get(
        "fragment_number", intent.get("frag_number", intent.get("frag_num", 1))
    )
    total_frags = intent.get(
        "total_fragments", intent.get("total_frags", intent.get("frag_cnt", 0))
    )

    if zone_index is None:
        raise ValueError("Missing 'zone_index'/'zone_index' in intent data")

    if frag_number == 0:
        raise ValueError(f"frag_number={frag_number}, but it is 1-indexed")
    elif frag_number == 1 and total_frags != 0:
        raise ValueError(
            f"total_frags={total_frags}, but must be 0 when frag_number=1"
        )
    elif frag_number > total_frags and total_frags != 0:
        raise ValueError(
            f"frag_number={frag_number}, but must be <= total_frags={total_frags}"
        )

    payload = ScheduleFragmentPayload(
        zone_index=zone_index,
        frag_number=frag_number,
        total_frags=total_frags,
        fragment_bytes=b"",
    ).hex()

    addr1, addr2, addr3 = resolve_addrs(intent.src, intent.dst)

    return CommandDTO(
        verb=RQ,
        addr1=addr1,
        addr2=addr2,
        addr3=addr3,
        code=Code._0404,
        payload=payload,
        priority=Priority.DEFAULT,
        num_repeats=DEFAULT_NUM_REPEATS,
    )


def build_set_schedule_fragment(intent: Command) -> CommandDTO:
    """Translate a SET_SCHEDULE_FRAGMENT intent into a CommandDTO.

    :param intent: The SET_SCHEDULE_FRAGMENT intent. It is expected to
        contain `zone_index` / `zone_index` (str | int), `fragment_number` / `frag_num` (int),
        `total_fragments` / `frag_cnt` (int), and `fragment` (str) in its data dictionary.
    :return: A populated CommandDTO.
    """
    zone_index = intent.get("zone_index", intent.get("zone_index"))
    frag_num = intent.get(
        "fragment_number", intent.get("frag_num", intent.get("frag_number"))
    )
    frag_cnt = intent.get(
        "total_fragments", intent.get("frag_cnt", intent.get("total_frags"))
    )
    fragment = intent.get("fragment")

    if (
        zone_index is None
        or frag_num is None
        or frag_cnt is None
        or fragment is None
    ):
        raise ValueError("Missing required arguments in intent data")

    if frag_num == 0:
        raise ValueError(f"frag_num={frag_num}, but it is 1-indexed")
    elif frag_num > frag_cnt:
        raise ValueError(
            f"frag_num={frag_num}, but must be <= frag_cnt={frag_cnt}"
        )

    frag_bytes = bytes.fromhex(fragment)
    payload = ScheduleFragmentPayload(
        zone_index=zone_index,
        frag_number=frag_num,
        total_frags=frag_cnt,
        fragment_bytes=frag_bytes,
    ).hex()

    addr1, addr2, addr3 = resolve_addrs(intent.src, intent.dst)

    return CommandDTO(
        verb=W_,
        addr1=addr1,
        addr2=addr2,
        addr3=addr3,
        code=Code._0404,
        payload=payload,
        priority=Priority.DEFAULT,
        num_repeats=DEFAULT_NUM_REPEATS,
    )
