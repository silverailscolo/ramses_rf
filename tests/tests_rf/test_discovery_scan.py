# --- START OF FILE test_discovery_scan.py ---

"""Tests for the passive device scan engine (ramses_rf.discovery_scan).

These tests verify:
- Device classification by prefix and verb/code pairs
- In-memory discovery list management
- JSON export/import round-trip
- Confidence scoring
- Zone binding extraction
- Known device filtering
- No topology mutation (read-only)
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime as dt
from typing import Any
from unittest.mock import MagicMock

import pytest

from ramses_rf.const import DevType
from ramses_rf.discovery_scan import (
    DiscoveredDevice,
    DiscoveryScan,
    _classify,
    _extract_zone_idx,
    _initial_confidence,
    _is_valid_address,
    _recompute_confidence,
)
from ramses_tx.dtos import PacketDTO

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_dto(
    src: str = "04:056053",
    dst: str = "01:145038",
    addr3: str = "--:------",
    code: str = "3150",
    verb: str = " I",
    payload: str = "02C8",
    rssi: str = "-72",
) -> PacketDTO:
    """Create a PacketDTO for testing."""
    return PacketDTO(
        timestamp=dt.now(),
        rssi=rssi,
        verb=verb,
        seq="00",
        addr1=src,
        addr2=dst,
        addr3=addr3,
        code=code,
        length="006",
        payload=payload,
    )


def make_mock_gateway(
    known_list: dict[str, Any] | None = None,
    schema: dict[str, Any] | None = None,
    device_by_id: dict[str, Any] | None = None,
) -> MagicMock:
    """Create a mock Gateway with the minimum interface DiscoveryScan needs."""
    gwy = MagicMock()
    gwy.device_registry = MagicMock()
    gwy.device_registry.device_by_id = device_by_id or {}
    gwy._gwy_config = MagicMock()
    gwy._gwy_config.known_list = known_list or {}
    gwy._gwy_config.schema = schema or {}
    gwy.add_raw_pkt_handler = MagicMock(return_value=lambda: None)
    return gwy


# ---------------------------------------------------------------------------
# Classification helper tests
# ---------------------------------------------------------------------------


class TestIsValidAddress:
    """Tests for _is_valid_address."""

    def test_valid_device_id(self) -> None:
        assert _is_valid_address("04:056053") is True

    def test_valid_ctl_id(self) -> None:
        assert _is_valid_address("01:145038") is True

    def test_broadcast_address_rejected(self) -> None:
        assert _is_valid_address("18:73030") is False

    def test_empty_rejected(self) -> None:
        assert _is_valid_address("") is False

    def test_no_colon_rejected(self) -> None:
        assert _is_valid_address("04056053") is False

    def test_too_short_rejected(self) -> None:
        assert _is_valid_address("04:056") is False

    def test_placeholder_rejected(self) -> None:
        assert _is_valid_address("--:------") is False

    def test_all_zeros_rejected(self) -> None:
        assert _is_valid_address("00:------") is False


class TestExtractZoneIdx:
    """Tests for _extract_zone_idx."""

    def test_valid_zone_idx(self) -> None:
        assert _extract_zone_idx("02C8") == "02"

    def test_hw_zone(self) -> None:
        # "HW" is not valid hex — should return None
        assert _extract_zone_idx("HW...") is None

    def test_empty_payload(self) -> None:
        assert _extract_zone_idx("") is None

    def test_short_payload(self) -> None:
        assert _extract_zone_idx("0") is None


class TestClassify:
    """Tests for _classify."""

    def test_prefix_ctl(self) -> None:
        assert _classify("01:145038", "2E04", " I", is_src=True) == DevType.CTL

    def test_prefix_trv(self) -> None:
        assert _classify("04:056053", "3150", " I", is_src=True) == DevType.TRV

    def test_prefix_dhw(self) -> None:
        assert _classify("07:046947", "10A0", " I", is_src=True) == DevType.DHW

    def test_prefix_bdr(self) -> None:
        assert _classify("10:067219", "0008", " I", is_src=True) == DevType.BDR

    def test_prefix_fan(self) -> None:
        assert _classify("32:157747", "31DA", " I", is_src=True) == DevType.FAN

    def test_prefix_rem(self) -> None:
        assert _classify("37:179540", "22F1", " I", is_src=True) == DevType.REM

    def test_vc_pair_fan(self) -> None:
        """I 31DA → FAN (from HVAC_KLASS_BY_VC_PAIR)."""
        assert _classify("32:157747", "31DA", " I", is_src=True) == DevType.FAN

    def test_vc_pair_rem(self) -> None:
        """I 22F1 → REM."""
        assert _classify("37:179540", "22F1", " I", is_src=True) == DevType.REM

    def test_vc_pair_co2(self) -> None:
        """I 1298 → CO2."""
        assert _classify("37:123456", "1298", " I", is_src=True) == DevType.CO2

    def test_hvac_prefix_wins_over_vc_pair(self) -> None:
        """A FAN (32:) sending 22F1 should stay FAN, not become REM."""
        assert _classify("32:157747", "22F1", " I", is_src=True) == DevType.FAN

    def test_vc_pair_for_non_hvac_prefix(self) -> None:
        """A non-HVAC prefix sending an HVAC code should use the VC pair."""
        # 18: is HGI, but if it sends I 31DA it's acting as FAN
        assert _classify("18:123456", "31DA", " I", is_src=True) == DevType.FAN

    def test_ctl_only_code(self) -> None:
        """A device sending 1030 (CTL-only code) is classified as CTL."""
        assert _classify("01:145038", "1030", " I", is_src=True) == DevType.CTL

    def test_ctl_only_code_not_from_dst(self) -> None:
        """CTL-only code from dst (not src) should not classify as CTL."""
        result = _classify("01:145038", "1030", " I", is_src=False)
        # Falls back to prefix
        assert result == DevType.CTL  # prefix 01 = CTL anyway

    def test_unknown_prefix(self) -> None:
        """Unknown prefix with no VC match returns DEV."""
        assert _classify("99:999999", "0001", " I", is_src=True) == DevType.DEV

    def test_reclassify_with_dev(self) -> None:
        """Re-classify using accumulated codes_seen."""
        dev = DiscoveredDevice(
            device_id="01:145038",
            first_seen="2026-07-01T10:00:00",
            last_seen="2026-07-01T10:00:00",
            likely_type="DEV",
            codes_seen=["1030", "2E04"],
        )
        result = _classify("01:145038", "0001", " I", is_src=True, dev=dev)
        assert result == DevType.CTL


class TestConfidence:
    """Tests for confidence scoring."""

    def test_initial_high_for_binding_code(self) -> None:
        assert _initial_confidence(True, "3150", " I") == "high"

    def test_initial_medium_for_src(self) -> None:
        assert _initial_confidence(True, "0001", " I") == "medium"

    def test_initial_low_for_dst(self) -> None:
        assert _initial_confidence(False, "0001", " I") == "low"

    def test_recompute_high_with_binding(self) -> None:
        dev = DiscoveredDevice(
            device_id="04:056053",
            first_seen="",
            last_seen="",
            likely_type="TRV",
            zone_idx="02",
            bound_to="01:145038",
        )
        assert _recompute_confidence(dev) == "high"

    def test_recompute_high_with_ctl_code(self) -> None:
        dev = DiscoveredDevice(
            device_id="01:145038",
            first_seen="",
            last_seen="",
            likely_type="CTL",
            codes_seen=["1030"],
        )
        assert _recompute_confidence(dev) == "high"

    def test_recompute_medium_multiple_src(self) -> None:
        dev = DiscoveredDevice(
            device_id="04:056053",
            first_seen="",
            last_seen="",
            likely_type="TRV",
            src_count=3,
        )
        assert _recompute_confidence(dev) == "medium"

    def test_recompute_low_dst_only(self) -> None:
        dev = DiscoveredDevice(
            device_id="04:056053",
            first_seen="",
            last_seen="",
            likely_type="TRV",
            dst_count=5,
            src_count=0,
        )
        assert _recompute_confidence(dev) == "low"


# ---------------------------------------------------------------------------
# DiscoveredDevice dataclass tests
# ---------------------------------------------------------------------------


class TestDiscoveredDevice:
    """Tests for the DiscoveredDevice dataclass."""

    def test_to_dict(self) -> None:
        dev = DiscoveredDevice(
            device_id="04:056053",
            first_seen="2026-07-01T10:00:00",
            last_seen="2026-07-01T10:01:00",
            likely_type="TRV",
            codes_seen=["1060", "3150"],
            bound_to="01:145038",
            zone_idx="02",
            rssi=-72.0,
            confidence="high",
        )
        d = dev.to_dict()
        assert d["device_id"] == "04:056053"
        assert d["likely_type"] == "TRV"
        assert d["codes_seen"] == ["1060", "3150"]
        assert d["bound_to"] == "01:145038"
        assert d["zone_idx"] == "02"

    def test_from_dict(self) -> None:
        data = {
            "device_id": "04:056053",
            "first_seen": "2026-07-01T10:00:00",
            "last_seen": "2026-07-01T10:01:00",
            "likely_type": "TRV",
            "codes_seen": ["1060", "3150"],
            "bound_to": "01:145038",
            "zone_idx": "02",
            "rssi": -72.0,
            "confidence": "high",
            "is_battery": True,
            "src_count": 5,
            "dst_count": 2,
        }
        dev = DiscoveredDevice.from_dict(data)
        assert dev.device_id == "04:056053"
        assert dev.likely_type == "TRV"
        assert dev.is_battery is True

    def test_from_dict_ignores_extra_fields(self) -> None:
        """from_dict should ignore fields not in the dataclass."""
        data = {
            "device_id": "04:056053",
            "first_seen": "",
            "last_seen": "",
            "likely_type": "TRV",
            "status": "accepted",  # ramses_cc concern, not engine
            "enabled": True,
        }
        dev = DiscoveredDevice.from_dict(data)
        assert dev.device_id == "04:056053"
        assert not hasattr(dev, "status")

    def test_round_trip(self) -> None:
        """to_dict → from_dict → should be identical."""
        dev = DiscoveredDevice(
            device_id="04:056053",
            first_seen="2026-07-01T10:00:00",
            last_seen="2026-07-01T10:01:00",
            likely_type="TRV",
            codes_seen=["1060", "3150"],
            rssi=-72.0,
            confidence="medium",
        )
        dev2 = DiscoveredDevice.from_dict(dev.to_dict())
        assert dev2.device_id == dev.device_id
        assert dev2.codes_seen == dev.codes_seen
        assert dev2.rssi == dev.rssi


# ---------------------------------------------------------------------------
# DiscoveryScan engine tests
# ---------------------------------------------------------------------------


class TestDiscoveryScanLifecycle:
    """Tests for start/stop lifecycle."""

    def test_start_registers_handler(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        scan.start()
        assert gwy.add_raw_pkt_handler.called
        assert scan.is_running is True

    def test_stop_unregisters_handler(self) -> None:
        gwy = make_mock_gateway()
        removed = MagicMock()
        gwy.add_raw_pkt_handler = MagicMock(return_value=removed)
        scan = DiscoveryScan(gwy)
        scan.start()
        scan.stop()
        assert removed.called
        assert scan.is_running is False

    def test_start_twice_warns(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        scan.start()
        scan.start()  # should not double-register
        assert gwy.add_raw_pkt_handler.call_count == 1

    def test_stop_without_start_is_noop(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        scan.stop()  # should not raise


class TestDiscoveryScanPacketHandling:
    """Tests for packet processing logic."""

    def test_new_device_from_src(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        scan._process_packet(make_dto(src="04:056053", dst="01:145038", code="3150"))
        dev = scan.get_device("04:056053")
        assert dev is not None
        assert dev.likely_type == "TRV"
        assert dev.confidence == "high"  # 3150 is a binding code
        assert dev.src_count == 1
        assert "3150" in dev.codes_seen

    def test_new_device_from_dst(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        scan._process_packet(make_dto(src="04:056053", dst="01:145038", code="3150"))
        # dst (01:145038) should also be recorded
        dev = scan.get_device("01:145038")
        assert dev is not None
        assert dev.dst_count == 1
        assert dev.confidence == "low"  # only seen as dst

    def test_known_device_skipped(self) -> None:
        gwy = make_mock_gateway(known_list={"04:056053": {}})
        scan = DiscoveryScan(gwy)
        scan._process_packet(make_dto(src="04:056053", code="3150"))
        assert scan.get_device("04:056053") is None

    def test_known_in_schema_skipped(self) -> None:
        gwy = make_mock_gateway(schema={"01:145038": {}})
        scan = DiscoveryScan(gwy)
        scan._process_packet(make_dto(src="01:145038", code="2E04"))
        assert scan.get_device("01:145038") is None

    def test_known_in_registry_skipped(self) -> None:
        gwy = make_mock_gateway(device_by_id={"04:056053": MagicMock()})
        scan = DiscoveryScan(gwy)
        scan._process_packet(make_dto(src="04:056053", code="3150"))
        assert scan.get_device("04:056053") is None

    def test_rssi_running_average(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        # First packet
        scan._process_packet(make_dto(src="04:056053", code="3150", rssi="-70"))
        dev = scan.get_device("04:056053")
        assert dev is not None
        assert dev.rssi == -70.0
        # Second packet — should average
        scan._process_packet(make_dto(src="04:056053", code="30C9", rssi="-80"))
        assert dev.rssi == -75.0

    def test_rssi_not_updated_from_dst(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        scan._process_packet(
            make_dto(src="04:056053", dst="01:145038", code="3150", rssi="-70")
        )
        # dst device should not get rssi from this packet
        dst_dev = scan.get_device("01:145038")
        assert dst_dev is not None
        assert dst_dev.rssi is None

    def test_zone_binding_extracted(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        scan._process_packet(
            make_dto(src="04:056053", dst="01:145038", code="3150", payload="02C8")
        )
        dev = scan.get_device("04:056053")
        assert dev is not None
        assert dev.zone_idx == "02"
        assert dev.bound_to == "01:145038"
        assert dev.confidence == "high"

    def test_codes_seen_deduplicated_and_sorted(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        scan._process_packet(make_dto(src="04:056053", code="3150"))
        scan._process_packet(make_dto(src="04:056053", code="1060"))
        scan._process_packet(make_dto(src="04:056053", code="3150"))  # duplicate
        dev = scan.get_device("04:056053")
        assert dev is not None
        assert dev.codes_seen == ["1060", "3150"]  # sorted, no dupes

    def test_battery_flag_set(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        scan._process_packet(make_dto(src="04:056053", code="1060"))
        dev = scan.get_device("04:056053")
        assert dev is not None
        assert dev.is_battery is True

    def test_addr3_processed(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        scan._process_packet(
            make_dto(
                src="01:145038",
                dst="18:006402",
                addr3="04:056053",
                code="000C",
            )
        )
        dev = scan.get_device("04:056053")
        assert dev is not None
        assert dev.dst_count == 1  # addr3 treated as non-src

    def test_broadcast_address_skipped(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        scan._process_packet(make_dto(src="01:145038", dst="18:73030", code="2E04"))
        # 18:73030 is broadcast — should not be in discovery list
        assert scan.get_device("18:73030") is None

    def test_hvac_fan_discovered(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        scan._process_packet(
            make_dto(src="32:157747", dst="18:006402", code="31DA", verb=" I")
        )
        dev = scan.get_device("32:157747")
        assert dev is not None
        assert dev.likely_type == "FAN"

    def test_hvac_rem_discovered(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        scan._process_packet(
            make_dto(src="37:179540", dst="32:157747", code="22F1", verb=" I")
        )
        dev = scan.get_device("37:179540")
        assert dev is not None
        assert dev.likely_type == "REM"

    def test_dirty_flag_set_on_new_device(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        assert scan.is_dirty is False
        scan._process_packet(make_dto(src="04:056053", code="3150"))
        assert scan.is_dirty is True

    def test_clear_dirty(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        scan._process_packet(make_dto(src="04:056053", code="3150"))
        scan.clear_dirty()
        assert scan.is_dirty is False


class TestDiscoveryScanGetDevices:
    """Tests for get_devices with filters."""

    def test_get_all_devices(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        scan._process_packet(make_dto(src="04:056053", code="3150"))
        scan._process_packet(make_dto(src="01:145038", code="2E04"))
        assert len(scan.get_devices()) == 2

    def test_filter_by_type(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        scan._process_packet(make_dto(src="04:056053", code="3150"))
        scan._process_packet(make_dto(src="01:145038", code="2E04"))
        trvs = scan.get_devices(likely_type="TRV")
        assert len(trvs) == 1
        assert trvs[0].device_id == "04:056053"

    def test_filter_by_min_confidence(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        # 04:056053 sends binding code → high
        scan._process_packet(make_dto(src="04:056053", dst="01:145038", code="3150"))
        # 01:145038 only seen as dst → low
        high_only = scan.get_devices(min_confidence="high")
        assert len(high_only) == 1
        assert high_only[0].device_id == "04:056053"

    def test_device_count(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        assert scan.device_count() == 0
        scan._process_packet(make_dto(src="04:056053", code="3150"))
        assert scan.device_count() == 2  # src + dst both recorded


class TestDiscoveryScanRemoveDevice:
    """Tests for remove_device."""

    def test_remove_existing(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        scan._process_packet(make_dto(src="04:056053", code="3150"))
        assert scan.remove_device("04:056053") is True
        assert scan.get_device("04:056053") is None

    def test_remove_nonexistent(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        assert scan.remove_device("99:999999") is False


class TestDiscoveryScanExportImport:
    """Tests for JSON export/import."""

    def test_export_json_structure(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        scan._process_packet(make_dto(src="04:056053", dst="01:145038", code="3150"))
        data = json.loads(scan.export_json())
        assert "version" in data
        assert "devices" in data
        assert len(data["devices"]) == 2

    def test_export_import_round_trip(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        scan._process_packet(make_dto(src="04:056053", dst="01:145038", code="3150"))
        scan._process_packet(make_dto(src="04:056053", code="1060"))
        exported = scan.export_json()

        # New scan, import the data
        scan2 = DiscoveryScan(make_mock_gateway())
        scan2.import_json(exported)
        assert scan2.device_count() == 2
        dev = scan2.get_device("04:056053")
        assert dev is not None
        assert dev.likely_type == "TRV"
        assert "3150" in dev.codes_seen
        assert "1060" in dev.codes_seen

    def test_import_clears_dirty(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        scan._process_packet(make_dto(src="04:056053", code="3150"))
        assert scan.is_dirty is True
        scan.import_json(scan.export_json())
        assert scan.is_dirty is False

    def test_export_sorted_by_device_id(self) -> None:
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        scan._process_packet(make_dto(src="04:056053", code="3150"))
        scan._process_packet(make_dto(src="01:145038", code="2E04"))
        data = json.loads(scan.export_json())
        ids = [d["device_id"] for d in data["devices"]]
        assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# Integration: no topology mutation
# ---------------------------------------------------------------------------


class TestNoTopologyMutation:
    """Verify the scan never mutates topology."""

    def test_no_get_device_calls(self) -> None:
        """The scan should never call get_device on the registry."""
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        scan._process_packet(make_dto(src="04:056053", code="3150"))
        scan._process_packet(make_dto(src="01:145038", code="2E04"))
        # get_device should never have been called
        gwy.device_registry.get_device.assert_not_called()

    def test_no_schema_modification(self) -> None:
        """The scan should not modify the schema."""
        original_schema: dict[str, Any] = {"01:145038": {}}
        gwy = make_mock_gateway(schema=original_schema)
        scan = DiscoveryScan(gwy)
        scan._process_packet(make_dto(src="04:056053", dst="01:145038", code="3150"))
        # Schema should be unchanged
        assert gwy._gwy_config.schema == original_schema


# ---------------------------------------------------------------------------
# Integration: out-of-order discovery (TRV before CTL)
# ---------------------------------------------------------------------------


class TestOutOfOrderDiscovery:
    """Tests for the out-of-order discovery scenario."""

    def test_trv_seen_before_ctl(self) -> None:
        """TRV broadcasts to a CTL address before CTL is seen.

        The CTL should be recorded as a referenced-but-unseen device.
        """
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        # TRV sends to CTL — CTL is dst
        scan._process_packet(make_dto(src="04:056053", dst="01:145038", code="3150"))
        # TRV should be discovered with binding info
        trv = scan.get_device("04:056053")
        assert trv is not None
        assert trv.bound_to == "01:145038"
        assert trv.zone_idx == "02"
        # CTL should also be recorded (as dst)
        ctl = scan.get_device("01:145038")
        assert ctl is not None
        assert ctl.confidence == "low"  # only seen as dst so far

    def test_ctl_appears_later_enriches(self) -> None:
        """When CTL starts sending, its confidence should upgrade."""
        gwy = make_mock_gateway()
        scan = DiscoveryScan(gwy)
        # Phase 1: TRV seen, CTL only as dst
        scan._process_packet(make_dto(src="04:056053", dst="01:145038", code="3150"))
        ctl = scan.get_device("01:145038")
        assert ctl is not None
        assert ctl.confidence == "low"

        # Phase 2: CTL sends its own traffic
        scan._process_packet(make_dto(src="01:145038", dst="18:006402", code="2E04"))
        assert ctl.src_count == 1
        assert "2E04" in ctl.codes_seen
        # Confidence should upgrade to medium (src_count >= 1 + codes >= 2)
        assert ctl.confidence in ("medium", "high")


# ---------------------------------------------------------------------------
# Integration: virtual RF with mixed CH + HVAC traffic
# ---------------------------------------------------------------------------


class TestVirtualRfIntegration:
    """Integration test using the virtual RF to simulate live traffic.

    Sends mixed CH + HVAC packets through a virtual serial port and verifies
    the scan engine discovers and classifies them correctly, even with
    enforce_known_list=True.
    """

    @pytest.mark.asyncio
    async def test_mixed_ch_hvac_discovery(self) -> None:
        """Scan discovers CH + HVAC devices from simulated RF traffic.

        Uses the virtual RF harness to send raw packet frames through a
        virtual serial port, just like real RF traffic.
        """
        from tests_rf.virtual_rf import HgiFwTypes, VirtualRf

        HGI_ID = "18:222222"
        CTL_ID = "01:145038"
        TRV_ID = "04:056053"
        DHW_ID = "07:046947"
        BDR_ID = "10:067219"
        FAN_ID = "32:157747"
        REM_ID = "37:179540"

        # Raw packet frames (evofw3 format: no RSSI, gateway adds it)
        # Must be terminated with \r\n for the virtual RF to process them
        # Payload length must match the declared hex length byte
        raw_pkts: list[bytes] = [
            # CTL broadcasts system mode
            b" I --- 01:145038 18:222222 --:------ 2E04 003 000200\r\n",
            # CTL sends zone device map (000C)
            b" I --- 01:145038 18:222222 --:------ 000C 006 000F0035D5B1\r\n",
            # TRV sends heat demand to CTL (zone 02)
            b" I --- 04:056053 01:145038 --:------ 3150 006 02C800000000\r\n",
            # TRV sends battery info
            b" I --- 04:056053 01:145038 --:------ 1060 003 00C800\r\n",
            # DHW sensor sends to CTL
            b" I --- 07:046947 01:145038 --:------ 10A0 006 01C800000000\r\n",
            # BDR sends state
            b" I --- 10:067219 01:145038 --:------ 0008 002 00FF\r\n",
            # FAN broadcasts fan state (31DA, 30 bytes payload)
            b" I --- 32:157747 --:------ 32:157747 31DA 030 00EF007FFF3A2F04C404E204A904BA68000003C8C80000EFEF20A91F0500\r\n",
            # FAN broadcasts fan info (31D9, 17 bytes payload)
            b" I --- 32:157747 --:------ 32:157747 31D9 017 001A020020202020202020202020202008\r\n",
            # REM sends fan mode to FAN
            b" I --- 37:179540 32:157747 --:------ 22F1 003 000107\r\n",
            # REM sends battery
            b" I --- 37:179540 32:157747 --:------ 1060 003 00C800\r\n",
        ]

        rf = VirtualRf(2)
        try:
            rf.set_gateway(rf.ports[0], HGI_ID, fw_type=HgiFwTypes.EVOFW3)

            from unittest.mock import patch

            from ramses_rf.gateway import Gateway, GatewayConfig
            from ramses_tx.config import EngineConfig

            engine_config = EngineConfig(
                disable_qos=True,
                enforce_known_list=True,
                disable_sending=True,
            )
            gwy_config = GatewayConfig(
                disable_discovery=True,
                enable_eavesdrop=False,
                engine=engine_config,
                known_list={HGI_ID: {}},  # only HGI — everything else unknown
                schema={},
            )

            with patch("ramses_tx.discovery.comports", rf.comports):
                gwy = Gateway(rf.ports[0], config=gwy_config)
                await gwy.start()

            scan = DiscoveryScan(gwy)
            scan.start()

            # Dump packets into the virtual RF (one at a time to avoid buffer overflow)
            for pkt in raw_pkts:
                await rf.dump_frames_to_rf([pkt])
                await asyncio.sleep(0.05)
            await asyncio.sleep(1)  # let packets fully process

            scan.stop()

            # Verify registry only has HGI
            registry_ids = set(gwy.device_registry.device_by_id.keys())
            assert registry_ids == {HGI_ID}, (
                f"Registry should only have HGI, got: {registry_ids}"
            )

            # Verify scan discovered all unknown devices
            discovered = {d.device_id: d for d in scan.get_devices()}
            assert CTL_ID in discovered, (
                f"CTL not discovered: {list(discovered.keys())}"
            )
            assert TRV_ID in discovered, (
                f"TRV not discovered: {list(discovered.keys())}"
            )
            assert DHW_ID in discovered, (
                f"DHW not discovered: {list(discovered.keys())}"
            )
            assert BDR_ID in discovered, (
                f"BDR not discovered: {list(discovered.keys())}"
            )
            assert FAN_ID in discovered, (
                f"FAN not discovered: {list(discovered.keys())}"
            )
            assert REM_ID in discovered, (
                f"REM not discovered: {list(discovered.keys())}"
            )

            # Verify classification
            assert discovered[CTL_ID].likely_type == "CTL"
            assert discovered[TRV_ID].likely_type == "TRV"
            assert discovered[DHW_ID].likely_type == "DHW"
            assert discovered[BDR_ID].likely_type == "BDR"
            assert discovered[FAN_ID].likely_type == "FAN"
            assert discovered[REM_ID].likely_type == "REM"

            # Verify TRV has zone binding
            trv = discovered[TRV_ID]
            assert trv.zone_idx == "02"
            assert trv.bound_to == CTL_ID
            assert trv.confidence == "high"
            assert trv.is_battery is True

            # Verify FAN is classified as FAN (not REM, despite 22F1)
            fan = discovered[FAN_ID]
            assert fan.likely_type == "FAN"
            assert "31DA" in fan.codes_seen

            # Verify REM is classified as REM
            rem = discovered[REM_ID]
            assert rem.likely_type == "REM"
            assert "22F1" in rem.codes_seen

            await gwy.stop()
        finally:
            await rf.stop()

    @pytest.mark.asyncio
    async def test_resume_after_export_import(self) -> None:
        """Scan can export its state, a new scan can import it and continue.

        Simulates an HA restart: scan1 discovers devices, exports JSON,
        scan2 imports the JSON and continues scanning, discovering new
        devices that appeared after the restart.
        """
        from tests_rf.virtual_rf import HgiFwTypes, VirtualRf

        HGI_ID = "18:333333"
        CTL_ID = "01:145038"
        TRV_ID = "04:056053"
        FAN_ID = "32:157747"

        # Phase 1 packets: CTL + TRV
        phase1_pkts: list[bytes] = [
            b" I --- 01:145038 18:333333 --:------ 2E04 003 000200\r\n",
            b" I --- 04:056053 01:145038 --:------ 3150 006 02C800000000\r\n",
        ]

        # Phase 2 packets: FAN (new device after "restart")
        phase2_pkts: list[bytes] = [
            b" I --- 32:157747 --:------ 32:157747 31DA 030 00EF007FFF3A2F04C404E204A904BA68000003C8C80000EFEF20A91F0500\r\n",
        ]

        rf = VirtualRf(2)
        try:
            rf.set_gateway(rf.ports[0], HGI_ID, fw_type=HgiFwTypes.EVOFW3)

            from unittest.mock import patch

            from ramses_rf.gateway import Gateway, GatewayConfig
            from ramses_tx.config import EngineConfig

            engine_config = EngineConfig(
                disable_qos=True,
                enforce_known_list=True,
                disable_sending=True,
            )
            gwy_config = GatewayConfig(
                disable_discovery=True,
                enable_eavesdrop=False,
                engine=engine_config,
                known_list={HGI_ID: {}},
                schema={},
            )

            # --- Phase 1: scan and export ---
            with patch("ramses_tx.discovery.comports", rf.comports):
                gwy = Gateway(rf.ports[0], config=gwy_config)
                await gwy.start()

            scan1 = DiscoveryScan(gwy)
            scan1.start()
            for pkt in phase1_pkts:
                await rf.dump_frames_to_rf([pkt])
                await asyncio.sleep(0.05)
            await asyncio.sleep(0.5)
            scan1.stop()

            devices1 = {d.device_id: d for d in scan1.get_devices()}
            assert CTL_ID in devices1
            assert TRV_ID in devices1
            assert FAN_ID not in devices1  # FAN not seen yet

            # Export state
            json_state = scan1.export_json()
            assert CTL_ID in json_state
            assert TRV_ID in json_state

            await gwy.stop()

            # --- Phase 2: new scan imports state and continues ---
            with patch("ramses_tx.discovery.comports", rf.comports):
                gwy2 = Gateway(rf.ports[0], config=gwy_config)
                await gwy2.start()

            scan2 = DiscoveryScan(gwy2)
            scan2.import_json(json_state)  # resume from exported state

            # Verify imported devices are present before scanning
            imported = {d.device_id: d for d in scan2.get_devices()}
            assert CTL_ID in imported
            assert TRV_ID in imported
            assert FAN_ID not in imported  # not yet

            scan2.start()
            for pkt in phase2_pkts:
                await rf.dump_frames_to_rf([pkt])
                await asyncio.sleep(0.05)
            await asyncio.sleep(0.5)
            scan2.stop()

            # Verify all devices now present
            devices2 = {d.device_id: d for d in scan2.get_devices()}
            assert CTL_ID in devices2  # from import
            assert TRV_ID in devices2  # from import
            assert FAN_ID in devices2  # newly discovered
            assert devices2[FAN_ID].likely_type == "FAN"

            await gwy2.stop()
        finally:
            await rf.stop()

    @pytest.mark.asyncio
    async def test_hvac_co2_and_hum_classification(self) -> None:
        """Scan correctly classifies CO2 and HUM devices via VC pairs.

        37: prefix is ambiguous (REM, CO2, HUM all use it), so the VC pair
        must distinguish them:
        - I 1298 → CO2
        - I 22F1 → REM
        - I 31E0 → HUM (if in HVAC_KLASS_BY_VC_PAIR)
        """
        from tests_rf.virtual_rf import HgiFwTypes, VirtualRf

        HGI_ID = "18:444444"
        CO2_ID = "37:111111"
        REM_ID = "37:222222"

        raw_pkts: list[bytes] = [
            # CO2 sends air quality (I 1298)
            b" I --- 37:111111 18:444444 --:------ 1298 013 00EF007FFF3A2F04C404E204A9\r\n",
            # REM sends fan mode (I 22F1)
            b" I --- 37:222222 32:157747 --:------ 22F1 003 000107\r\n",
        ]

        rf = VirtualRf(2)
        try:
            rf.set_gateway(rf.ports[0], HGI_ID, fw_type=HgiFwTypes.EVOFW3)

            from unittest.mock import patch

            from ramses_rf.gateway import Gateway, GatewayConfig
            from ramses_tx.config import EngineConfig

            engine_config = EngineConfig(
                disable_qos=True,
                enforce_known_list=True,
                disable_sending=True,
            )
            gwy_config = GatewayConfig(
                disable_discovery=True,
                enable_eavesdrop=False,
                engine=engine_config,
                known_list={HGI_ID: {}},
                schema={},
            )

            with patch("ramses_tx.discovery.comports", rf.comports):
                gwy = Gateway(rf.ports[0], config=gwy_config)
                await gwy.start()

            scan = DiscoveryScan(gwy)
            scan.start()
            for pkt in raw_pkts:
                await rf.dump_frames_to_rf([pkt])
                await asyncio.sleep(0.05)
            await asyncio.sleep(0.5)
            scan.stop()

            discovered = {d.device_id: d for d in scan.get_devices()}

            # CO2 should be classified as CO2 (via I 1298 VC pair)
            assert CO2_ID in discovered, (
                f"CO2 not discovered: {list(discovered.keys())}"
            )
            assert discovered[CO2_ID].likely_type == "CO2", (
                f"Expected CO2, got {discovered[CO2_ID].likely_type}"
            )

            # REM should be classified as REM (via I 22F1 VC pair)
            assert REM_ID in discovered, (
                f"REM not discovered: {list(discovered.keys())}"
            )
            assert discovered[REM_ID].likely_type == "REM", (
                f"Expected REM, got {discovered[REM_ID].likely_type}"
            )

            # Both are 37: prefix but different types — VC pair disambiguates
            assert discovered[CO2_ID].likely_type != discovered[REM_ID].likely_type

            await gwy.stop()
        finally:
            await rf.stop()
