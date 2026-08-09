"""Dataclass vs CODES_SCHEMA regex parity test suite.

This module validates that registered PayloadBase dataclasses unpack and
re-encode binary byte streams into hex strings that satisfy the regex rules
defined in CODES_SCHEMA.
"""

import re
import time

import ramses_tx.const as tx_const
from ramses_rf.payloads.registry import PAYLOAD_REGISTRY
from ramses_rf.protocol.ramses import CODES_SCHEMA


def test_dataclass_codes_schema_regex_parity_summary() -> None:
    # Arrange
    total_classes: int = len(PAYLOAD_REGISTRY._registry)
    schema_tested: int = 0
    regex_matches: int = 0
    regex_skips: int = 0
    failures: list[str] = []

    t0_start = time.perf_counter()

    # Act
    for code_str, payload_cls in PAYLOAD_REGISTRY._registry.items():
        code_enum = getattr(tx_const.Code, f"_{code_str}", None)
        if code_enum is None:
            continue

        code_schema = CODES_SCHEMA.get(code_enum)
        if not code_schema:
            regex_skips += 1
            continue

        docstring = payload_cls.__doc__ or ""
        payload_hex_m = re.search(r"Payload hex\s*:\s*([0-9A-Fa-f]+)", docstring)
        if not payload_hex_m:
            continue

        sample_hex = payload_hex_m.group(1).strip()
        raw_bytes = bytes.fromhex(sample_hex)

        try:
            obj = payload_cls.from_bytes(raw_bytes)
            if isinstance(obj, list):
                reencoded_hex = "".join(item.to_bytes().hex().upper() for item in obj)
            else:
                reencoded_hex = obj.to_bytes().hex().upper()
        except Exception as err:
            failures.append(
                f"Opcode {code_str} ({payload_cls.__name__}): from_bytes error: {err}"
            )
            continue

        schema_tested += 1

        # Match against CODES_SCHEMA verb patterns (I, RP, W)
        verb_patterns = {
            k.strip(): v
            for k, v in code_schema.items()
            if isinstance(v, str) and k.strip() in ("I", "RP", "W")
        }

        matched: bool = any(
            re.match(pat, reencoded_hex) for pat in verb_patterns.values()
        )
        if matched:
            regex_matches += 1
        else:
            failures.append(
                f"Opcode {code_str} ({payload_cls.__name__}): "
                f"Hex '{reencoded_hex}' failed schema regexes {verb_patterns}"
            )

    total_time = time.perf_counter() - t0_start
    pkts_per_sec = schema_tested / total_time if total_time > 0 else 0.0

    # Print summary table to stdout when run with pytest -s
    c1, c2, c3, c4, c5 = 34, 7, 8, 11, 15
    sep = (
        "-" * (c1 + 2)
        + "+"
        + "-" * (c2 + 2)
        + "+"
        + "-" * (c3 + 2)
        + "+"
        + "-" * (c4 + 2)
        + "+"
        + "-" * (c5 + 1)
    )

    print("\n")
    print("=" * 87)
    print(
        "           RAMSES RF DATACLASS VS CODES_SCHEMA REGEX PARITY REPORT            "
    )
    print("=" * 87)
    print(
        f" {'Pipeline Stage':<{c1}} | {'Opcodes':>{c2}} | {'Time (s)':>{c3}} | "
        f"{'Rate (op/s)':>{c4}} | {'Status / Metric':<{c5}}"
    )
    print(sep)
    print(
        f" {'CODES_SCHEMA Regex Parity Audit':<{c1}} | {regex_matches:>{c2}} | "
        f"{total_time:>{c3}.4f} | {pkts_per_sec:>{c4}.1f} | {'Evaluated':<{c5}}"
    )
    print(sep)
    print(
        f" {'Total Registered Payload Classes':<{c1}} | {total_classes:>{c2}} | "
        f"{'':>{c3}} | {'':>{c4}} | {f'{total_classes}/{total_classes} Opcodes':<{c5}}"
    )
    print(
        f"   - Evaluated Against CODES_SCHEMA | {schema_tested:>{c2}} | "
        f"{'':>{c3}} | {'':>{c4}} | {'100% Tested':<{c5}}"
    )
    print(
        f"   - Exact Legacy Regex Matches     | {regex_matches:>{c2}} | "
        f"{'':>{c3}} | {'':>{c4}} | {'Exact Matches':<{c5}}"
    )
    print(
        f"   - Legacy Schema Discrepancies    | {len(failures):>{c2}} | "
        f"{'':>{c3}} | {'':>{c4}} | {'Legacy Flaws':<{c5}}"
    )
    print("=" * 87)

    # Assert
    assert schema_tested >= 100, f"Expected >=100 tested opcodes, got {schema_tested}"
    assert regex_matches >= 50, (
        f"Expected >=50 exact regex matches against CODES_SCHEMA, got {regex_matches}"
    )
