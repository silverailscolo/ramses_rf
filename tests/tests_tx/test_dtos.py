"""Tests for the OSI layer decoupling DTO conversions."""

from datetime import UTC, datetime as dt

import pytest

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
    assert dto.raw_payload == "0800"


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


def test_packet_dto_is_tx_default_and_custom() -> None:
    # Arrange
    test_dtm = dt(2026, 7, 31, 12, 0, 0, tzinfo=UTC)

    # Act: Construct default inbound DTO and custom outbound DTO
    inbound_dto = PacketDTO(
        timestamp=test_dtm,
        rssi="045",
        verb="RQ",
        seq="",
        addr1="18:000730",
        addr2="01:145038",
        addr3="--:------",
        code="000A",
        length="002",
        payload="0800",
    )
    outbound_dto = PacketDTO(
        timestamp=test_dtm,
        rssi="045",
        verb="RQ",
        seq="",
        addr1="18:000730",
        addr2="01:145038",
        addr3="--:------",
        code="000A",
        length="002",
        payload="0800",
        is_tx=True,
    )

    # Assert
    assert inbound_dto.is_tx is False
    assert outbound_dto.is_tx is True


# ── Positional addressing: addr1/addr2/addr3 → src/dst resolution ──────
# RAMSES II positional addressing rules (issue 639):
#   I  broadcast:  addr1=src, addr2=--:------, addr3=src (same device)
#   I  directed:   addr1=src, addr2=dst,      addr3=--:------
#   RQ directed:   addr1=src, addr2=dst,      addr3=--:------
#   RP directed:   addr1=dst, addr2=src,      addr3=--:------
#   W  directed:   addr1=src, addr2=dst,      addr3=--:------

_PACKET_CASES = [
    (" I --- 01:150003 --:------ 01:150003 30C9 003 030AC0", "01:150003", "01:150003"),
    (" I --- 37:168270 32:153289 --:------ 22F1 003 000307", "37:168270", "32:153289"),
    ("RQ --- 18:001234 01:150000 --:------ 0002 001 00", "18:001234", "01:150000"),
    ("RP --- 01:150000 18:001234 --:------ 0002 002 0000", "01:150000", "18:001234"),
    (
        " W --- 18:001234 01:150000 --:------ 2E04 008 00FFFFFFFFFFFF00",
        "18:001234",
        "01:150000",
    ),
]


@pytest.mark.parametrize(
    ("frame", "expected_src", "expected_dst"),
    _PACKET_CASES,
    ids=["I broadcast", "I directed", "RQ directed", "RP directed", "W directed"],
)
def test_packet_from_dict_resolves_src_dst(
    frame: str, expected_src: str, expected_dst: str
) -> None:
    """Packet.from_dict resolves positional addr1/addr2/addr3 to logical src/dst.

    The verb determines which positional address is src and which is dst:
    - I/RQ/W: addr1=src, addr2=dst
    - RP: addr1=dst, addr2=src (reversed for replies)
    - I broadcast: addr1=src=addr3 (self-announcement)
    """
    pkt = Packet.from_dict("2026-01-01T00:00:00", {"rssi": "000", "frame": frame})
    assert pkt.src.id == expected_src
    assert pkt.dst.id == expected_dst
