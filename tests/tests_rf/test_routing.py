#!/usr/bin/env python3
"""Tests for the L7 domain routing components."""

from ramses_rf.routing import EventTopic, RoutingContext, StateHeader


def test_routing_context_string_formatting() -> None:
    """Test that RoutingContext handles legacy string casting safely."""
    assert RoutingContext(True).as_string == "True"
    assert RoutingContext(False).as_string == "False"
    assert RoutingContext("00").as_string == "00"
    assert RoutingContext("FA").as_string == "FA"
    assert RoutingContext(None).as_string == "None"


def test_state_header_legacy_formatting() -> None:
    """Test that StateHeader perfectly replicates the legacy _hdr format."""
    hdr = StateHeader.create(
        code="3220",
        verb="RP",
        source_id="01:123456",
        context_val="00",
    )
    assert hdr.legacy_hdr == "3220|RP|01:123456|00"

    base_hdr = StateHeader.create(
        code="10A0",
        verb=" I",
        source_id="04:654321",
        context_val=True,
    )
    assert base_hdr.legacy_hdr == "10A0| I|04:654321|True"


def test_state_header_hashing() -> None:
    """Test that StateHeader can be used as an O(1) dictionary key."""
    hdr1 = StateHeader.create("000C", "RP", "01:111111", "01")
    hdr2 = StateHeader.create("000C", "RP", "01:111111", "01")
    hdr3 = StateHeader.create("000C", "RP", "01:111111", "02")

    cache = {hdr1: "payload_data"}

    assert hdr2 in cache
    assert hdr3 not in cache


def test_state_header_topic_generation() -> None:
    """Test the Master Plan topic generation logic."""
    # Note: using the exact string spaces to map to the Enum
    state_hdr = StateHeader.create("30C9", " I", "01:123456", "00")
    assert state_hdr.topic is EventTopic.INFORMATION

    disc_hdr = StateHeader.create("1FC9", " I", "01:123456", "00")
    assert disc_hdr.topic is EventTopic.TOPOLOGY_DISCOVERY

    req_hdr = StateHeader.create("3220", "RQ", "01:123456", "00")
    assert req_hdr.topic is EventTopic.REQUEST

    write_hdr = StateHeader.create("2309", " W", "01:123456", "00")
    assert write_hdr.topic is EventTopic.WRITE
