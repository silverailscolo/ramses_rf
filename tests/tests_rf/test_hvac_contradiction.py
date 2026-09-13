# --- START OF FILE test_hvac_contradiction.py ---

"""Unit tests for HvacTopologyHandler contradiction detection (issue 1000).

Tests that a device classified as FAN that only sends non-FAN packets
(RQ 31DA, I 22F1, RQ 2411) is detected as a contradiction and a
TopologyChangedEvent is emitted suggesting reclassification to DIS.

Also tests that ``_locked: true`` suppresses the reclassification event.
"""

from __future__ import annotations

from typing import Any

import pytest

from ramses_rf.const import DevType
from ramses_rf.enums import TopologyAction
from ramses_rf.models import TopologyChangedEvent
from ramses_rf.pipeline.topology_handlers.hvac import HvacTopologyHandler
from ramses_tx.const import Code, Verb


class _FakeHeader:
    """Minimal header stub for Message."""

    def __init__(self, verb: Verb, code: Code) -> None:
        self.verb = verb
        self.code = code


class _FakeAddr:
    """Minimal address stub for Message."""

    def __init__(self, device_id: str) -> None:
        self.id = device_id
        self.type = None


class _FakeMsg:
    """Minimal Message stub for testing HvacTopologyHandler.consume()."""

    def __init__(
        self, src_id: str, dst_id: str, verb: Verb, code: Code
    ) -> None:
        self.header = _FakeHeader(verb, code)
        self.src = _FakeAddr(src_id)
        self.dst = _FakeAddr(dst_id)


def _make_handler(
    emitted: list[TopologyChangedEvent],
    *,
    enable_eavesdrop: bool = True,
    device_class_lookup_cb: Any = None,
) -> HvacTopologyHandler:
    """Create an HvacTopologyHandler that captures emitted events."""

    def _emit(event: TopologyChangedEvent) -> None:
        emitted.append(event)

    return HvacTopologyHandler(
        _emit,
        enable_eavesdrop=enable_eavesdrop,
        device_class_lookup_cb=device_class_lookup_cb,
    )


def _make_lookup(class_map: dict[str, dict[str, Any]]) -> Any:
    """Create a device_class_lookup_cb from a {device_id: traits} map."""

    def _lookup(device_id: str) -> dict[str, Any] | None:
        return class_map.get(device_id)

    return _lookup


# --- Tests for contradiction detection ---


def _display_events(
    emitted: list[TopologyChangedEvent],
) -> list[TopologyChangedEvent]:
    """Return direct 2411 display-classification events."""
    return [
        event
        for event in emitted
        if event.causation == "Rule_HVAC_2411_Request_Source_to_DIS"
    ]


def test_non_faked_rem_requesting_2411_is_display() -> None:
    emitted: list[TopologyChangedEvent] = []
    lookup = _make_lookup(
        {
            "37:169161": {
                "class": DevType.REM,
                "locked": False,
                "faked": False,
            },
            "32:153289": {"class": DevType.FAN},
        }
    )
    handler = _make_handler(emitted, device_class_lookup_cb=lookup)

    handler.consume(_FakeMsg("37:169161", "32:153289", Verb.RQ, Code._2411))

    assert len(_display_events(emitted)) == 1
    assert _display_events(emitted)[0].metadata["device_class"] == DevType.DIS


def test_faked_rem_requesting_2411_is_not_display_evidence() -> None:
    emitted: list[TopologyChangedEvent] = []
    lookup = _make_lookup(
        {
            "37:169161": {
                "class": DevType.REM,
                "locked": False,
                "faked": True,
            },
            "32:153289": {"class": DevType.FAN},
        }
    )
    handler = _make_handler(emitted, device_class_lookup_cb=lookup)

    for _ in range(3):
        handler.consume(
            _FakeMsg("37:169161", "32:153289", Verb.RQ, Code._2411)
        )

    assert _display_events(emitted) == []
    assert handler._evidence["37:169161"]["non_fan"] == 0


def test_locked_rem_requesting_2411_is_not_reclassified() -> None:
    emitted: list[TopologyChangedEvent] = []
    lookup = _make_lookup(
        {
            "37:169161": {
                "class": DevType.REM,
                "locked": True,
                "faked": False,
            },
            "32:153289": {"class": DevType.FAN},
        }
    )
    handler = _make_handler(emitted, device_class_lookup_cb=lookup)

    handler.consume(_FakeMsg("37:169161", "32:153289", Verb.RQ, Code._2411))

    assert _display_events(emitted) == []


