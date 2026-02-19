#!/usr/bin/env python3
"""Test the Packet class and its exposed attributes, including lifespan and parsing."""

from datetime import datetime as dt, timedelta as td

import pytest

from ramses_tx.exceptions import PacketInvalid
from ramses_tx.packet import Packet, pkt_lifespan

# Constants for testing frames
DTM = dt(2023, 1, 1, 12, 0, 0)
VALID_FRAME_I = "045  I --- 01:145038 --:------ 01:145038 1F09 003 0004B5"
VALID_FRAME_RQ = "095 RQ --- 18:006402 13:049798 --:------ 1FC9 001 00"


class MockCommand:
    """A mock command to test the Packet._from_cmd constructor."""

    def __init__(self) -> None:
        """Initialize the mock command."""
        self._frame = " I --- 01:145038 --:------ 01:145038 1F09 003 0004B5"


def test_packet_properties() -> None:
    """Test that Packet initializes correctly and exposes properties.

    :return: None
    """
    packet = Packet(DTM, VALID_FRAME_I, comment="A test comment")

    assert packet.dtm == DTM
    assert packet.rssi == "045"
    assert packet.comment == "A test comment"
    assert packet.error_text == ""
    assert packet.verb == " I"
    assert packet.code == "1F09"


def test_packet_partitioning() -> None:
    """Test the static _partition method for log line splitting.

    :return: None
    """
    raw_line = (
        "045  I --- 01:145038 --:------ 01:145038 1F09 003 0004B5 "
        "< hint * error # comment"
    )

    # _partition returns a map object, so we convert to a tuple to assert
    fragment, err_msg, comment = tuple(Packet._partition(raw_line))

    assert fragment == "045  I --- 01:145038 --:------ 01:145038 1F09 003 0004B5"
    assert err_msg == "error"
    assert comment == "comment"


def test_packet_validation_errors() -> None:
    """Test that invalid packets raise PacketInvalid.

    :return: None
    """
    with pytest.raises(PacketInvalid, match="Custom error"):
        Packet(DTM, VALID_FRAME_I, err_msg="Custom error")

    with pytest.raises(PacketInvalid, match="Null packet"):
        # Frame is sliced by 4:, so a frame of length < 4 is effectively empty.
        # This will now successfully trigger our newly added intercept in packet.py.
        Packet(DTM, "   ", comment="Should fail")


def test_packet_constructors() -> None:
    """Test the alternate classmethod constructors.

    :return: None
    """
    dtm_str = DTM.isoformat()

    # Test from_dict
    pkt_dict = Packet.from_dict(dtm_str, f"{VALID_FRAME_I} # my comment")
    assert pkt_dict.dtm == DTM
    assert pkt_dict.rssi == "045"
    assert pkt_dict.comment == "my comment"

    # Test from_file
    pkt_file_valid = Packet.from_file(dtm_str, VALID_FRAME_I)
    assert pkt_file_valid.rssi == "045"
    assert pkt_file_valid.verb == " I"

    # Test from_port
    pkt_port = Packet.from_port(DTM, VALID_FRAME_I)
    assert pkt_port.rssi == "045"

    # Test _from_cmd
    cmd = MockCommand()
    pkt_cmd = Packet._from_cmd(cmd, DTM)  # type: ignore[arg-type]

    # _from_cmd prepends "... " to the frame, simulating a blank RSSI from a command
    assert pkt_cmd.rssi == "..."
    assert pkt_cmd.verb == " I"


def test_pkt_lifespan(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test the packet lifespan calculation logic.

    :param monkeypatch: The pytest monkeypatch fixture.
    :return: None
    """
    # RQ packets should have 0 lifespan
    pkt_rq = Packet(DTM, VALID_FRAME_RQ)
    assert pkt_lifespan(pkt_rq) == td(seconds=0)

    # 1F09 ' I' packet has 360 seconds
    pkt_1f09 = Packet(DTM, VALID_FRAME_I)
    assert pkt_lifespan(pkt_1f09) == td(seconds=360)

    # Force an array scenario for 000A logic paths
    valid_000a = "045  I --- 01:145038 --:------ 01:145038 000A 006 001122334455"
    pkt_000a = Packet(DTM, valid_000a)

    # Set the internal property cache to safely bypass deeper array schema detection
    monkeypatch.setattr(pkt_000a, "_has_array_", True)
    assert pkt_lifespan(pkt_000a) == td(minutes=60)


def test_packet_representations() -> None:
    """Test the string and repr outputs of the Packet class.

    :return: None
    """
    packet = Packet(DTM, VALID_FRAME_I)

    # The repr should output the time, the original frame components and the header context
    repr_str = repr(packet)
    assert "2023-01-01T12:00:00.000000" in repr_str
    assert "1F09" in repr_str

    # __str__ simply delegates to super().__repr__() which outputs just the formatted frame
    assert str(packet) == " I --- 01:145038 --:------ 01:145038 1F09 003 0004B5"
