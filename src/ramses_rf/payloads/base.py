"""RAMSES RF - Dataclass Payload Layer base interface.

This module defines the abstract base class and protocol contract
for all RAMSES packet payload dataclasses.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Self

from .adapters import payload_to_dict


@dataclass(frozen=True, slots=True)
class PayloadBase(ABC):
    """Abstract base class for RAMSES packet payload dataclasses.

    All payload classes must inherit from this class, specify slots
    and frozen, and implement binary decoding (from_bytes) and
    encoding (to_bytes) methods.
    """

    @classmethod
    @abstractmethod
    def from_bytes(
        cls, raw_data: bytes
    ) -> Self | list[Self] | PayloadBase | list[PayloadBase]:
        """Unpack raw binary payload bytes into typed dataclass instance(s).

        :param raw_data: Raw byte string representation of payload.
        :type raw_data: bytes
        :returns: A typed payload dataclass instance or list of instances.
        :rtype: Self | list[Self] | PayloadBase | list[PayloadBase]
        """
        ...

    @abstractmethod
    def to_bytes(self) -> bytes:
        """Pack payload attributes into a raw byte string for transmission.

        :returns: Packed raw byte string representation of the payload.
        :rtype: bytes
        """
        ...

    def to_dict(self, *args: Any, **kwargs: Any) -> Any:
        """Convert payload dataclass to legacy dictionary format.

        :param args: Optional positional arguments for compatibility.
        :param kwargs: Optional keyword arguments for compatibility.
        :returns: Dictionary or list representation of the payload.
        :rtype: Any
        """
        return payload_to_dict(self)

    def __getitem__(self, key: str) -> Any:
        """Access payload field via dictionary lookup for legacy compatibility.

        :param key: Field name key.
        :type key: str
        :returns: Decoded field value.
        :rtype: Any
        :raises KeyError: If key is not in dictionary.
        """
        d = self.to_dict()
        if isinstance(d, dict):
            return d[key]
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        """Check if key exists in payload dictionary.

        :param key: Field name key.
        :type key: object
        :returns: True if key exists, False otherwise.
        :rtype: bool
        """
        d = self.to_dict()
        return key in d if isinstance(d, dict) else False

    def get(self, key: str, default: Any = None) -> Any:
        """Get value for key with optional fallback default.

        :param key: Field name key.
        :type key: str
        :param default: Fallback default value.
        :type default: Any
        :returns: Field value or default.
        :rtype: Any
        """
        d = self.to_dict()
        return d.get(key, default) if isinstance(d, dict) else default

    def keys(self) -> Any:
        """Return dictionary keys view for legacy compatibility.

        :returns: Keys view.
        :rtype: Any
        """
        d = self.to_dict()
        return d.keys() if isinstance(d, dict) else {}.keys()

    def values(self) -> Any:
        """Return dictionary values view for legacy compatibility.

        :returns: Values view.
        :rtype: Any
        """
        d = self.to_dict()
        return d.values() if isinstance(d, dict) else {}.values()

    def items(self) -> Any:
        """Return dictionary items view for legacy compatibility.

        :returns: Items view.
        :rtype: Any
        """
        d = self.to_dict()
        return d.items() if isinstance(d, dict) else {}.items()

    def hex(self) -> str:
        """Return uppercase ASCII hex representation of binary payload.

        :returns: Uppercase hex string payload representation.
        :rtype: str
        """
        return self.to_bytes().hex().upper()


def parse_idx(idx: int | str) -> int:
    """Parse integer or hex string zone/domain index into a byte integer.

    :param idx: Zone/domain index integer or hex string
        (e.g. 1, "01", "HW", "FA").
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