def test_normal_rem_fan_mode_command_is_not_display_evidence() -> None:
    emitted: list[TopologyChangedEvent] = []
    lookup = _make_lookup(
        {
            "37:169161": {
                "class": DevType.REM,
                "locked": False,
                "faked": False,
            },
            "32:153289": {"class": DevType.FAN},
        }
    )
    handler = _make_handler(emitted, device_class_lookup_cb=lookup)

    handler.consume(_FakeMsg("37:169161", "32:153289", Verb.I_, Code._22F1))

    assert _display_events(emitted) == []


def test_contradiction_detected_after_threshold() -> None:
    """A FAN-classified device sending only non-FAN packets triggers DIS reclassification."""
    emitted: list[TopologyChangedEvent] = []
    lookup = _make_lookup(
        {"37:169161": {"class": DevType.FAN, "locked": False}}
    )
    handler = _make_handler(emitted, device_class_lookup_cb=lookup)

    # Inject 3 non-FAN packets (threshold is 3)
    packets = [
        _FakeMsg("37:169161", "32:153289", Verb.RQ, Code._31DA),
        _FakeMsg("37:169161", "32:153289", Verb.I_, Code._22F1),
        _FakeMsg("37:169161", "32:153289", Verb.RQ, Code._2411),
    ]
    for msg in packets:
        handler.consume(msg)

    # Should emit at least one UPDATE_DEVICE_CLASS event with DIS
    contradiction_events = [
        e
        for e in emitted
        if e.action == TopologyAction.UPDATE_DEVICE_CLASS
        and e.causation == "Rule_HVAC_Contradiction_FAN_to_DIS"
    ]
    assert len(contradiction_events) > 0, (
        f"Expected at least one contradiction event, got {len(contradiction_events)} "
        f"(total events: {len(emitted)})"
    )
    assert contradiction_events[0].metadata["device_class"] == DevType.DIS
    assert contradiction_events[0].device_id == "37:169161"


def test_no_contradiction_when_fan_evidence_present() -> None:
    """A FAN-classified device that also sends FAN packets should NOT trigger reclassification."""
    emitted: list[TopologyChangedEvent] = []
    lookup = _make_lookup(
        {"37:169161": {"class": DevType.FAN, "locked": False}}
    )
    handler = _make_handler(emitted, device_class_lookup_cb=lookup)

    # Mix of FAN and non-FAN packets
    packets = [
        _FakeMsg(
            "37:169161", "32:153289", Verb.I_, Code._31DA
        ),  # FAN evidence
        _FakeMsg("37:169161", "32:153289", Verb.RQ, Code._31DA),  # non-FAN
        _FakeMsg("37:169161", "32:153289", Verb.I_, Code._22F1),  # non-FAN
        _FakeMsg("37:169161", "32:153289", Verb.RQ, Code._2411),  # non-FAN
    ]
    for msg in packets:
        handler.consume(msg)

    contradiction_events = [
        e
        for e in emitted
        if e.causation == "Rule_HVAC_Contradiction_FAN_to_DIS"
    ]
    assert len(contradiction_events) == 0, (
        f"Should not trigger contradiction when FAN evidence is present, "
        f"got {len(contradiction_events)} events"
    )


def test_contradiction_below_threshold_no_event() -> None:
    """Only 2 non-FAN packets (below threshold of 3) should not trigger reclassification."""
    emitted: list[TopologyChangedEvent] = []
    lookup = _make_lookup(
        {"37:169161": {"class": DevType.FAN, "locked": False}}
    )
    handler = _make_handler(emitted, device_class_lookup_cb=lookup)

    # Only 2 non-FAN packets (threshold is 3)
    packets = [
        _FakeMsg("37:169161", "32:153289", Verb.RQ, Code._31DA),
        _FakeMsg("37:169161", "32:153289", Verb.I_, Code._22F1),
    ]
    for msg in packets:
        handler.consume(msg)

    contradiction_events = [
        e
        for e in emitted
        if e.causation == "Rule_HVAC_Contradiction_FAN_to_DIS"
    ]
    assert len(contradiction_events) == 0


