"""RAMSES RF - Dataclass Payload Layer base interface.

This module defines the abstract base class and protocol contract for all RAMSES
packet payload dataclasses.
"""

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
    def from_bytes(cls, raw_data: bytes) -> Self:
        """Unpack raw binary payload bytes into a typed dataclass instance.

        :param raw_data: Raw byte string representation of the payload.
        :type raw_data: bytes
        :returns: A typed payload dataclass instance.
        :rtype: Self
        """
        ...

    @abstractmethod
    def to_bytes(self) -> bytes:
        """Pack payload attributes into a raw byte string layout for transmission.

        :returns: Packed raw byte string representation of the payload.
        :rtype: bytes
        """
        ...
