#!/usr/bin/env python3
"""RAMSES RF - Helper functions for packet transports."""

from __future__ import annotations

import logging
import re
import warnings
from string import printable

from ..const import I_, RP, RQ, W_

_LOGGER = logging.getLogger(__name__)


def _normalise(packet_line: str) -> str:
    """Perform any (transparent) frame-level hacks, as required at (near-)RF layer.

    Goals:
      - ensure an evofw3 provides the same output as a HGI80 (none, presently)
      - handle 'strange' packets (e.g. ``I|08:|0008``)

    :param packet_line: The raw packet string from the hardware.
    :type packet_line: str
    :return: The normalized packet string.
    :rtype: str
    """
    # ramses_esp-specific bugs, see: https://github.com/IndaloTech/ramses_esp/issues/1
    if "\r\r" in packet_line or packet_line.startswith(" 000"):
        warnings.warn(
            "Legacy ramses_esp <0.4.0 frame normalization is deprecated and will be removed in a future release.",
            DeprecationWarning,
            stacklevel=2,
        )
    packet_line = re.sub("\r\r", "\r", packet_line)
    if packet_line[:4] == " 000":
        packet_line = packet_line[1:]
    elif packet_line[:2] in (I_, RQ, RP, W_):
        packet_line = ""

    # pseudo-RAMSES-II packets (encrypted payload?)...
    if (
        packet_line[10:14] in (" 08:", " 31:")
        and packet_line[-16:] == "* Checksum error"
    ):
        packet_line = packet_line[:-17] + " # Checksum error (ignored)"

    # remove any "/r/n" (leading whitespeace is a problem for commands, but not packets)
    return packet_line.strip()


def _str(value: bytes) -> str:
    """Decode bytes to a string, ignoring non-printable characters.

    :param value: The bytes to decode.
    :type value: bytes
    :return: The decoded string.
    :rtype: str
    """
    try:
        result = "".join(
            c for c in value.decode("ascii", errors="strict") if c in printable
        )
    except UnicodeDecodeError:
        _LOGGER.warning("%s < Can't decode bytestream (ignoring)", value)
        return ""
    return result
