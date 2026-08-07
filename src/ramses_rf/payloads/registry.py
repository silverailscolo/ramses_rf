"""RAMSES RF - Dataclass Payload Registry.

This module maintains the O(1) opcode-to-payload-class lookup registry.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

from ramses_tx.const import Code

if TYPE_CHECKING:
    from .base import PayloadBase


class PayloadRegistry:
    """Registry managing mapping between RAMSES opcodes and PayloadBase classes."""

    def __init__(self) -> None:
        """Initialize an empty payload registry."""
        self._registry: dict[str, type[PayloadBase]] = {}

    def register(
        self, code: Code | str
    ) -> Callable[[type[PayloadBase]], type[PayloadBase]]:
        """Register a PayloadBase class for a RAMSES opcode.

        :param code: The Code enum or 4-character hex code string.
        :type code: Code | str
        :returns: Decorator function registering target payload class.
        :rtype: Callable[[type[PayloadBase]], type[PayloadBase]]
        """
        key = code.value if isinstance(code, Code) else str(code).upper()

        def decorator(cls: type[PayloadBase]) -> type[PayloadBase]:
            self._registry[key] = cls
            return cls

        return decorator

    def get(self, code: Code | str) -> type[PayloadBase] | None:
        """Retrieve registered PayloadBase class for an opcode.

        :param code: The Code enum or 4-character hex code string.
        :type code: Code | str
        :returns: Registered payload dataclass, or None if not found.
        :rtype: type[PayloadBase] | None
        """
        key = code.value if isinstance(code, Code) else str(code).upper()
        return self._registry.get(key)

    def clear(self) -> None:
        """Clear all registered payload classes."""
        self._registry.clear()

    def __contains__(self, code: Code | str) -> bool:
        """Check if an opcode is registered.

        :param code: The Code enum or 4-character hex code string.
        :type code: Code | str
        :returns: True if opcode is registered, False otherwise.
        :rtype: bool
        """
        key = code.value if isinstance(code, Code) else str(code).upper()
        return key in self._registry


# Global default registry instance
PAYLOAD_REGISTRY = PayloadRegistry()


def register_payload(
    code: Code | str,
) -> Callable[[type[PayloadBase]], type[PayloadBase]]:
    """Register a payload dataclass with the global registry.

    :param code: The Code enum or 4-character hex code string.
    :type code: Code | str
    :returns: Decorator function registering the payload class.
    :rtype: Callable[[type[PayloadBase]], type[PayloadBase]]
    """
    return PAYLOAD_REGISTRY.register(code)


def get_payload_class(code: Code | str) -> type[PayloadBase] | None:
    """Retrieve a registered payload dataclass from the global registry.

    :param code: The Code enum or 4-character hex code string.
    :type code: Code | str
    :returns: The registered payload class or None.
    :rtype: type[PayloadBase] | None
    """
    return PAYLOAD_REGISTRY.get(code)
