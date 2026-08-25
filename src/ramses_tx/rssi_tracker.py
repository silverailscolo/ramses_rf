"""RSSI tracking per HGI (transport layer).

Tracks the last N RSSI readings per device that the HGI (gateway's
CC1101 receiver) has heard.  RSSI is a L1/L2 measurement made by the
receiver, not the sender, so it lives on the transport side.

The tracker maintains a small ring buffer per device (default 3
readings).  This is intentionally **not** a running average or EMA —
a flat window of the last N readings is predictable, time-agnostic,
and handles both degradation and recovery cleanly.

See: https://github.com/ramses-rf/ramses_cc/issues/1047
"""

from __future__ import annotations

from collections import deque
from datetime import datetime as dt
from typing import Final

# Default window size — last N RSSI readings per device.
# A small window (3) balances responsiveness with noise immunity.
DEFAULT_WINDOW_SIZE: Final[int] = 3

# Sentinel RSSI values that carry no signal information.
_RSSI_SENTINELS: Final[frozenset[str]] = frozenset({"", "...", "---", "///"})


class RssiTracker:
    """Per-HGI RSSI tracker maintaining the last N readings per device.

    Lives on the transport side (one instance per HGI/gateway).  The
    domain layer queries ``best_rssi_for(device_id)`` to compute
    communication quality across all HGIs.

    :param window_size: Number of recent readings to retain per device.
    """

    __slots__ = ("_window_size", "_readings")

    def __init__(self, window_size: int = DEFAULT_WINDOW_SIZE) -> None:
        """Initialise the tracker.

        :param window_size: Readings to keep per device (default 3).
        """
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        self._window_size: int = window_size
        # device_id -> deque of (rssi_dBm, timestamp)
        self._readings: dict[str, deque[tuple[int, dt]]] = {}

    def record(self, device_id: str, rssi: str | int, timestamp: dt) -> None:
        """Record an RSSI reading for a device.

        Silently ignores sentinel values (``...``, ``---``, etc.) and
        unparsable strings — these carry no signal information.

        :param device_id: The device that was heard (source address).
        :param rssi: RSSI value as string (from PacketDTO) or int.
        :param timestamp: When the packet was received.
        """
        dBm = _parse_rssi(rssi)
        if dBm is None:
            return

        buf = self._readings.get(device_id)
        if buf is None:
            buf = deque(maxlen=self._window_size)
            self._readings[device_id] = buf
        buf.append((dBm, timestamp))

    def best_rssi_for(self, device_id: str) -> int | None:
        """Return the strongest (highest) RSSI from the last N readings.

        :param device_id: The device to query.
        :returns: Best RSSI in dBm (negative), or ``None`` if no
            readings exist for the device.
        """
        buf = self._readings.get(device_id)
        if not buf:
            return None
        return max(rssi for rssi, _ in buf)

    def last_seen(self, device_id: str) -> dt | None:
        """Return the timestamp of the most recent reading for a device.

        :param device_id: The device to query.
        :returns: Timestamp of last reading, or ``None``.
        """
        buf = self._readings.get(device_id)
        if not buf:
            return None
        return buf[-1][1]

    def readings_for(self, device_id: str) -> list[int]:
        """Return the raw list of recent RSSI readings for a device.

        :param device_id: The device to query.
        :returns: List of recent RSSI values in dBm (oldest first),
            or an empty list.
        """
        buf = self._readings.get(device_id)
        if not buf:
            return []
        return [rssi for rssi, _ in buf]

    def known_devices(self) -> frozenset[str]:
        """Return the set of device IDs that have at least one reading.

        :returns: Frozenset of device IDs with recorded RSSI data.
        """
        return frozenset(self._readings)

    def clear(self) -> None:
        """Clear all recorded readings."""
        self._readings.clear()


def _parse_rssi(rssi: str | int) -> int | None:
    """Parse an RSSI value to signed dBm int.

    Accepts signed dBm (already normalised by ``packet.py``) as either
    a string (``"-74"``) or int (``-74``).  Sentinel values and
    unparsable strings return ``None``.

    :param rssi: RSSI value from PacketDTO or caller.
    :returns: Signed dBm int, or ``None`` if no signal info.
    """
    if isinstance(rssi, int):
        return rssi
    if not isinstance(rssi, str) or rssi in _RSSI_SENTINELS:
        return None
    try:
        return int(rssi)
    except ValueError:
        return None
