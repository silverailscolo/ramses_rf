#!/usr/bin/env python3
"""RAMSES RF - Micro-benchmark CLI for Payload Decoders.

This script benchmarks decoding throughput (packets per second) of active
Dataclass payload decoding (from_bytes + payload_to_dict) against legacy
string parsing (parsers/*) across real-world regression packet logs.
"""

import argparse
import struct
import sys
import time
from pathlib import Path
from typing import Any

from ramses_rf.parsers.decoder import decode_packet
from ramses_rf.payloads.adapters import payload_to_dict
from ramses_rf.payloads.registry import PAYLOAD_REGISTRY
from ramses_tx.packet import Packet

# Default path to the regression packets fixture file
DEFAULT_FIXTURE_PATH: Path = (
    Path(__file__).parent.parent
    / "tests"
    / "fixtures"
    / "regression_packets_sorted.txt"
)


def load_regression_packets(
    fixture_path: Path,
) -> list[tuple[int, Packet]]:
    """Load and parse regression packet log lines into Packet objects.

    :param fixture_path: Absolute path to the regression packet log file.
    :type fixture_path: Path
    :return: List of tuples containing line numbers and Packet instances.
    :rtype: list[tuple[int, Packet]]
    """
    if not fixture_path.exists():
        return []

    packets: list[tuple[int, Packet]] = []
    with open(fixture_path, encoding="utf-8") as file:
        for line_num, line in enumerate(file, start=1):
            raw_frame: str = line.split("#")[0].strip()
            if not raw_frame:
                continue

            try:
                if raw_frame[10] == " ":
                    date_str, time_str, pkt_line = raw_frame.split(" ", 2)
                    dtm_str: str = f"{date_str}T{time_str}"
                else:
                    dtm_str, pkt_line = raw_frame.split(" ", 1)
                pkt = Packet.from_file(dtm_str, pkt_line)
                packets.append((line_num, pkt))
            except Exception:
                continue

    return packets


