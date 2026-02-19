"""
Automated regression analysis for Ramses TX packet parsing.

This script performs a side-by-side comparison between the current parsing
logic of the `ramses_tx` library and a previously recorded 'golden' snapshot.
It identifies changes in packet validity or string representation.

Functional Overview:
    1.  **Parse:** Reads the packet log (`regression_packets_sorted.txt`)
        line-by-line, applying the exact logic used in `test_regression_tx.py`.
    2.  **Snapshot Extraction:** Parses the Syrupy AMBR snapshot file.
    3.  **Diff Analysis:** Compares current output against expected results.

Usage:
    Run manually from the project root:
    $ python3 tests/utils/analyze_diff_tx.py
"""

import ast
import datetime
import logging
import re
import sys
from importlib import metadata
from pathlib import Path
from typing import Final, cast

from ramses_tx import Packet
from ramses_tx.exceptions import PacketInvalid

# --- Configuration ---
PACKET_LOG: Final[Path] = Path("tests/fixtures/regression_packets_sorted.txt")
SNAPSHOT_FILE: Final[Path] = Path(
    "tests/tests_tx/__snapshots__/test_regression_tx.ambr"
)
TARGET_SNAPSHOT_KEY: Final[str] = "test_packet_parsing_regression"


def load_expected_state() -> list[str]:
    """Parse the syrupy AMBR file to extract the expected snapshot list.

    :return: The list of expected result strings.
    """
    if not SNAPSHOT_FILE.exists():
        print(f"Error: Snapshot file not found: {SNAPSHOT_FILE}")
        sys.exit(1)

    content = SNAPSHOT_FILE.read_text(encoding="utf-8")

    # Extract the block for the specific snapshot key
    pattern = re.compile(
        r"# name: (?P<key>.*?)\n(?P<value>.*?)(?=\n# name:|\Z)",
        re.DOTALL,
    )

    found_snapshots: dict[str, str] = {
        m.group("key"): m.group("value").strip() for m in pattern.finditer(content)
    }

    raw_value = found_snapshots.get(TARGET_SNAPSHOT_KEY)
    if not raw_value:
        print(f"Error: Could not find snapshot for '{TARGET_SNAPSHOT_KEY}'.")
        sys.exit(1)

    # Robust Syrupy cleanup:
    # 1. Remove the 'list([' prefix
    # 2. Find the last ']' and discard everything after it (to avoid unmatched brackets)
    cleaned_value = raw_value.strip()
    if cleaned_value.startswith("list("):
        cleaned_value = cleaned_value[5:]

    last_bracket = cleaned_value.rfind("]")
    if last_bracket != -1:
        cleaned_value = cleaned_value[: last_bracket + 1]

    try:
        data = ast.literal_eval(cleaned_value)
    except (ValueError, SyntaxError) as err:
        print(f"Error parsing snapshot content: {err}")
        print(f"Cleaned snippet (end): {cleaned_value[-50:]!r}")
        sys.exit(1)

    return cast(list[str], data)


def generate_actual_state() -> list[tuple[int, str, str]]:
    """Process the packet log using current library logic.

    :return: A list of tuples containing line number, raw content, and result.
    """
    if not PACKET_LOG.exists():
        print(f"Error: Packet log not found: {PACKET_LOG}")
        sys.exit(1)

    results: list[tuple[int, str, str]] = []

    with PACKET_LOG.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    for line_no, line in enumerate(lines, start=1):
        clean_line = line.strip()
        if not clean_line or clean_line.startswith("#"):
            continue

        if len(clean_line) < 27:
            res = f"Line {line_no}: Skipped (too short)"
            results.append((line_no, clean_line, res))
            continue

        dtm_str = clean_line[:26]
        pkt_str = clean_line[27:]

        try:
            pkt = Packet.from_file(dtm_str, pkt_str)
            res = f"VALID:   {pkt}"
        except PacketInvalid as err:
            res = f"INVALID: {type(err).__name__}: {err}"
        except ValueError as err:
            res = f"ERROR:   {type(err).__name__}: {err}"

        results.append((line_no, clean_line, res))

    return results


def print_report(expected: list[str], actual: list[tuple[int, str, str]]) -> None:
    """Print the comparison report with summary statistics.

    :param expected: The reference results from the snapshot.
    :param actual: The current results from the packet log.
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        ver = metadata.version("ramses_rf")
    except metadata.PackageNotFoundError:
        ver = "unknown"

    diffs = []
    max_len = max(len(expected), len(actual))
    match_count = 0

    for i in range(max_len):
        exp_val = expected[i] if i < len(expected) else "<MISSING IN SNAPSHOT>"

        if i < len(actual):
            line_no, raw_line, act_val = actual[i]
        else:
            line_no, raw_line, act_val = (-1, "<NONE>", "<MISSING IN LOG>")

        if exp_val == act_val:
            match_count += 1
        else:
            diffs.append(
                {
                    "index": i,
                    "line": line_no,
                    "raw": raw_line,
                    "expected": exp_val,
                    "actual": act_val,
                }
            )

    print("\n" + "=" * 80)
    print("TX LAYER REGRESSION ANALYSIS REPORT")
    print("=" * 80)

    print("\n## METADATA")
    print(f"- **Time:** {now}")
    print(f"- **Library:** `ramses_rf {ver}`")
    print(f"- **Log:** `{PACKET_LOG}`")
    print(f"- **Snapshot:** `{SNAPSHOT_FILE}`")

    print("\n## SUMMARY")
    if not diffs:
        print("SUCCESS: Current parsing matches the Golden Snapshot.")
    else:
        print(f"FAILURE: Found {len(diffs)} discrepancies.")

    print("\n## DETAILS")
    for d in diffs:
        print("-" * 40)
        print(f"SNAPSHOT INDEX: {d['index']}")
        if d["line"] != -1:
            print(f"FILE LINE NO:   {d['line']}")
            print(f"RAW PACKET:     {d['raw']}")

        print(f"EXPECTED: {d['expected']}")
        print(f"ACTUAL:   {d['actual']}")

    print("\n" + "-" * 80)
    print("\n## FINAL STATISTICS")
    print(f"- **Total Records:** {max_len}")
    print(f"- **Matched:** {match_count}")
    print(f"- **Mismatched:** {len(diffs)}")

    print("\n" + "=" * 80)
    print("END OF REPORT")
    print("=" * 80)


def main() -> None:
    """Main execution flow."""
    logging.getLogger("ramses_rf").setLevel(logging.CRITICAL)
    logging.getLogger("ramses_tx").setLevel(logging.CRITICAL)

    print("Generating current state from packet log...")
    actual_data = generate_actual_state()

    print("Loading expected state from snapshot...")
    expected_data = load_expected_state()

    print("Comparing states...")
    print_report(expected_data, actual_data)


if __name__ == "__main__":
    main()
