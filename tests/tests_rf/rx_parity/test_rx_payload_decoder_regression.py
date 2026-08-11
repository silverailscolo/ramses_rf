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
EXPECTED_SCHEMA_SKIPS: int = 11


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


# ---------------------------------------------------------------------------
# Regression: ramses_cc issue 929 — faking Zone THM broken
#
# 30C9 packets from non-controller devices (03:/04:/12:) with a non-zero
# zone_idx must be accepted by the decoder.  The 0xAB guard in _pkt_idx
# was rejecting them because those device types are not in {01, 02, 23}.
# Real THM sensors send 30C9 with their zone_idx, and faked THM sensors
# (introduced in 0.59.2 via commit 5b9abbe4) do the same.
# ---------------------------------------------------------------------------

_DTM = "2026-08-09T19:09:23.000000"


@pytest.mark.parametrize(
    "frame",
    [
        # 03: analog_thermostat, zone_idx 05 (the issue's faked sensor)
        "000  I --- 03:055486 --:------ 03:055486 30C9 003 050AA0",
        # 03: analog_thermostat, zone_idx 01 (real sensor from fixture)
        "044  I 007 03:201565 --:------ 03:201565 30C9 003 01073A",
        # 04: radiator_valve, zone_idx 03
        "000  I --- 04:055480 --:------ 04:055480 30C9 003 030A28",
    ],
)
def test_30c9_non_controller_with_zone_idx_accepted(frame: str) -> None:
    """30C9 from a non-controller with a non-zero idx must not raise."""
    pkt: Any = Packet.from_file(_DTM, frame)
    dto: Any = pkt.to_dto()
    result: Any = decode_packet(dto)  # must not raise PacketPayloadInvalid
    assert isinstance(result, dict)
    assert "temperature" in result


def test_30c9_controller_still_injects_zone_idx() -> None:
    """30C9 from a controller (01:) must still inject zone_idx into the result."""
    pkt: Any = Packet.from_file(
        _DTM, "000  I --- 01:050858 --:------ 01:050858 30C9 003 050AA0"
    )
    result: Any = decode_packet(pkt.to_dto())
    assert result.get("zone_idx") == "05"
    assert result.get("temperature") is not None
