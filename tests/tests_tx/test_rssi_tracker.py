"""Tests for the RssiTracker (transport-layer RSSI tracking per HGI).

See: https://github.com/ramses-rf/ramses_cc/issues/1047
"""

from __future__ import annotations

from datetime import UTC, datetime as dt

import pytest

from ramses_tx.rssi_tracker import RssiTracker


@pytest.fixture
def now() -> dt:
    """Fixed timestamp for deterministic tests."""
    return dt(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


class TestRssiTracker:
    """Unit tests for RssiTracker."""

    def test_record_and_best_rssi(self, now: dt) -> None:
        """Basic recording and best_rssi retrieval."""
        tracker = RssiTracker(window_size=3)
        tracker.record("04:123456", "-70", now)
        tracker.record("04:123456", "-65", now)
        tracker.record("04:123456", "-72", now)

        # Best (strongest = highest dBm) of last 3
        assert tracker.best_rssi_for("04:123456") == -65

    def test_window_eviction(self, now: dt) -> None:
        """Old readings are evicted when window is full."""
        tracker = RssiTracker(window_size=3)
        tracker.record("04:123456", "-50", now)
        tracker.record("04:123456", "-60", now)
        tracker.record("04:123456", "-70", now)
        tracker.record("04:123456", "-80", now)

        # Only last 3 readings: -60, -70, -80
        readings = tracker.readings_for("04:123456")
        assert readings == [-60, -70, -80]
        assert tracker.best_rssi_for("04:123456") == -60

    def test_degradation_detection(self, now: dt) -> None:
        """Window detects signal degradation (e.g. door closing)."""
        tracker = RssiTracker(window_size=3)
        # Good signal for a while
        tracker.record("04:123456", "-55", now)
        tracker.record("04:123456", "-56", now)
        tracker.record("04:123456", "-54", now)
        assert tracker.best_rssi_for("04:123456") == -54

        # Door closes — signal degrades
        tracker.record("04:123456", "-90", now)
        tracker.record("04:123456", "-92", now)
        tracker.record("04:123456", "-88", now)
        # Old good readings evicted, now all weak
        assert tracker.best_rssi_for("04:123456") == -88

    def test_recovery_detection(self, now: dt) -> None:
        """Window detects signal recovery (e.g. door opening)."""
        tracker = RssiTracker(window_size=3)
        tracker.record("04:123456", "-90", now)
        tracker.record("04:123456", "-92", now)
        tracker.record("04:123456", "-88", now)
        assert tracker.best_rssi_for("04:123456") == -88

        # Door opens — signal recovers
        tracker.record("04:123456", "-55", now)
        tracker.record("04:123456", "-56", now)
        tracker.record("04:123456", "-54", now)
        assert tracker.best_rssi_for("04:123456") == -54

    def test_multiple_devices(self, now: dt) -> None:
        """Each device has independent tracking."""
        tracker = RssiTracker(window_size=3)
        tracker.record("04:111111", "-70", now)
        tracker.record("04:222222", "-80", now)
        tracker.record("04:111111", "-65", now)

        assert tracker.best_rssi_for("04:111111") == -65
        assert tracker.best_rssi_for("04:222222") == -80
        assert tracker.best_rssi_for("04:333333") is None

    def test_unknown_device(self) -> None:
        """Unknown device returns None."""
        tracker = RssiTracker()
        assert tracker.best_rssi_for("04:999999") is None
        assert tracker.last_seen("04:999999") is None
        assert tracker.readings_for("04:999999") == []

    def test_sentinel_values_ignored(self, now: dt) -> None:
        """Sentinel RSSI values are silently ignored."""
        tracker = RssiTracker()
        tracker.record("04:123456", "...", now)
        tracker.record("04:123456", "---", now)
        tracker.record("04:123456", "///", now)
        tracker.record("04:123456", "", now)

        assert tracker.best_rssi_for("04:123456") is None
        assert tracker.readings_for("04:123456") == []

    def test_unparsable_ignored(self, now: dt) -> None:
        """Unparsable RSSI strings are silently ignored."""
        tracker = RssiTracker()
        tracker.record("04:123456", "abc", now)
        tracker.record("04:123456", "N/A", now)

        assert tracker.best_rssi_for("04:123456") is None

    def test_int_rssi_accepted(self, now: dt) -> None:
        """Integer RSSI values are accepted directly."""
        tracker = RssiTracker()
        tracker.record("04:123456", -70, now)
        tracker.record("04:123456", -65, now)

        assert tracker.best_rssi_for("04:123456") == -65

    def test_last_seen(self, now: dt) -> None:
        """last_seen returns the timestamp of the most recent reading."""
        tracker = RssiTracker(window_size=3)
        t1 = dt(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        t2 = dt(2026, 1, 1, 12, 5, 0, tzinfo=UTC)
        t3 = dt(2026, 1, 1, 12, 10, 0, tzinfo=UTC)

        tracker.record("04:123456", "-70", t1)
        tracker.record("04:123456", "-65", t2)
        tracker.record("04:123456", "-72", t3)

        assert tracker.last_seen("04:123456") == t3

    def test_known_devices(self, now: dt) -> None:
        """known_devices returns all devices with readings."""
        tracker = RssiTracker()
        tracker.record("04:111111", "-70", now)
        tracker.record("04:222222", "-80", now)

        known = tracker.known_devices()
        assert "04:111111" in known
        assert "04:222222" in known
        assert "04:333333" not in known

    def test_clear(self, now: dt) -> None:
        """clear removes all readings."""
        tracker = RssiTracker()
        tracker.record("04:123456", "-70", now)
        assert tracker.best_rssi_for("04:123456") == -70

        tracker.clear()
        assert tracker.best_rssi_for("04:123456") is None
        assert tracker.known_devices() == frozenset()

    def test_invalid_window_size(self) -> None:
        """Window size < 1 raises ValueError."""
        with pytest.raises(ValueError, match="window_size must be >= 1"):
            RssiTracker(window_size=0)

        with pytest.raises(ValueError, match="window_size must be >= 1"):
            RssiTracker(window_size=-1)

    def test_window_size_1(self, now: dt) -> None:
        """Window size 1 keeps only the latest reading."""
        tracker = RssiTracker(window_size=1)
        tracker.record("04:123456", "-70", now)
        tracker.record("04:123456", "-80", now)

        assert tracker.readings_for("04:123456") == [-80]
        assert tracker.best_rssi_for("04:123456") == -80
