"""Tests for the Gateway backward compatibility and deprecation shims."""

import warnings

import pytest

from ramses_rf.gateway import Gateway, GatewayConfig


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
    Test that passing undefined kwargs triggers a DeprecationWarning safely.

    This ensures that older versions of downstream libraries passing arbitrary kwargs
    do not crash (TypeError), but instead notify the user to upgrade their config.

    :returns: None
    """
    with pytest.warns(DeprecationWarning, match="deprecated"):
        # We pass a nonsensical kwarg to trigger the graceful warning
        Gateway(port_name="/dev/null", legacy_unsupported_flag=True)


@pytest.mark.asyncio
async def test_gateway_with_config() -> None:
    """
    Test initializing the Gateway using the strictly typed GatewayConfig DTO.

    :returns: None
    """
    config = GatewayConfig(enforce_known_list=True)
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        gwy = Gateway("/dev/null", config=config)

    assert gwy.config.enforce_known_list is True

    deprecation_warnings = [
        w for w in recorded_warnings if issubclass(w.category, DeprecationWarning)
    ]
    assert len(deprecation_warnings) == 0
