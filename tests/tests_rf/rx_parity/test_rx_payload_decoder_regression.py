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

# Baseline metrics for the static fixture file. If these change, a parser
# has been altered and the regression requires manual review.
EXPECTED_L2_SKIPS: int = 10
EXPECTED_SCHEMA_SKIPS: int = 15


def _load_regression_frames() -> list[tuple[int, str]]:
    """Load and sanitize raw packet frames from the regression text file.

    Strips out comments and ignores empty lines.

    :raises FileNotFoundError: If the regression file cannot be found at
        FIXTURE_PATH.
    :return: A list of tuples containing line numbers and sanitized raw
        frame strings.
    """
    if not FIXTURE_PATH.exists():
        raise FileNotFoundError(f"Could not find regression file at: {FIXTURE_PATH}")

    frames: list[tuple[int, str]] = []
    with open(FIXTURE_PATH, encoding="utf-8") as file:
        for line_num, line in enumerate(file, start=1):
            raw_frame: str = line.split("#")[0].strip()
            if raw_frame:
                frames.append((line_num, raw_frame))

    return frames


# Constants initialized after function declaration
RAW_FRAMES: list[tuple[int, str]] = _load_regression_frames()


def test_rx_payload_decoder_regression() -> None:
    """Stress-test the decoupled DTO decoder against real-world packet
    frames.

    Ensures that L3 DTOs successfully cross the OSI boundary into L7 and
    decode without raising unexpected exceptions.
    """
    errors: list[str] = []
    skipped_l2_count: int = 0
    skipped_schema_count: int = 0

    for line_num, raw_frame in RAW_FRAMES:
        if raw_frame[10] == " ":
            date_str, time_str, pkt_line = raw_frame.split(" ", 2)
            dtm_str: str = f"{date_str}T{time_str}"
        else:
            dtm_str, pkt_line = raw_frame.split(" ", 1)

        # 1. Arrange: Construct the raw packet to simulate L2/L3 reception.
        try:
            pkt: Any = Packet.from_file(dtm_str, pkt_line)
        except Exception:
            # Skipped due to L2 packet instantiation failure
            skipped_l2_count += 1
            continue

        # 2. Act: Translate to DTO and push across the boundary to the L7
        # Decoder.
        try:
            dto: Any = pkt.to_dto()
            new_payload: Any = decode_packet(dto)
        except PacketPayloadInvalid:
            # The L7 decoder successfully caught a malformed/corrupt RF payload
            skipped_schema_count += 1
            continue
        except Exception as err:
            # A genuine code crash occurred (e.g., KeyError, AttributeError)
            errors.append(f"Line {line_num} | Frame: {raw_frame} | Error: {err}")
            continue

        # 3. Assert: Verify the decoder produced a valid output (dict, list,
        # or valid str).
        if new_payload is None:
            errors.append(
                f"Line {line_num} | Frame: {raw_frame} | Error: Returned None"
            )
            continue

        # If the payload is returned as a raw string, ensure it isn't a
        # flagged ERROR state
        if isinstance(new_payload, str) and new_payload.startswith("ERROR"):
            errors.append(
                f"Line {line_num} | Frame: {raw_frame} | "
                f"Error: ERROR state {new_payload}"
            )

    # Final Evaluation: Catch genuine code crashes
    if errors:
        error_summary: str = "\n".join(errors)
        pytest.fail(f"Decoder crashed on {len(errors)} frames:\n{error_summary}")

    # Final Evaluation: Prevent silent regressions on known baselines
    assert skipped_l2_count == EXPECTED_L2_SKIPS, (
        f"L2 Exception baseline shifted! Expected {EXPECTED_L2_SKIPS}, "
        f"got {skipped_l2_count}."
    )
    assert skipped_schema_count == EXPECTED_SCHEMA_SKIPS, (
        f"Schema Rejection baseline shifted! Expected {EXPECTED_SCHEMA_SKIPS}, "
        f"got {skipped_schema_count}."
    )
