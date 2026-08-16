# --- START OF FILE test_multi_tcs_dhw_isolation.py ---

"""Tests for DHW isolation in multi-controller (multi-TCS) setups.

Verifies:
- Unassociated DHW sensors do not route to arbitrary fallback systems.
- Multi-controller setups route DHW opcodes only to systems with DHW.
- DiscoveryScan establishes bound_to for DHW sensors from directed packets.
"""

from __future__ import annotations

from datetime import datetime as dt
from typing import Any
from unittest.mock import MagicMock

from ramses_rf.const import Code, DevType, Verb
from ramses_rf.discovery_scan import DiscoveryScan
from ramses_rf.state_projector import _get_dhw_zone_from_msg
from ramses_tx.address import Address
from ramses_tx.dtos import PacketDTO


def make_dto(
    src: str = "07:045491",
    dst: str = "--:------",
    addr3: str = "--:------",
    code: str = Code._1260,
    verb: str = Verb.I_,
    payload: str = "000771",
) -> PacketDTO:
    """Create a PacketDTO for testing."""
    return PacketDTO(
        timestamp=dt.now(),
        rssi="-65",
        verb=verb,
        seq="00",
        addr1=src,
        addr2=dst,
        addr3=addr3,
        code=code,
        length=f"{len(payload) // 2:03d}",
        payload=payload,
        raw_payload=payload,
    )


def make_mock_gateway() -> MagicMock:
    """Create a minimal mock Gateway for DiscoveryScan."""
    gwy = MagicMock()
    gwy.device_registry = MagicMock()
    gwy.device_registry.device_by_id = {}
    gwy._gwy_config = MagicMock()
    gwy._gwy_config.known_list = {}
    gwy._gwy_config.schema = {}
    gwy.add_raw_packet_handler = MagicMock(return_value=lambda: None)
    return gwy


class MockDevice:
    """Mock device without dynamic attributes."""

    def __init__(
        self,
        dev_type: str,
        slug: str,
        tcs: Any = None,
        dhw: Any = None,
    ) -> None:
        self.type = dev_type
        self._SLUG = slug
        self.tcs = tcs
        self._tcs = tcs
        if dhw is not None:
            self.dhw = dhw


def test_get_dhw_zone_from_msg_unassociated_returns_none() -> None:
    # Arrange
    msg = MagicMock()
    msg.code = Code._1260
    msg.src = Address("07:999999")

    source_device = MockDevice("07", DevType.DHW)

    # Act
    result = _get_dhw_zone_from_msg(msg, source_device)

    # Assert
    assert result is None


def test_get_dhw_zone_from_msg_multi_tcs_isolation() -> None:
    # Arrange
    dhw_zone_mock = MagicMock()

    tcs_with_dhw = MagicMock()
    tcs_with_dhw.id = "01:111111"
    tcs_with_dhw.dhw = dhw_zone_mock

    tcs_without_dhw = MagicMock()
    tcs_without_dhw.id = "01:222222"
    tcs_without_dhw.dhw = None

    # Device associated with tcs_with_dhw
    dhw_sensor = MockDevice("07", DevType.DHW, tcs=tcs_with_dhw)

    msg_dhw = MagicMock()
    msg_dhw.code = Code._1260
    msg_dhw.src = Address("07:045491")

    # Controller without DHW sending 10A0
    msg_ctl_no_dhw = MagicMock()
    msg_ctl_no_dhw.code = Code._10A0
    msg_ctl_no_dhw.src = Address("01:222222")

    ctl_no_dhw_dev = MockDevice("01", DevType.CTL, tcs=tcs_without_dhw)

    # Act
    res_dhw = _get_dhw_zone_from_msg(msg_dhw, dhw_sensor)
    res_no_dhw = _get_dhw_zone_from_msg(msg_ctl_no_dhw, ctl_no_dhw_dev)

    # Assert
    assert res_dhw is dhw_zone_mock
    assert res_no_dhw is None


def test_discovery_scan_dhw_directed_rq_sets_bound_to() -> None:
    # Arrange
    scan = DiscoveryScan(gateway=make_mock_gateway())
    dto = make_dto(
        src="01:161591",
        dst="07:045491",
        code=Code._10A0,
        verb=Verb.RQ,
        payload="00",
    )

    # Act
    scan._process_packet(dto)
    devices = {d.device_id: d for d in scan.get_devices()}

    # Assert
    assert "07:045491" in devices
    dhw_dev = devices["07:045491"]
    assert dhw_dev.bound_to == "01:161591"
    assert dhw_dev.confidence == "high"


def test_discovery_scan_dhw_directed_rp_sets_bound_to() -> None:
    # Arrange
    scan = DiscoveryScan(gateway=make_mock_gateway())
    dto = make_dto(
        src="07:045491",
        dst="01:161591",
        code=Code._1260,
        verb=Verb.RP,
        payload="000771",
    )

    # Act
    scan._process_packet(dto)
    devices = {d.device_id: d for d in scan.get_devices()}

    # Assert
    assert "07:045491" in devices
    dhw_dev = devices["07:045491"]
    assert dhw_dev.bound_to == "01:161591"
    assert dhw_dev.confidence == "high"


def test_discovery_scan_dhw_broadcast_remains_unbound() -> None:
    # Arrange
    scan = DiscoveryScan(gateway=make_mock_gateway())
    dto = make_dto(
        src="07:045491",
        dst="--:------",
        code=Code._1260,
        verb=Verb.I_,
        payload="000771",
    )

    # Act
    scan._process_packet(dto)
    devices = {d.device_id: d for d in scan.get_devices()}

    # Assert
    assert "07:045491" in devices
    dhw_dev = devices["07:045491"]
    assert dhw_dev.bound_to is None
