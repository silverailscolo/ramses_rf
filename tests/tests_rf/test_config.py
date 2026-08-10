"""Tests for the strip_and_map_traits pipeline (Phase 3a).

These tests verify that ramses_rf's strip+map pipeline correctly:
- Strips ramses_cc-only ``_``-prefixed keys (stage 1)
- Maps known ``_``-prefixed keys to native trait names (stage 2)
- Passes through non-``_`` keys unchanged
- Accepts ``str | list[str]`` for the ``bound`` trait in SCH_TRAITS_HVAC
"""

import asyncio
import contextlib
from typing import Any

import pytest

from ramses_rf.config import (
    SCH_TRAITS,
    GatewayConfig,
    strip_and_map_schema,
    strip_and_map_traits,
    strip_traits,
)
from ramses_rf.gateway import Gateway
from ramses_rf.typing import DeviceIdT


class TestStripAndMapTraits:
    """Unit tests for strip_and_map_traits()."""

    def test_strip_commands(self) -> None:
        """_commands is stripped (ramses_rf doesn't need it)."""
        traits = {"_commands": {"on": "22F1"}, "class": "FAN"}
        result = strip_and_map_traits(traits)
        assert "_commands" not in result
        assert result["class"] == "FAN"

    def test_strip_disabled_name_owner(self) -> None:
        """_disabled, _owner are stripped (ramses_cc-only).

        _name is preserved (not stripped) because ramses_rf's
        SCH_TCS_ZONES_ZON accepts it for zone name hydration
        (ramses-rf/ramses_cc#919: zone names lost after 24h).
        """
        traits = {"_disabled": True, "_name": "My REM", "_owner": "me", "alias": "test"}
        result = strip_and_map_traits(traits)
        assert "_disabled" not in result
        assert "_name" in result  # preserved for zone name hydration (issue 919)
        assert result["_name"] == "My REM"
        assert "_owner" not in result
        assert result["alias"] == "test"

    def test_map_bound_to_bound(self) -> None:
        """_bound maps to bound."""
        traits = {"_bound": "32:153001", "class": "FAN"}
        result = strip_and_map_traits(traits)
        assert result["bound"] == "32:153001"

    def test_map_scheme_to_scheme(self) -> None:
        """_scheme maps to scheme."""
        traits = {"_scheme": "vasco", "class": "FAN"}
        result = strip_and_map_traits(traits)
        assert result["scheme"] == "vasco"

    def test_map_alias_to_alias(self) -> None:
        """_alias maps to alias."""
        traits = {"_alias": "My Device", "class": "SEN"}
        result = strip_and_map_traits(traits)
        assert result["alias"] == "My Device"

    def test_map_faked_to_faked(self) -> None:
        """_faked maps to faked."""
        traits = {"_faked": True, "class": "SEN"}
        result = strip_and_map_traits(traits)
        assert result["faked"] is True

    def test_map_class_to_class(self) -> None:
        """_class maps to class."""
        traits = {"_class": "REM"}
        result = strip_and_map_traits(traits)
        assert result["class"] == "REM"

    def test_list_bound(self) -> None:
        """_bound accepts list[str] (multi-REM binding)."""
        traits = {"_bound": ["32:153001", "32:153002"], "_scheme": "itho"}
        result = strip_and_map_traits(traits)
        assert result["bound"] == ["32:153001", "32:153002"]
        assert result["scheme"] == "itho"

    def test_non_underscore_keys_pass_through(self) -> None:
        """Keys without _ prefix are passed through unchanged."""
        traits = {"class": "FAN", "bound": "32:153001", "scheme": "vasco"}
        result = strip_and_map_traits(traits)
        assert result == traits

    def test_empty_dict(self) -> None:
        """Empty dict returns empty dict."""
        assert strip_and_map_traits({}) == {}

    def test_mixed_keys(self) -> None:
        """Mixed _ and non-_ keys: strip unknown, map known, pass through rest."""
        traits = {
            "_commands": {"on": "22F1"},
            "_bound": "32:153001",
            "_disabled": True,
            "class": "FAN",
            "alias": "My Fan",
        }
        result = strip_and_map_traits(traits)
        assert "_commands" not in result
        assert "_disabled" not in result
        assert result["bound"] == "32:153001"
        assert result["class"] == "FAN"
        assert result["alias"] == "My Fan"

    def test_recursive_nested_dict_strips_underscore(self) -> None:
        """_name inside a nested dict (e.g. a zone) is preserved.

        _name is preserved (not stripped) because ramses_rf's
        SCH_TCS_ZONES_ZON accepts it for zone name hydration
        (ramses-rf/ramses_cc#919: zone names lost after 24h).
        """
        traits = {
            "class": "TCS",
            "zones": {"01": {"_name": "Living Room", "setpoint": 20.0}},
        }
        result = strip_and_map_traits(traits)
        assert result["zones"]["01"]["setpoint"] == 20.0
        assert result["zones"]["01"]["_name"] == "Living Room"  # preserved (issue 919)

    def test_recursive_nested_dict_maps_underscore(self) -> None:
        """_bound inside a nested dict is mapped to bound."""
        traits = {
            "class": "TCS",
            "zones": {"01": {"_bound": "32:153001", "setpoint": 20.0}},
        }
        result = strip_and_map_traits(traits)
        assert result["zones"]["01"]["bound"] == "32:153001"
        assert "_bound" not in result["zones"]["01"]

    def test_recursive_deeply_nested(self) -> None:
        """Recursion works at arbitrary depth.

        _name is preserved (issue 919), _disabled is stripped.
        """
        traits = {
            "class": "TCS",
            "zones": {
                "01": {"_name": "Zone 1", "sub": {"_disabled": True, "ok": 1}},
            },
        }
        result = strip_and_map_traits(traits)
        assert result["zones"]["01"]["_name"] == "Zone 1"  # preserved (issue 919)
        assert "_disabled" not in result["zones"]["01"]["sub"]
        assert result["zones"]["01"]["sub"] == {"ok": 1}


