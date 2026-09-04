#!/usr/bin/env python3
"""RAMSES RF - Interfaces for the RAMSES-II protocol stack."""

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .dtos import CommandDTO
    from .packet import Packet
    from .typing import QosParams


class TransportInterface(ABC):
    """Interface for the Packet Transport layer."""

    @abstractmethod
    def close(self) -> None:
        """Close the transport."""

    @abstractmethod
    def get_extra_info(self, name: str, default: Any = None) -> Any:
        """Get extra information about the transport."""

    @abstractmethod
    async def send_frame(self, frame: str) -> None:
        """Send a frame."""

    @abstractmethod
    async def write_frame(self, frame: str) -> None:
        """Write a frame (legacy alias for send_frame)."""


class ProtocolInterface(ABC, asyncio.Protocol):
    """Interface for the RAMSES-II Protocol layer."""

    @abstractmethod
    def connection_made(
        self, transport: Any, /, *, ramses: bool = False
    ) -> None:
        """Handle connection made event."""

    @abstractmethod
    def connection_lost(self, error: Exception | None) -> None:
        """Handle connection lost event."""

    @abstractmethod
    def pause_writing(self) -> None:
        """Pause writing."""

    @abstractmethod
    def packet_received(self, packet: "Packet") -> None:
        """Receive a packet."""

    @abstractmethod
    def resume_writing(self) -> None:
        """Resume writing."""

    @abstractmethod
    async def send_cmd(
        self,
        command: "CommandDTO",
        /,
        *,
        qos: "QosParams | None" = None,
    ) -> "Packet | None":
        """Send a command."""

    @abstractmethod
    async def wait_for_connection_made(
        self, timeout: float = 1.0
    ) -> TransportInterface:
        """Wait for connection_made to be called."""

    @abstractmethod
    def set_regex_rules(self, rules: Any) -> None:
        """Set regex rules on the protocol."""
