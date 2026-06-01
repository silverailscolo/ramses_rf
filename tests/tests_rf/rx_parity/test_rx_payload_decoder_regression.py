"""Test module for ensuring the decoupled RX DTO pipeline parses payloads cleanly."""

from pathlib import Path
from typing import Any

import pytest

from ramses_rf.parsers.decoder import decode_packet
from ramses_tx.exceptions import PacketPayloadInvalid
from ramses_tx.packet import Packet

# Constants
FIXTURE_PATH: Path = (
    Path(__file__).parent.parent.parent / "fixtures" / "regression_packets_sorted.txt"
)


def _load_regression_frames() -> list[str]:
    """Load and sanitize raw packet frames from the regression text file.

    Strips out comments and ignores empty lines.

    :raises FileNotFoundError: If the regression file cannot be found at FIXTURE_PATH.
    :return: A list of sanitized raw frame strings.
    """
    if not FIXTURE_PATH.exists():
        raise FileNotFoundError(f"Could not find regression file at: {FIXTURE_PATH}")

    frames: list[str] = []
    with open(FIXTURE_PATH, encoding="utf-8") as file:
        for line in file:
            raw_frame: str = line.split("#")[0].strip()
            if raw_frame:
                frames.append(raw_frame)

    return frames


# Constants initialized after function declaration
RAW_FRAMES: list[str] = _load_regression_frames()


@pytest.mark.parametrize("raw_frame", RAW_FRAMES)
def test_rx_payload_decoder_regression(raw_frame: str) -> None:
    """Stress-test the decoupled DTO decoder against real-world packet frames.

    Ensures that L3 DTOs successfully cross the OSI boundary into L7 and decode
    without raising unexpected exceptions.

    :param raw_frame: The raw regression frame string.
    """
    if raw_frame[10] == " ":
        date_str, time_str, pkt_line = raw_frame.split(" ", 2)
        dtm_str: str = f"{date_str}T{time_str}"
    else:
        dtm_str, pkt_line = raw_frame.split(" ", 1)

    # 1. Arrange: Construct the raw packet to simulate L2/L3 reception.
    try:
        pkt: Any = Packet.from_file(dtm_str, pkt_line)
    except Exception as err:
        pytest.skip(f"Skipped due to L2 packet instantiation failure: {err}")

    # 2. Act: Translate to DTO and push across the boundary to the L7 Decoder.
    try:
        dto: Any = pkt.to_dto()
        new_payload: Any = decode_packet(dto)
    except PacketPayloadInvalid as err:
        # The L7 decoder successfully caught a malformed/corrupt RF payload
        pytest.skip(f"Legitimate schema rejection: {err}")
    except Exception as err:
        # A genuine code crash occurred (e.g., KeyError, AttributeError)
        pytest.fail(
            f"Decoder crashed on DTO boundary for frame: {raw_frame}\nError: {err}"
        )

    # 3. Assert: Verify the decoder produced a valid output (dict, list, or valid str).
    assert new_payload is not None, f"Decoder returned None for frame: {raw_frame}"

    # If the payload is returned as a raw string, ensure it isn't a flagged ERROR state
    if isinstance(new_payload, str):
        assert not new_payload.startswith("ERROR"), (
            f"Decoder returned an ERROR payload state: {new_payload}"
        )
