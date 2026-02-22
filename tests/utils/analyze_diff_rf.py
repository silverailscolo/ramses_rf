"""
Automated regression analysis for Ramses RF state synchronization.

This script performs a side-by-side comparison between the current state of a
mocked Ramses RF Gateway and a previously recorded 'golden' snapshot. It is
designed to debug regressions without requiring the generation of intermediate
JSON files or modifying the primary test suite.

Functional Overview:
    1.  **Replay:** Replays a specific packet log (`regression_packets_sorted.txt`)
        through a virtual Gateway in memory. Internal library logging is
        suppressed to provide a clean analysis output.
    2.  **State Generation:** Serializes the resulting Gateway topology,
        devices, and system settings into a dictionary.
    3.  **Snapshot Extraction:** Parses the Syrupy AMBR snapshot file
        associated with the regression tests. It converts Syrupy's custom
        serialization (e.g., dict(...) and list(...)) into Python literals.
    4.  **Diff Analysis:** Identifies discrepancies in device attributes,
        missing/added devices, or global schema changes.
    5.  **Packet Tracing:** For every detected difference, it scans the
        original packet log to provide the relevant log lines for context.

Referenced Files:
    * **tests/fixtures/regression_packets_sorted.txt**: The source packet log.
    * **tests/tests_rf/__snapshots__/test_regression_rf.ambr**: The 'golden'
        reference file containing the Syrupy snapshots.

Usage:
    Run manually from the project root:
    $ python3 tests/utils/analyze_diff_rf.py
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import logging
import re
import sys
from collections import defaultdict
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast
from unittest.mock import AsyncMock, patch

from ramses_rf import Gateway
from ramses_rf.device import DeviceHeat, DeviceHvac
from ramses_rf.gateway import GatewayConfig
from ramses_tx.exceptions import TransportError
from ramses_tx.transport import SZ_READER_TASK

if TYPE_CHECKING:
    pass

# --- Configuration ---
PACKET_LOG: Final[Path] = Path("tests/fixtures/regression_packets_sorted.txt")
SNAPSHOT_FILE: Final[Path] = Path(
    "tests/tests_rf/__snapshots__/test_regression_rf.ambr"
)
TARGET_SNAPSHOT_KEY: Final[str] = "test_gateway_replay_regression"


def serialize_device(dev: Any) -> dict[str, Any]:
    """Helper to serialize a device's state for snapshotting.

    Identifies attributes based on device type (Heat vs HVAC) and existence
    of properties to create a deterministic state snapshot.

    :param dev: The device object to serialize.
    :type dev: Any
    :return: A dictionary representing the device state.
    :rtype: dict[str, Any]
    """
    # Base attributes for all devices
    data: dict[str, Any] = {
        "id": dev.id,
        "type": type(dev).__name__,
        "is_alive": getattr(dev, "_is_alive", None),
        "battery_low": getattr(dev, "battery_low", None),
    }

    # Capture specific state for Heating devices
    if isinstance(dev, DeviceHeat):
        # Topology
        zone = getattr(dev, "zone", None)
        tcs = getattr(dev, "tcs", None)

        data.update(
            {
                "tcs_id": tcs.id if tcs else None,
                "zone_idx": getattr(zone, "idx", None),
            }
        )

        # General Heating Attributes
        # We iterate and try to access each attribute.
        for attr in (
            "active",  # BDR Switch
            "actuator_cycle",  # Actuators
            "actuator_state",
            "heat_demand",  # Many heat devices
            "heat_demands",  # UFC
            "modulation_level",  # OTB/Actuators
            "relay_demand",  # BDR/UFC
            "setpoint",  # Thermostats/TRVs
            "setpoints",  # UFC
            "temperature",  # Sensors
            "window_open",  # TRV
        ):
            try:
                # getattr triggers the @property logic
                val = getattr(dev, attr, None)
                if val is not None:
                    data[attr] = val
            except AttributeError:
                continue  # Attribute strictly does not exist on this object
            except Exception as err:
                # Capture functional regressions (bugs) in the library code as string data
                data[attr] = f"<{type(err).__name__}: {err}>"

        # OpenTherm Bridge (OTB) Specifics
        if getattr(dev, "_SLUG", None) == "OTB":
            for attr in (
                "boiler_output_temp",
                "boiler_return_temp",
                "boiler_setpoint",
                "ch_max_setpoint",
                "ch_water_pressure",
                "dhw_flow_rate",
                "dhw_setpoint",
                "dhw_temp",
                "fault_present",
                "flame_active",
                "max_rel_modulation",
                "oem_code",
                "otc_active",
                "outside_temp",
                "rel_modulation_level",
            ):
                try:
                    val = getattr(dev, attr, None)
                    if val is not None:
                        data[attr] = val
                except AttributeError:
                    continue
                except Exception as err:
                    data[attr] = f"<{type(err).__name__}: {err}>"

    # Capture specific state for HVAC devices
    if isinstance(dev, DeviceHvac):
        for attr in (
            "air_quality",
            "air_quality_base",
            "boost_timer",
            "bypass_mode",
            "bypass_position",
            "bypass_state",
            "co2_level",
            "dewpoint_temp",
            "exhaust_fan_speed",
            "exhaust_flow",
            "exhaust_temp",
            "fan_info",
            "fan_mode",
            "fan_rate",
            "filter_remaining",
            "indoor_humidity",
            "indoor_temp",
            "outdoor_humidity",
            "outdoor_temp",
            "post_heat",
            "pre_heat",
            "presence_detected",
            "remaining_mins",
            "speed_cap",
            "supply_fan_speed",
            "supply_flow",
            "supply_temp",
        ):
            try:
                val = getattr(dev, attr, None)
                if val is not None:
                    data[attr] = val
            except AttributeError:
                continue
            except Exception as err:
                data[attr] = f"<{type(err).__name__}: {err}>"

    # Return sorted dictionary for deterministic snapshots
    return {k: v for k, v in sorted(data.items())}


async def generate_actual_state() -> dict[str, Any]:
    """Replay packet log in memory and generate the current system state.

    :return: The generated system state dictionary.
    :rtype: dict[str, Any]
    """
    gwy = Gateway(
        None,
        input_file=str(PACKET_LOG),
        config=GatewayConfig(
            disable_discovery=True,
            reduce_processing=0,
        ),
        disable_sending=True,
    )

    # Replicate the test environment: Patch sending methods to prevent Read-Only errors.
    mock_send = AsyncMock(return_value=None)

    with patch.object(gwy, "async_send_cmd", mock_send):
        # 1. Start the Gateway processing
        with contextlib.suppress(TransportError):
            await gwy.start()

        # 2. Wait for the Transport to finish reading the file
        if gwy._transport:
            reader_task = gwy._transport.get_extra_info(SZ_READER_TASK)
            if reader_task:
                await reader_task

        # 3. Extract State for Snapshot (Matches test_regression_rf.py flow)
        system_state: dict[str, Any] = {
            "schema": gwy.schema,
            "devices": [
                serialize_device(d) for d in sorted(gwy.devices, key=lambda x: x.id)
            ],
        }

        # Add specific System (TCS) details if a TCS was discovered
        if gwy.tcs:
            system_state["tcs"] = {
                "id": gwy.tcs.id,
                "zones": {
                    z.idx: {
                        "name": z.name,
                        "type": type(z).__name__,
                        "sensor": z.sensor.id if z.sensor else None,
                        "actuators": sorted([a.id for a in z.actuators]),
                    }
                    for z in sorted(gwy.tcs.zones, key=lambda x: x.idx)
                },
            }

        # 4. Stop Gateway
        with contextlib.suppress(asyncio.CancelledError, TransportError):
            await gwy.stop()

    return system_state


def load_expected_state() -> dict[str, Any]:
    """Parse the syrupy AMBR file to extract the expected snapshot.

    :return: The parsed dictionary from the snapshot file.
    :rtype: dict[str, Any]
    """
    if not SNAPSHOT_FILE.exists():
        print(f"Error: Snapshot file not found: {SNAPSHOT_FILE}")
        sys.exit(1)

    import ast

    content = SNAPSHOT_FILE.read_text(encoding="utf-8")

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

    # Convert syrupy's dictionary/list representation back to Python literal format
    py_literal = raw_value.replace("dict({", "{").replace("list([", "[")
    py_literal = py_literal.replace("})", "}").replace("])", "]")

    return cast(dict[str, Any], ast.literal_eval(py_literal))


def find_diffs(old: dict[str, Any], new: dict[str, Any]) -> dict[str, list[str]]:
    """Compare two states and identify differences.

    :param old: The reference state.
    :type old: dict[str, Any]
    :param new: The current state.
    :type new: dict[str, Any]
    :return: A dictionary of differences keyed by entity ID.
    :rtype: dict[str, list[str]]
    """
    diffs: dict[str, list[str]] = defaultdict(list)

    old_devs = {d.get("id"): d for d in old.get("devices", [])}
    new_devs = {d.get("id"): d for d in new.get("devices", [])}

    all_ids = sorted(set(old_devs.keys()) | set(new_devs.keys()))

    for dev_id in all_ids:
        did = str(dev_id)
        if did not in old_devs:
            diffs[did].append("Device ADDED")
            continue
        if did not in new_devs:
            diffs[did].append("Device REMOVED")
            continue

        d_old = old_devs[did]
        d_new = new_devs[did]

        all_keys = set(d_old.keys()) | set(d_new.keys())
        for k in sorted(all_keys):
            if d_old.get(k) != d_new.get(k):
                diffs[did].append(f"{k}: {d_old.get(k)!r} -> {d_new.get(k)!r}")

    if old.get("schema") != new.get("schema"):
        diffs["GLOBAL"].append("Schema mismatch detected.")

    return dict(diffs)


def extract_packets(target_ids: set[str]) -> dict[str, list[str]]:
    """Scan log file for packets related to affected IDs.

    :param target_ids: Set of IDs to filter for.
    :type target_ids: set[str]
    :return: Mapping of ID to list of relevant log lines.
    :rtype: dict[str, list[str]]
    """
    if not PACKET_LOG.exists():
        return {}

    packet_map: dict[str, list[str]] = defaultdict(list)
    with open(PACKET_LOG, encoding="utf-8", errors="ignore") as f:
        for line in f:
            clean_line = line.strip()
            for tid in target_ids:
                if tid in clean_line:
                    packet_map[tid].append(clean_line)
    return dict(packet_map)


def print_report(diffs: dict[str, list[str]], packets: dict[str, list[str]]) -> None:
    """Print the final analysis report in a Gemini-friendly format.

    :param diffs: Found differences.
    :type diffs: dict[str, list[str]]
    :param packets: Relevant packets for those differences.
    :type packets: dict[str, list[str]]
    :return: None
    :rtype: None
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Safely get library version
    try:
        ver = metadata.version("ramses_rf")
    except metadata.PackageNotFoundError:
        ver = "unknown"

    print("\n" + "=" * 80)
    print("AI-READY REGRESSION ANALYSIS REPORT")
    print("=" * 80)

    # --- LLM Context Section ---
    print("\n## LLM PROMPT CONTEXT")
    print("This is a diagnostic output from `tests/utils/analyze_diff_rf.py`.")
    print("It represents a fresh regression analysis run comparing the current")
    print("in-memory Gateway state (after replaying the packet log) against the")
    print("official 'Golden Snapshot' (expected state).")
    print("\n**Please use this data to:**")
    print("1.  Verify the success of the most recent code modifications.")
    print("2.  Analyze remaining discrepancies for logic errors or expected")
    print("    behavior shifts.")

    # --- System Meta Data ---
    print("\n## SYSTEM METADATA")
    print(f"- **Execution Time:** {now}")
    print(f"- **Library Version:** `ramses_rf {ver}`")
    print(f"- **Packet Log Source:** `{PACKET_LOG}`")
    print(f"- **Snapshot Source:** `{SNAPSHOT_FILE}`")

    # --- Summary ---
    total_diffs = len(diffs)
    added = sum(1 for v in diffs.values() if "Device ADDED" in v)
    removed = sum(1 for v in diffs.values() if "Device REMOVED" in v)

    print("\n## EXECUTIVE SUMMARY")
    print(f"- **Status:** {'REGRESSION DETECTED' if diffs else 'MATCH'}")
    print(f"- **Affected Entities:** {total_diffs}")
    print(f"- **New Devices Found:** {added}")
    print(f"- **Missing Devices:** {removed}")

    if not diffs:
        print("\nSUCCESS: The current library state matches the snapshot.")
        return

    # --- Detailed Diffs ---
    print("\n## DETAILED DIFFERENCES")
    for entity_id in sorted(diffs.keys()):
        print(f"\n### ENTITY: `{entity_id}`")
        print("#### Changes:")
        for change in diffs[entity_id]:
            print(f"- {change}")

        pkts = packets.get(entity_id, [])
        if pkts:
            print("\n#### Relevant Packets (Context):")
            print("```text")
            for p in pkts[-15:]:
                print(p)
            print("```")
        print("---")

    print("\n" + "=" * 80)
    print("END OF REPORT")
    print("=" * 80)


async def main() -> None:
    """Main execution flow.

    :return: None
    :rtype: None
    """
    logging.getLogger("ramses_rf").setLevel(logging.CRITICAL)
    logging.getLogger("ramses_tx").setLevel(logging.CRITICAL)
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)

    print("Replaying packets and generating state...")
    actual = await generate_actual_state()

    print("Loading expected state from AMBR snapshot...")
    expected = load_expected_state()

    diffs = find_diffs(expected, actual)
    packets = extract_packets(set(diffs.keys()))

    print_report(diffs, packets)


if __name__ == "__main__":
    asyncio.run(main())
