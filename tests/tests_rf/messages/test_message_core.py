"""Tests for the Phase 2.75 immutable Message domain model."""

from datetime import UTC, datetime as dt

from ramses_rf.address import Address
from ramses_rf.const import Code, Verb
from ramses_rf.enums import Topic
from ramses_rf.messages.core import Message
from ramses_rf.routing import StateHeader
from ramses_tx.dtos import PacketDTO


def test_message_enrichment_and_lineage() -> None:
    """Verify Message safely enriches data and preserves audit lineage."""
    src = Address("01:111111")
    dst = Address("04:222222")
    packet = PacketDTO(
        timestamp=dt.now(tz=UTC),
        rssi="-70",
        verb=Verb.I_,
        seq="000",
        addr1="01:111111",
        addr2="--:------",
        addr3="04:222222",
        code=Code._30C9,
        length="003",
        raw_payload="0001C8",
    )

    # 1. Create the base Message (RAW_EVENT)

    mock_header = StateHeader.create(
        code=Code._30C9,
        verb=Verb.I_,
        source_id="01:111111",
        context_value=None,
    )

    msg = Message(
        topic=Topic.RAW_EVENT,
        header=mock_header,
        src=src,
        dst=dst,
        data={"raw_temp": 45.6},
        packets=(packet,),
        timestamp=packet.timestamp,
    )

    assert len(msg.lineage) == 0
    assert msg.get("raw_temp") == 45.6

    # 2. First Enrichment (e.g., Decoder Engine parsing)
    msg_parsed = msg.enrich(Topic.STATE_UPDATE, parsed_temp=45.6)

    assert msg_parsed.topic == Topic.STATE_UPDATE
    assert msg_parsed.get("parsed_temp") == 45.6
    assert msg_parsed.get("raw_temp") == 45.6
    assert len(msg_parsed.lineage) == 1
    assert msg_parsed.lineage[0] is msg

    # 3. Second Enrichment (e.g., SSOT tracking)
    msg_final = msg_parsed.enrich(Topic.TOPOLOGY_DISCOVERY, zone_index="01")

    assert msg_final.topic == Topic.TOPOLOGY_DISCOVERY
    assert msg_final.get("zone_index") == "01"
    assert len(msg_final.lineage) == 2
    assert msg_final.lineage[0] is msg
    assert msg_final.lineage[1] is msg_parsed
