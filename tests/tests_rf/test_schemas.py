"""Unit tests for voluptuous schema definitions in ramses_rf.schemas."""

import pytest
import voluptuous as vol

from ramses_rf.schemas import (
    SCH_DOM_ID,
    SCH_UFH_INDEX,
    SCH_ZON_INDEX,
    error_renamed_key,
)


def test_sch_dom_id_validation() -> None:
    """Verify SCH_DOM_ID validates 2-character hex domain IDs."""
    # Valid domain IDs
    assert SCH_DOM_ID("00") == "00"
    assert SCH_DOM_ID("FA") == "FA"
    assert SCH_DOM_ID("FC") == "FC"

    # Invalid domain IDs
    with pytest.raises(vol.Invalid):
        SCH_DOM_ID("0")
    with pytest.raises(vol.Invalid):
        SCH_DOM_ID("FFF")
    with pytest.raises(vol.Invalid):
        SCH_DOM_ID("zz")


def test_sch_zon_index_validation() -> None:
    """Verify SCH_ZON_INDEX validates zone index format."""
    # Valid zone indices
    assert SCH_ZON_INDEX("00") == "00"
    assert SCH_ZON_INDEX("09") == "09"
    assert SCH_ZON_INDEX("0A") == "0A"
    assert SCH_ZON_INDEX("0B") == "0B"

    # Invalid zone indices
    with pytest.raises(vol.Invalid):
        SCH_ZON_INDEX("0C")
    with pytest.raises(vol.Invalid):
        SCH_ZON_INDEX("10")


def test_sch_ufh_index_validation() -> None:
    """Verify SCH_UFH_INDEX validates UFH circuit index format."""
    # Valid circuit indices (00 - 08)
    assert SCH_UFH_INDEX("00") == "00"
    assert SCH_UFH_INDEX("08") == "08"

    # Invalid circuit indices
    with pytest.raises(vol.Invalid):
        SCH_UFH_INDEX("09")
    with pytest.raises(vol.Invalid):
        SCH_UFH_INDEX("10")


def test_error_renamed_key_raises() -> None:
    """Verify error_renamed_key validator helper raises voluptuous error."""
    validator = error_renamed_key("new_feature_key")
    with pytest.raises(
        vol.Invalid,
        match="the key name has changed: rename it to 'new_feature_key'",
    ):
        validator("old_val")
