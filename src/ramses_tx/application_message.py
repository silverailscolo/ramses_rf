#!/usr/bin/env python3

"""RAMSES RF - The Application Message module."""

from __future__ import annotations

from datetime import timedelta as td
from typing import TYPE_CHECKING, Any

from .const import RQ, Code
from .message import Message

if TYPE_CHECKING:
    from .engine import Engine


class ApplicationMessage(Message):
    """Application-level message extended with gateway context and
    expiration.
    """

    CANT_EXPIRE: float = -1.0  # sentinel value for fraction_expired
    HAS_EXPIRED: float = 2.0  # fraction_expired >= HAS_EXPIRED
    IS_EXPIRING: float = 0.8  # fraction_expired >= 0.8 (and < HAS_EXPIRED)

    _engine: Engine | None = None
    _fraction_expired: float | None = None
    _gwy: Any | None = None

    @classmethod
    def from_message(cls, msg: Message) -> ApplicationMessage:
        """Factory to safely promote a transport Message to an
        ApplicationMessage.
        """
        # Initialize the subclass identically to how the base class initializes
        return cls(msg._pkt)

    def bind_context(self, gwy: Any) -> None:
        """Explicitly assign the application context (gateway).

        :param gwy: The application context (gateway) to associate.
        :type gwy: Any
        """
        self._gwy = gwy

    def set_gateway(self, gwy: Engine) -> None:
        """Set the gateway (engine) instance for this message.

        :param gwy: The gateway (engine) instance to associate.
        :type gwy: Engine
        """
        self._engine = gwy

    @property
    def _expired(self) -> bool:
        """Return True if the message is dated, False otherwise.

        :return: True if the message is dated, False otherwise.
        :rtype: bool
        """
        # Safest fallback for unit tests without an engine
        now = self._engine._dt_now() if self._engine else self.dtm

        # 1. Enforce the hard 7-day expiration limit
        if now - self.dtm > td(days=7):
            return True

        def fraction_expired(lifespan: td) -> float:
            """Calculate the fraction of expired normal lifespan.

            :param lifespan: The lifespan of the message.
            :type lifespan: td
            :return: The expired fraction.
            :rtype: float
            """
            return float((now - self.dtm - td(seconds=3)) / lifespan)

        # 1. Look for easy win...
        if self._fraction_expired is not None:
            if self._fraction_expired == self.CANT_EXPIRE:
                return False
            if self._fraction_expired >= self.HAS_EXPIRED:
                return True

        # 2. Need to update the fraction_expired...
        # sync_cycle is a special case
        if self.code == Code._1F09 and self.verb != RQ:
            # RQs won't have remaining_seconds, RP/Ws have only partial
            # cycle times
            rem_secs = getattr(self.payload, "remaining_seconds", None)
            if rem_secs is None and isinstance(self.payload, dict):
                rem_secs = self.payload.get("remaining_seconds", 0)

            self._fraction_expired = fraction_expired(
                td(seconds=float(rem_secs or 0)),
            )

        # Can't expire
        elif getattr(self._pkt, "_lifespan", None) is False:
            self._fraction_expired = self.CANT_EXPIRE

        # Can't expire
        elif getattr(self._pkt, "_lifespan", None) is True:
            raise NotImplementedError("Lifespan True not implemented")

        else:
            lifespan = getattr(self._pkt, "_lifespan", None)
            assert isinstance(lifespan, td)
            self._fraction_expired = fraction_expired(lifespan)

        return self._fraction_expired >= self.HAS_EXPIRED