def test_locked_suppresses_reclassification() -> None:
    """A _locked FAN device should NOT trigger reclassification events."""
    emitted: list[TopologyChangedEvent] = []
    lookup = _make_lookup(
        {"37:169161": {"class": DevType.FAN, "locked": True}}
    )
    handler = _make_handler(emitted, device_class_lookup_cb=lookup)

    # 3 non-FAN packets — would normally trigger reclassification
    packets = [
        _FakeMsg("37:169161", "32:153289", Verb.RQ, Code._31DA),
        _FakeMsg("37:169161", "32:153289", Verb.I_, Code._22F1),
        _FakeMsg("37:169161", "32:153289", Verb.RQ, Code._2411),
    ]
    for msg in packets:
        handler.consume(msg)

    contradiction_events = [
        e
        for e in emitted
        if e.causation == "Rule_HVAC_Contradiction_FAN_to_DIS"
    ]
    assert len(contradiction_events) == 0, (
        f"Locked device should not emit reclassification events, "
        f"got {len(contradiction_events)}"
    )


def test_rp_2411_is_fan_evidence() -> None:
    """RP 2411 from a FAN-classified device counts as FAN evidence."""
    emitted: list[TopologyChangedEvent] = []
    lookup = _make_lookup(
        {"37:169161": {"class": DevType.FAN, "locked": False}}
    )
    handler = _make_handler(emitted, device_class_lookup_cb=lookup)

    # RP 2411 (FAN evidence) + 3 non-FAN packets
    packets = [
        _FakeMsg(
            "37:169161", "32:153289", Verb.RP, Code._2411
        ),  # FAN evidence
        _FakeMsg("37:169161", "32:153289", Verb.RQ, Code._31DA),  # non-FAN
        _FakeMsg("37:169161", "32:153289", Verb.I_, Code._22F1),  # non-FAN
        _FakeMsg("37:169161", "32:153289", Verb.RQ, Code._2411),  # non-FAN
    ]
    for msg in packets:
        handler.consume(msg)

    contradiction_events = [
        e
        for e in emitted
        if e.causation == "Rule_HVAC_Contradiction_FAN_to_DIS"
    ]
    assert len(contradiction_events) == 0, (
        "RP 2411 is FAN evidence — should not trigger contradiction"
    )


def test_non_fan_device_no_contradiction() -> None:
    """A device classified as REM (not FAN) should not trigger FAN→DIS contradiction."""
    emitted: list[TopologyChangedEvent] = []
    lookup = _make_lookup(
        {"37:169161": {"class": DevType.REM, "locked": False}}
    )
    handler = _make_handler(emitted, device_class_lookup_cb=lookup)

    packets = [
        _FakeMsg("37:169161", "32:153289", Verb.RQ, Code._31DA),
        _FakeMsg("37:169161", "32:153289", Verb.I_, Code._22F1),
        _FakeMsg("37:169161", "32:153289", Verb.RQ, Code._2411),
    ]
    for msg in packets:
        handler.consume(msg)

    contradiction_events = [
        e
        for e in emitted
        if e.causation == "Rule_HVAC_Contradiction_FAN_to_DIS"
    ]
    assert len(contradiction_events) == 0


