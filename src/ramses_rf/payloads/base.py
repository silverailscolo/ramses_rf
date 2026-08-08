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