class TestStripAndMapSchema:
    """Unit tests for strip_and_map_schema()."""

    def test_schema_with_device_entries(self) -> None:
        """Schema with device entries: strip+map each device's traits."""
        schema = {
            "main_tcs": "01:145038",
            "32:153001": {"_commands": {"on": "22F1"}, "_class": "REM", "_faked": True},
            "30:160000": {"_bound": "32:153001", "_scheme": "vasco", "class": "FAN"},
        }
        result = strip_and_map_schema(schema)
        assert result["main_tcs"] == "01:145038"
        assert result["32:153001"]["class"] == "REM"
        assert result["32:153001"]["faked"] is True
        assert "_commands" not in result["32:153001"]
        assert result["30:160000"]["bound"] == "32:153001"
        assert result["30:160000"]["scheme"] == "vasco"

    def test_schema_preserves_non_dict_values(self) -> None:
        """Non-dict values (strings, lists) are passed through unchanged."""
        schema = {
            "main_tcs": "01:145038",
            "orphans_heat": ["04:111111", "04:222222"],
        }
        result = strip_and_map_schema(schema)
        assert result == schema


class TestSchTraitsHvacBound:
    """Tests that SCH_TRAITS_HVAC accepts str | list[str] for bound."""

    def test_string_bound(self) -> None:
        """Single string bound (backward compat)."""
        result = SCH_TRAITS({"class": "FAN", "bound": "32:153001", "scheme": "vasco"})
        assert result["bound"] == "32:153001"

    def test_list_bound(self) -> None:
        """List bound (multi-REM binding)."""
        result = SCH_TRAITS(
            {"class": "FAN", "bound": ["32:153001", "32:153002"], "scheme": "itho"}
        )
        assert result["bound"] == ["32:153001", "32:153002"]

    def test_none_bound(self) -> None:
        """None bound (no binding)."""
        result = SCH_TRAITS({"class": "FAN", "bound": None, "scheme": "vasco"})
        assert result["bound"] is None

    def test_no_bound(self) -> None:
        """No bound key at all."""
        result = SCH_TRAITS({"class": "FAN", "scheme": "vasco"})
        assert "bound" not in result or result.get("bound") is None

    def test_bound_without_class_uses_default_hvc(self) -> None:
        """bound is valid even without an explicit class (regression).

        SCH_TRAITS_HVAC defaults ``class`` to ``DevType.HVC`` when absent,
        but that default value must itself pass the class validator, or
        voluptuous falls through to SCH_TRAITS_HEAT (which rejects
        ``bound``) and raises a generic, hard-to-diagnose "not a valid
        value @ data['bound']" error for any HVAC device that has a
        ``bound`` trait but no ``class`` (e.g. a REM/FAN discovered from
        traffic before its class trait was learned).
        """
        result = SCH_TRAITS({"bound": "37:168270"})
        assert result["bound"] == "37:168270"
        assert result["class"] == "HVC"


