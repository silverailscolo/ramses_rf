"""Tests for the OSI layer decoupling DTO conversions."""

from datetime import UTC, datetime as dt

from ramses_tx.dtos import PacketDTO
from ramses_tx.packet import Packet


def test_packet_to_dto_populates_all_fields_accurately() -> None:
    # Arrange: Setup a known UTC timezone-aware timestamp
    test_dtm = dt(2023, 10, 25, 12, 0, 0, tzinfo=UTC)

    # Standard format: RSSI VERB SEQN ADDR1 ADDR2 ADDR3 CODE LEN PAYLOAD
    raw_frame = "045 RQ --- 18:000730 01:145038 --:------ 000A 002 0800"

    # Act: Pass through the modem Packet class and convert to our DTO
    packet = Packet(test_dtm, raw_frame)
    dto = packet.to_dto()

    # Assert: Verify all primitive strings are accurately separated
    assert isinstance(dto, PacketDTO)
    assert dto.timestamp == test_dtm
    assert dto.rssi == "045"
    assert dto.verb == "RQ"
    assert dto.seq == ""
    assert dto.addr1 == "18:000730"
    assert dto.addr2 == "01:145038"
    assert dto.addr3 == "--:------"
    assert dto.code == "000A"
    assert dto.length == "002"
    assert dto.payload == "0800"


def test_packet_to_dto_enforces_strict_verb_padding() -> None:
    # Arrange: The architectural boundary requires " I" instead of "I"
    test_dtm = dt(2023, 10, 25, 12, 5, 0, tzinfo=UTC)

    # Frame with 'I' verb (Information)
    raw_frame = "045  I --- 01:145038 --:------ 01:145038 30C9 003 0001C8"

    # Act: Process the frame
    packet = Packet(test_dtm, raw_frame)
    dto = packet.to_dto()

    # Assert: Ensure ' I' dynamically right-pads to exactly two characters
    assert dto.verb == " I"
    assert dto.addr1 == "01:145038"
    assert dto.addr2 == "--:------"
    assert dto.addr3 == "01:145038"
    assert dto.code == "30C9"
