"""RAMSES RF - Intent-to-DTO Translation Helpers."""

from ramses_rf.address import Address


def resolve_addrs(src: Address, dst: Address) -> tuple[str, str, str]:
    """Resolve logical source and destination to positional MAC addresses.

    :param src: Logical source of the command.
    :param dst: Logical target of the command.
    :return: A tuple of (addr1, addr2, addr3) for the L3 CommandDTO.
    """
    if src.id == dst.id:
        return src.id, "--:------", dst.id
    return src.id, dst.id, "--:------"
