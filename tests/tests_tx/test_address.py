#!/usr/bin/env python3
"""Test suite for ramses_tx.address module."""

import pytest

from ramses_tx.address import HGI_DEV_ADDR, Address, is_hgi_id


class TestIsHgiId:
    """Tests for is_hgi_id — the HGI (18:) prefix check."""

    @pytest.mark.parametrize(
        "device_id",
        ["18:000730", "18:001234", HGI_DEV_ADDR.id],
    )
    def test_hgi_ids(self, device_id: str) -> None:
        assert is_hgi_id(device_id)

    @pytest.mark.parametrize(
        "device_id",
        ["01:123456", "32:000032", "--:------", "63:262142", "180:12345"],
    )
    def test_non_hgi_ids(self, device_id: str) -> None:
        assert not is_hgi_id(device_id)

    @pytest.mark.parametrize("value", [None, 123, b"18:000730", ""])
    def test_non_string_values(self, value: object) -> None:
        assert not is_hgi_id(value)


class TestAddressHgi:
    """The well-known HGI address has the 18 device type."""

    def test_hgi_dev_addr_type(self) -> None:
        assert HGI_DEV_ADDR.type == "18"
        assert is_hgi_id(HGI_DEV_ADDR.id)

    def test_address_type_matches_helper(self) -> None:
        addr = Address(HGI_DEV_ADDR.id)
        assert is_hgi_id(addr.id) == (addr.type == HGI_DEV_ADDR.type)