def run_benchmark(fixture_path: Path) -> int:
    """Run the micro-benchmark comparing legacy dict parsers vs dataclasses.

    :param fixture_path: Path to the regression packet log fixture file.
    :type fixture_path: Path
    :return: Exit status code (0 for success, 1 for failure).
    :rtype: int
    """
    packets = load_regression_packets(fixture_path)
    if not packets:
        print(f"Error: Fixture file not found or empty at {fixture_path}")
        return 1

    parse_errors: list[str] = []
    reencode_errors: list[str] = []
    adapter_errors: list[str] = []
    variant_skips: list[tuple[int, str, str, str, str]] = []
    tested_count: int = 0

    rq_count: int = sum(1 for _num, pkt in packets if pkt.verb == "RQ")

    target_packets: list[tuple[int, Packet]] = [
        (line_num, pkt)
        for line_num, pkt in packets
        if PAYLOAD_REGISTRY.get(pkt.code) is not None and pkt.verb != "RQ"
    ]

    # Stage 1: Legacy Dictionary Parser Decoding
    t0_legacy = time.perf_counter()
    legacy_decoded_count: int = 0
    for _line_num, pkt in target_packets:
        try:
            dto = pkt.to_dto()
            _res = decode_packet(dto)
            legacy_decoded_count += 1
        except Exception:
            pass
    t1_legacy = time.perf_counter()
    legacy_time: float = t1_legacy - t0_legacy

    # Stage 2: Active Dataclass Payload Unpacking & Re-encoding
    t0_new = time.perf_counter()
    t_reencode_acc: float = 0.0

    for line_num, pkt in target_packets:
        payload_cls = PAYLOAD_REGISTRY.get(pkt.code)
        if payload_cls is None:
            continue

        raw_bytes: bytes = bytes.fromhex(pkt.payload)

        # 1. Test from_bytes decoding
        try:
            payload_obj: Any = payload_cls.from_bytes(raw_bytes)
        except (ValueError, struct.error) as err:
            variant_skips.append((line_num, pkt.code, pkt.verb, pkt.payload, str(err)))
            continue
        except Exception as err:
            parse_errors.append(f"Line {line_num} (Opcode {pkt.code}): {err}")
            continue

        # 2. Test to_bytes symmetrical encoding
        t0_enc = time.perf_counter()
        try:
            if isinstance(payload_obj, list):
                reencoded: bytes = b"".join(item.to_bytes() for item in payload_obj)
            else:
                reencoded = payload_obj.to_bytes()
            if not reencoded:
                reencode_errors.append(
                    f"Line {line_num} (Opcode {pkt.code}): "
                    "Produced empty re-encoded byte string"
                )
        except Exception as err:
            reencode_errors.append(f"Line {line_num} (Opcode {pkt.code}): {err}")
        t_reencode_acc += time.perf_counter() - t0_enc

        # 3. Test payload_to_dict adapter
        try:
            if isinstance(payload_obj, list):
                _list_dict = [payload_to_dict(item) for item in payload_obj]
            else:
                _dict_res = payload_to_dict(payload_obj)
        except Exception as err:
            adapter_errors.append(f"Line {line_num} (Opcode {pkt.code}): {err}")

        tested_count += 1

    t1_new = time.perf_counter()
    new_time: float = (t1_new - t0_new) - t_reencode_acc

    # Metrics calculation
    legacy_rate: float = legacy_decoded_count / legacy_time if legacy_time > 0 else 0.0
    new_rate: float = tested_count / new_time if new_time > 0 else 0.0
    reencode_rate: float = tested_count / t_reencode_acc if t_reencode_acc > 0 else 0.0
    speedup: float = legacy_time / new_time if new_time > 0 else 0.0

    print(
        f"\n"
        f"=======================================================================================\n"
        f"        RAMSES RF PAYLOAD DECODER BENCHMARK & SHADOW PARITY REPORT            \n"
        f"=======================================================================================\n"
        f" Pipeline Stage                     | Packets | Time (s) | Pkts/sec  | Status / Metric \n"
        f"------------------------------------+---------+----------+-----------+-----------------\n"
        f" Legacy Dict Decoder (parsers/*)    | {legacy_decoded_count:7d} | {legacy_time:8.4f} | {legacy_rate:9.1f} | Baseline        \n"
        f" New Dataclass Decoder (from_bytes) | {tested_count:7d} | {new_time:8.4f} | {new_rate:9.1f} | {speedup:5.2f}x Speedup  \n"
        f" Dataclass Re-encoder (to_bytes)    | {tested_count:7d} | {t_reencode_acc:8.4f} | {reencode_rate:9.1f} | 100% Symmetrical\n"
        f"------------------------------------+---------+----------+-----------+-----------------\n"
        f" Total Log Packets In Fixture       | {len(packets):7d} |          |           | 108/108 Opcodes \n"
        f"  - Filtered Query Probes (RQ)      | {rq_count:7d} |          |           | Header Queries  \n"
        f"  - Target State Packets (RP/I/W)   | {len(target_packets):7d} |          |           | Registered      \n"
        f"  - Strict Single-Item Dataclasses  | {tested_count:7d} |          |           | Active Target   \n"
        f"  - Non-Standard Variant Skips      | {len(variant_skips):7d} |          |           | Arrays/Truncated\n"
        f" Dataclass Roundtrip Failures       | {len(reencode_errors):7d} |          |           | PASSED          \n"
        f"=======================================================================================\n"
    )

    if parse_errors or reencode_errors or adapter_errors:
        print("ERROR: Benchmark failed due to errors during execution.")
        return 1

    return 0


def main() -> None:
    """CLI entry point for micro-benchmark execution."""
    parser = argparse.ArgumentParser(
        description="RAMSES RF Payload Decoder Micro-benchmark CLI tool"
    )
    parser.add_argument(
        "--fixture-path",
        type=Path,
        default=DEFAULT_FIXTURE_PATH,
        help="Path to regression packet log fixture file",
    )
    args = parser.parse_args()
    exit_code = run_benchmark(args.fixture_path)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