def test_warning_emitted_once_per_session(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The WARNING log fires once, but the event continues to fire on each packet."""
    import logging

    emitted: list[TopologyChangedEvent] = []
    lookup = _make_lookup(
        {"37:169161": {"class": DevType.FAN, "locked": False}}
    )
    handler = _make_handler(emitted, device_class_lookup_cb=lookup)

    with caplog.at_level(
        logging.WARNING, logger="ramses_rf.pipeline.topology_handlers.hvac"
    ):
        # First batch of 3 non-FAN packets — triggers warning + first event
        for msg in [
            _FakeMsg("37:169161", "32:153289", Verb.RQ, Code._31DA),
            _FakeMsg("37:169161", "32:153289", Verb.I_, Code._22F1),
            _FakeMsg("37:169161", "32:153289", Verb.RQ, Code._2411),
        ]:
            handler.consume(msg)

        warning_count_after_first = sum(
            1 for r in caplog.records if r.levelno == logging.WARNING
        )

        # Second batch — should still emit events (idempotent SSOT update)
        for msg in [
            _FakeMsg("37:169161", "32:153289", Verb.RQ, Code._31DA),
            _FakeMsg("37:169161", "32:153289", Verb.I_, Code._22F1),
        ]:
            handler.consume(msg)

        warning_count_after_second = sum(
            1 for r in caplog.records if r.levelno == logging.WARNING
        )

    # WARNING should only fire once (despite 5 total non-FAN packets)
    assert warning_count_after_first == 1, (
        f"Expected 1 WARNING after first batch, got {warning_count_after_first}"
    )
    assert warning_count_after_second == 1, (
        f"WARNING should not repeat — expected 1, got {warning_count_after_second}"
    )

    # Events should continue to fire after the first warning
    contradiction_events = [
        e
        for e in emitted
        if e.causation == "Rule_HVAC_Contradiction_FAN_to_DIS"
    ]
    # 3 non-FAN packets in first batch (threshold=3, so event on packet 3)
    # + 2 non-FAN packets in second batch (events on packets 4 and 5)
    assert len(contradiction_events) >= 2, (
        f"Events should continue to fire after first warning, "
        f"got {len(contradiction_events)} total contradiction events"
    )


# --- Tests for CO2 promotion (hybrid CO2+REM devices) ---


def test_dis_promoted_to_co2_when_1298_received() -> None:
    """A DIS-classified device sending I 1298 is promoted to CO2.

    If the device was already promoted to DIS (e.g. via RQ 2411 active
    probing) before the first I 1298 was received, the direct CO2
    promotion rule should still fire when I 1298 arrives and promote
    the device from DIS to CO2.
    """
    emitted: list[TopologyChangedEvent] = []
    lookup = _make_lookup(
        {
            "37:126776": {
                "class": DevType.DIS,
                "locked": False,
                "faked": False,
            },
        }
    )
    handler = _make_handler(emitted, device_class_lookup_cb=lookup)

    # Send I 1298 — should promote directly to CO2
    handler.consume(_FakeMsg("37:126776", "--:------", Verb.I_, Code._1298))

    co2_events = [
        e for e in emitted if e.causation == "Rule_HVAC_1298_Signature_to_CO2"
    ]
    assert len(co2_events) == 1, (
        f"Expected 1 CO2 promotion from DIS, got {len(co2_events)}"
    )
    assert co2_events[0].metadata["device_class"] == DevType.CO2


def test_rem_promoted_to_co2_when_1298_received() -> None:
    """A REM-classified device sending I 1298 is promoted directly to CO2.

    I 1298 is the definitive CO2 signature — no other HVAC device type
    sends it.  The direct promotion rule fires immediately, without
    waiting for the REM→DIS rule or the contradiction threshold.
    """
    emitted: list[TopologyChangedEvent] = []
    lookup = _make_lookup(
        {
            "37:126776": {
                "class": DevType.REM,
                "locked": False,
                "faked": False,
            },
        }
    )
    handler = _make_handler(emitted, device_class_lookup_cb=lookup)

    handler.consume(_FakeMsg("37:126776", "--:------", Verb.I_, Code._1298))

    co2_events = [
        e for e in emitted if e.causation == "Rule_HVAC_1298_Signature_to_CO2"
    ]
    assert len(co2_events) == 1
    assert co2_events[0].metadata["device_class"] == DevType.CO2


def test_locked_suppresses_direct_co2_promotion() -> None:
    """A _locked device should NOT be promoted to CO2 by I 1298."""
    emitted: list[TopologyChangedEvent] = []
    lookup = _make_lookup(
        {
            "37:126776": {
                "class": DevType.REM,
                "locked": True,
                "faked": False,
            },
        }
    )
    handler = _make_handler(emitted, device_class_lookup_cb=lookup)

    handler.consume(_FakeMsg("37:126776", "--:------", Verb.I_, Code._1298))

    co2_events = [
        e for e in emitted if e.causation == "Rule_HVAC_1298_Signature_to_CO2"
    ]
    assert len(co2_events) == 0, "Locked device should not be promoted to CO2"


def test_co2_not_re_promoted_when_already_co2() -> None:
    """A CO2-classified device sending I 1298 should NOT re-promote."""
    emitted: list[TopologyChangedEvent] = []
    lookup = _make_lookup(
        {
            "37:126776": {
                "class": DevType.CO2,
                "locked": False,
                "faked": False,
            },
        }
    )
    handler = _make_handler(emitted, device_class_lookup_cb=lookup)

    handler.consume(_FakeMsg("37:126776", "--:------", Verb.I_, Code._1298))

    co2_events = [
        e for e in emitted if e.causation == "Rule_HVAC_1298_Signature_to_CO2"
    ]
    assert len(co2_events) == 0, "Device already CO2 should not be re-promoted"


def test_rem_with_co2_evidence_promoted_to_co2_not_dis() -> None:
    """A REM sending both I 1298 (CO2) and RQ 2411 (display) is promoted
    to CO2, not DIS.

    A CO2 sensor with integrated remote buttons sends both I 1298
    (CO2 level — definitive CO2 signature) and RQ 2411 (display
    request).  The REM→DIS rule fires on RQ 2411, but CO2 evidence
    must take precedence.
    """
    emitted: list[TopologyChangedEvent] = []
    lookup = _make_lookup(
        {
            "37:126776": {
                "class": DevType.REM,
                "locked": False,
                "faked": False,
            },
            "32:153289": {"class": DevType.FAN},
        }
    )
    handler = _make_handler(emitted, device_class_lookup_cb=lookup)

    # Send I 1298 first (CO2 evidence)
    handler.consume(_FakeMsg("37:126776", "--:------", Verb.I_, Code._1298))
    # Then send RQ 2411 to FAN (would trigger REM→DIS)
    handler.consume(_FakeMsg("37:126776", "32:153289", Verb.RQ, Code._2411))

    co2_events = [
        e
        for e in emitted
        if e.causation == "Rule_HVAC_2411_Request_Source_to_CO2"
    ]
    dis_events = [
        e
        for e in emitted
        if e.causation == "Rule_HVAC_2411_Request_Source_to_DIS"
    ]
    assert len(co2_events) == 1, (
        f"Expected 1 CO2 promotion event, got {len(co2_events)}"
    )
    assert len(dis_events) == 0, (
        f"Expected 0 DIS promotion events, got {len(dis_events)}"
    )
    assert co2_events[0].metadata["device_class"] == DevType.CO2


def test_rem_without_co2_evidence_promoted_to_dis() -> None:
    """A REM sending only RQ 2411 (no CO2 evidence) is promoted to DIS."""
    emitted: list[TopologyChangedEvent] = []
    lookup = _make_lookup(
        {
            "37:169161": {
                "class": DevType.REM,
                "locked": False,
                "faked": False,
            },
            "32:153289": {"class": DevType.FAN},
        }
    )
    handler = _make_handler(emitted, device_class_lookup_cb=lookup)

    handler.consume(_FakeMsg("37:169161", "32:153289", Verb.RQ, Code._2411))

    dis_events = [
        e
        for e in emitted
        if e.causation == "Rule_HVAC_2411_Request_Source_to_DIS"
    ]
    co2_events = [
        e
        for e in emitted
        if e.causation == "Rule_HVAC_2411_Request_Source_to_CO2"
    ]
    assert len(dis_events) == 1
    assert len(co2_events) == 0
    assert dis_events[0].metadata["device_class"] == DevType.DIS


def test_fan_with_co2_evidence_promoted_to_co2_not_dis() -> None:
    """A FAN sending I 1298 (CO2) + non-FAN packets is promoted to CO2,
    not DIS."""
    emitted: list[TopologyChangedEvent] = []
    lookup = _make_lookup(
        {"37:126776": {"class": DevType.FAN, "locked": False}}
    )
    handler = _make_handler(emitted, device_class_lookup_cb=lookup)

    # I 1298 (CO2 evidence) + 3 non-FAN packets (threshold)
    packets = [
        _FakeMsg("37:126776", "32:153289", Verb.I_, Code._1298),
        _FakeMsg("37:126776", "32:153289", Verb.RQ, Code._31DA),
        _FakeMsg("37:126776", "32:153289", Verb.I_, Code._22F1),
        _FakeMsg("37:126776", "32:153289", Verb.RQ, Code._2411),
    ]
    for msg in packets:
        handler.consume(msg)

    co2_events = [
        e
        for e in emitted
        if e.causation == "Rule_HVAC_Contradiction_FAN_to_CO2"
    ]
    dis_events = [
        e
        for e in emitted
        if e.causation == "Rule_HVAC_Contradiction_FAN_to_DIS"
    ]
    assert len(co2_events) >= 1, (
        f"Expected at least 1 CO2 promotion, got {len(co2_events)}"
    )
    assert len(dis_events) == 0, (
        f"Expected 0 DIS promotions, got {len(dis_events)}"
    )
    assert co2_events[0].metadata["device_class"] == DevType.CO2