class TestStripTraits:
    """Unit tests for strip_traits() (stage 1 only — strip, no mapping)."""

    def test_strips_underscore_keys(self) -> None:
        """All _-prefixed keys are removed."""
        traits = {"_commands": {"on": "22F1"}, "_name": "My REM", "class": "FAN"}
        result = strip_traits(traits)
        assert result == {"class": "FAN"}

    def test_does_not_map(self) -> None:
        """strip_traits does NOT map _bound -> bound (stage 1 only)."""
        traits = {"_bound": "32:153001", "class": "FAN"}
        result = strip_traits(traits)
        assert result == {"class": "FAN"}
        assert "bound" not in result

    def test_passes_through_non_underscore(self) -> None:
        """Non-_ keys pass through unchanged."""
        traits = {"class": "FAN", "bound": "32:153001", "scheme": "vasco"}
        result = strip_traits(traits)
        assert result == traits

    def test_empty_dict(self) -> None:
        """Empty dict returns empty dict."""
        assert strip_traits({}) == {}

    def test_recursive_nested(self) -> None:
        """_ keys inside nested dicts are also stripped."""
        traits = {
            "class": "TCS",
            "zones": {"01": {"_name": "Living Room", "setpoint": 20.0}},
        }
        result = strip_traits(traits)
        assert result == {"class": "TCS", "zones": {"01": {"setpoint": 20.0}}}

    def test_recursive_deeply_nested(self) -> None:
        """Recursion works at arbitrary depth."""
        traits = {
            "class": "TCS",
            "zones": {"01": {"_name": "Z1", "sub": {"_disabled": True, "ok": 1}}},
        }
        result = strip_traits(traits)
        assert result == {"class": "TCS", "zones": {"01": {"sub": {"ok": 1}}}}


# --- Known List Pipeline Boundary Tests ---


@pytest.mark.asyncio
async def test_known_list_data_pipeline_boundary() -> None:
    """Verify the known_list pipeline strips L7 traits before L3."""
    raw_known_list: dict[str, dict[str, Any]] = {
        "18:123456": {"class": "HGI", "alias": "MyGateway"},
        "01:111111": {"class": "CTL"},
        "04:222222": {"faked": True, "alias": "FakedSensor"},
    }

    config = GatewayConfig(known_list=raw_known_list)
    loop = asyncio.get_running_loop()
    gateway = Gateway(port_name="/dev/null", config=config, loop=loop)

    assert isinstance(gateway.config.known_list, dict)
    assert gateway.config.known_list["18:123456"]["alias"] == "MyGateway"
    assert gateway.config.hgi_id == "18:123456"

    assert isinstance(gateway.config.mac_filter_list, list)
    assert len(gateway.config.mac_filter_list) == 3
    assert "01:111111" in gateway.config.mac_filter_list

    engine_config = gateway._gwy_config.engine
    assert isinstance(engine_config.known_list, list)
    assert "04:222222" in engine_config.known_list

    for mac in engine_config.known_list:
        assert isinstance(mac, str)

    registry_known_list = await gateway.device_registry.known_list()
    assert isinstance(registry_known_list, dict)

    dev_id = DeviceIdT("04:222222")
    assert registry_known_list[dev_id]["faked"] is True

    with contextlib.suppress(asyncio.CancelledError):
        await gateway.stop()


@pytest.mark.asyncio
async def test_implicit_hgi_discovery_fallback() -> None:
    """Verify GatewayConfig can deduce an HGI without explicit traits."""
    raw_known_list: dict[str, dict[str, Any]] = {
        "18:006402": {},
        "01:145038": {"class": "CTL"},
    }

    config = GatewayConfig(known_list=raw_known_list)
    assert config.hgi_id == "18:006402"
