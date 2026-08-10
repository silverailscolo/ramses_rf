"""RAMSES RF - Dataclass Payload Layer base interface.

This module defines the abstract base class and protocol contract for all RAMSES
packet payload dataclasses.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Self


@dataclass(frozen=True, slots=True)
class PayloadBase(ABC):
    """Abstract base class for RAMSES packet payload dataclasses.

    All payload classes must inherit from this class, specify slots and frozen,
    and implement binary decoding (from_bytes) and encoding (to_bytes) methods.
    """

    @classmethod
    @abstractmethod
    def from_bytes(
        cls, raw_data: bytes
    ) -> Self | list[Self] | PayloadBase | list[PayloadBase]:
        """Unpack raw binary payload bytes into typed dataclass instance(s).

        :param raw_data: Raw byte string representation of the payload.
        :type raw_data: bytes
        :returns: A typed payload dataclass instance or list of instances.
        :rtype: Self | list[Self] | PayloadBase | list[PayloadBase]
        """
        ...

    @abstractmethod
    def to_bytes(self) -> bytes:
        """Pack payload attributes into a raw byte string layout for transmission.

        :returns: Packed raw byte string representation of the payload.
        :rtype: bytes
        """
        ...

    def hex(self) -> str:
        """Return uppercase ASCII hex representation of binary payload.

        :returns: Uppercase hex string payload representation.
        :rtype: str
        """
        return self.to_bytes().hex().upper()


def parse_idx(idx: int | str) -> int:
    """Parse integer or hex string zone/domain index into a byte integer.

    :param idx: Zone/domain index integer or hex string (e.g. 1, "01", "HW", "FA").
    :type idx: int | str
    :returns: Index as an unsigned 8-bit integer.
    :rtype: int
    :raises ValueError: If idx is an invalid index value.
    """
    if isinstance(idx, int):
        if not (0 <= idx <= 255):
            raise ValueError(f"Invalid zone index: {idx}")
        return idx
    if idx == "HW":
        return 0xFA
    result = int(idx, 16)
    if not (0 <= result <= 255):
        raise ValueError(f"Invalid zone index: {idx}")
    return result
