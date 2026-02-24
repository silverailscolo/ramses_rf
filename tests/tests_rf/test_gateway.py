"""Tests for the Gateway backward compatibility and deprecation shims."""

import warnings

import pytest

from ramses_rf.gateway import Gateway


@pytest.mark.asyncio
async def test_gateway_positional_port_name() -> None:
    """
    Test that initializing Gateway with a positional port_name succeeds.

    This ensures standard initialization does not trigger deprecation warnings.

    :returns: None
    """
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        Gateway("/dev/null")

    deprecation_warnings = [
        w for w in recorded_warnings if issubclass(w.category, DeprecationWarning)
    ]
    assert len(deprecation_warnings) == 0


@pytest.mark.asyncio
async def test_gateway_keyword_port_name() -> None:
    """
    Test that port_name can be passed as a keyword argument.

    This specifically tests the fix for Issue #501 where the positional-only
    marker ('/') caused a TypeError for legacy integrations like ramses_cc.

    :returns: None
    """
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        Gateway(port_name="/dev/null")

    deprecation_warnings = [
        w for w in recorded_warnings if issubclass(w.category, DeprecationWarning)
    ]
    assert len(deprecation_warnings) == 0


@pytest.mark.asyncio
async def test_gateway_legacy_kwargs_warning() -> None:
    """
    Test that passing undefined kwargs triggers a DeprecationWarning.

    This ensures that older versions of ramses_cc passing arbitrary kwargs
    do not crash (TypeError), but do notify the user to upgrade their config.

    :returns: None
    """
    with pytest.warns(DeprecationWarning, match="deprecated"):
        Gateway(port_name="/dev/null", legacy_unsupported_flag=True)
