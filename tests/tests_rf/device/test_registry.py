# tests/tests_rf/test_device_registry.py
"""Tests for the decoupled independent Device Registry."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock

import pytest

from ramses_rf.address import Address
from ramses_rf.config import GatewayConfig
from ramses_rf.devices.dev_filter import DeviceFilter
from ramses_rf.devices.dev_registry import DeviceRegistry
from ramses_rf.enums import TopologyAction
from ramses_rf.exceptions import DeviceNotFoundError, SchemaInconsistentError
from ramses_rf.models import DeviceTraits, TopologyChangedEvent
from ramses_rf.typing import DeviceIdT
from ramses_tx.address import HGI_DEV_ADDR

if TYPE_CHECKING:
    from ramses_rf.devices.dev_base import Device
    from ramses_rf.messages import Message

_LOGGER = logging.getLogger(__name__)


@pytest.fixture
def mock_device_factory() -> MagicMock:
    """Provide a mock device factory callback.

    :returns: A MagicMock simulating device_factory_cb.
    :rtype: MagicMock
    """
    return MagicMock()


@pytest.fixture
def standalone_registry(mock_device_factory: MagicMock) -> DeviceRegistry:
    """Provide a standalone DeviceRegistry instantiated with zero Gateway
    context.

    :param mock_device_factory: The mocked entity creation callback.
    :type mock_device_factory: MagicMock
    :returns: A clean DeviceRegistry instance.
    :rtype: DeviceRegistry
    """
    config = GatewayConfig()
    config.engine.enforce_known_list = False

    device_filter = DeviceFilter(
        include=[],
        exclude=[],
        unwanted=[],
        enforce_known_list=False,
        hgi_id_provider=lambda: None,
    )

    return DeviceRegistry(
        device_filter=device_filter,
        config=config,
        device_factory_cb=mock_device_factory,
    )


def test_registry_add_and_retrieve_device(
    standalone_registry: DeviceRegistry,
) -> None:
    """Test adding a device explicitly to the registry tracking dictionaries.

    :param standalone_registry: The test device registry fixture.
    :type standalone_registry: DeviceRegistry
    :returns: None
    """
    mock_dev = MagicMock()
    mock_dev.id = cast(DeviceIdT, "01:123456")

    # Verify initial state
    assert mock_dev.id not in standalone_registry.device_by_id

    # Add and verify identity tracking
    standalone_registry._add_device(mock_dev)
    assert standalone_registry.device_by_id[mock_dev.id] is mock_dev
    assert mock_dev in standalone_registry.devices


def test_registry_duplicate_device_raises_error(
    standalone_registry: DeviceRegistry,
) -> None:
    """Test that attempting to add a duplicate device ID triggers a consistency
    exception.

    :param standalone_registry: The test device registry fixture.
    :type standalone_registry: DeviceRegistry
    :returns: None
    """
    mock_dev = MagicMock()
    mock_dev.id = cast(DeviceIdT, "01:123456")

    standalone_registry._add_device(mock_dev)

    with pytest.raises(SchemaInconsistentError, match="Device already exists"):
        standalone_registry._add_device(mock_dev)


def test_registry_get_device_triggers_callback(
    standalone_registry: DeviceRegistry,
    mock_device_factory: MagicMock,
) -> None:
    """Test that get_device invokes the injected factory callback if the entity
    does not exist.

    :param standalone_registry: The test device registry fixture.
    :type standalone_registry: DeviceRegistry
    :param mock_device_factory: The mocked entity creation callback.
    :type mock_device_factory: MagicMock
    :returns: None
    """
    dev_id = cast(DeviceIdT, "04:111111")
    mock_spawned_device = MagicMock()
    mock_spawned_device.id = dev_id
    mock_device_factory.return_value = mock_spawned_device

    # Trigger entity lookup/creation
    result_dev = standalone_registry.get_device(dev_id)

    # Verify the callback was triggered with the correct abstract L7 args
    mock_device_factory.assert_called_once()
    args, _ = mock_device_factory.call_args
    assert isinstance(args[0], Address)
    assert args[0].id == dev_id
    assert isinstance(args[2], DeviceTraits)

    # Mock object verification
    assert result_dev is mock_spawned_device


def test_registry_enforces_filter_lists() -> None:
    """Test that the registry respects the boundaries set by the injected
    DeviceFilter service.

    :returns: None
    """
    blocked_id = cast(DeviceIdT, "04:999999")

    # Build a filter that actively flags the ID as invalid or unwanted
    device_filter = DeviceFilter(
        include=[],
        exclude=[blocked_id],
        unwanted=[],
        enforce_known_list=True,
        hgi_id_provider=lambda: None,
    )

    registry = DeviceRegistry(
        device_filter=device_filter,
        config=GatewayConfig(),
        device_factory_cb=MagicMock(),
    )

    with pytest.raises(DeviceNotFoundError):
        registry.get_device(blocked_id)


def test_filter_hgi_exempt_from_unwanted() -> None:
    """The gateway's own ID must not be permanently blocked by _unwanted.

    Regression guard for issue 864: when enforce_known_list is True and
    the HGI device object has not yet been created, hgi_id_provider
    returned None, causing the gateway's own ID to be rejected and
    added to _unwanted.  The filter must exempt the HGI ID from the
    _unwanted permanent block so it can be created later.

    :returns: None
    """
    hgi_id = cast(DeviceIdT, "18:000730")

    # Simulate the race: HGI ID is already in _unwanted (e.g. from an
    # earlier rejection before the config.hgi_id was set), but the
    # provider now returns the correct ID.
    device_filter = DeviceFilter(
        include=[hgi_id],
        exclude=[],
        unwanted=[hgi_id],
        enforce_known_list=True,
        hgi_id_provider=lambda: hgi_id,
    )

    # Must NOT raise — the HGI ID is exempted from the _unwanted check
    device_filter.check_filter_lists(hgi_id)


def test_filter_hgi_id_provider_fallback() -> None:
    """hgi_id_provider should allow the HGI ID via config fallback.

    When self.hgi is None (device not yet created), the provider
    falls back to config.hgi_id.  The filter must accept the HGI ID
    even when enforce_known_list is True and the ID is not in the
    include list.

    :returns: None
    """
    hgi_id = cast(DeviceIdT, "18:000730")

    # HGI ID is not in include list, but provider returns it
    device_filter = DeviceFilter(
        include=[],
        exclude=[],
        unwanted=[],
        enforce_known_list=True,
        hgi_id_provider=lambda: hgi_id,
    )

    # Must NOT raise — the HGI ID is exempted via the provider
    device_filter.check_filter_lists(hgi_id)


@pytest.mark.asyncio
async def test_fan_promotion_race_condition() -> None:
    """Test that early PROMOTE_CLASS events correctly apply via the SSOT.

    This reproduces the race condition where a TopologyBuilder emits a
    promotion event before the packet processing pipeline has actually
    instantiated the device in memory.
    """
    # Arrange
    config = GatewayConfig(known_list={})
    filter_mock = MagicMock()
    captured_traits: list[DeviceTraits] = []

    def mock_device_factory(
        addr: Address,
        msg: Message | None,
        traits: DeviceTraits,
    ) -> Device:
        """Mock factory to track what traits were passed at creation."""
        captured_traits.append(traits)
        dev_mock = MagicMock()
        dev_mock.id = addr.id
        dev_mock.addr = addr
        dev_mock._SLUG = traits.device_class
        return cast("Device", dev_mock)

    registry = DeviceRegistry(filter_mock, config, mock_device_factory)
    fan_id = "32:111111"

    event = TopologyChangedEvent(
        action=TopologyAction.UPDATE_DEVICE_CLASS,
        device_id=fan_id,
        metadata={"device_class": "FAN"},
        causation="test_eavesdrop",
    )

    # Act 1: The TopologyBuilder fires the event early (Race Condition)
    registry.handle_topology_event(event)

    # Act 2: The packet pipeline finally requests the device
    dev = registry.get_device(fan_id)

    # Assert
    # 1. The registry must have mutated the Single Source of Truth
    assert fan_id in config.known_list
    assert config.known_list[fan_id].get("class") == "ventilator"

    # 2. The factory must have received the correct promoted traits
    assert len(captured_traits) == 1
    assert captured_traits[0].device_class == "ventilator"

    # 3. The returned device must act as the promoted class
    assert getattr(dev, "_SLUG", None) == "ventilator"


def test_filter_placeholder_exempt_from_enforce_known_list() -> None:
    """HGI_DEV_ADDR (18:000730) must bypass enforce_known_list.

    Regression guard for issue 1015: when the active gateway is a real
    HGI80, it transmits under the shared placeholder address 18:000730
    (not its own real device ID).  GatewayConfig.__post_init__ derives
    config.hgi_id from the known_list, which is the *real* ID (e.g.
    18:123456), so hgi_id_provider() returns the real ID — not the
    placeholder the HGI80 actually transmits as.

    check_filter_lists("18:000730") therefore failed both the
    enforce_known_list check (18:000730 != 18:123456 and not in
    include) and, after the first rejection, the _unwanted permanent
    block — logging a DeviceNotFoundError warning pair on every
    self-originated RQ/W.

    The placeholder must be exempt from both checks (but NOT from the
    block_list, which the protocol-level filter intentionally keeps
    enforced for HGI_DEV_ADDR).

    :returns: None
    """
    real_hgi_id = cast(DeviceIdT, "18:123456")
    placeholder_id = HGI_DEV_ADDR.id  # 18:000730

    # Simulate the HGI80 scenario: provider returns the real ID (from
    # config.hgi_id, derived from known_list by __post_init__), the
    # placeholder is NOT in the include list, enforce_known_list is True.
    device_filter = DeviceFilter(
        include=[real_hgi_id],
        exclude=[],
        unwanted=[],
        enforce_known_list=True,
        hgi_id_provider=lambda: real_hgi_id,
    )

    # Must NOT raise — the placeholder is exempt from enforce_known_list
    device_filter.check_filter_lists(placeholder_id)

    # Must NOT have been added to _unwanted (which would cause repeating
    # rejections on every subsequent packet via the faster _unwanted branch)
    assert placeholder_id not in device_filter._unwanted


def test_filter_placeholder_exempt_from_unwanted() -> None:
    """HGI_DEV_ADDR must bypass the _unwanted permanent block.

    Companion to test_filter_placeholder_exempt_from_enforce_known_list:
    even if 18:000730 somehow ends up in _unwanted (e.g. from a race
    during startup before config.hgi_id was set), the filter must not
    permanently reject it — otherwise the active HGI80 can never be
    created in the registry.

    :returns: None
    """
    placeholder_id = HGI_DEV_ADDR.id

    # placeholder already in _unwanted, provider returns a *different*
    # real HGI ID (the HGI80 scenario)
    real_hgi_id = cast(DeviceIdT, "18:123456")
    device_filter = DeviceFilter(
        include=[],
        exclude=[],
        unwanted=[placeholder_id],
        enforce_known_list=True,
        hgi_id_provider=lambda: real_hgi_id,
    )

    # Must NOT raise — the placeholder is exempt from the _unwanted check
    device_filter.check_filter_lists(placeholder_id)


def test_filter_placeholder_still_subject_to_block_list() -> None:
    """HGI_DEV_ADDR must remain subject to the block_list.

    The protocol-level filter (_is_wanted_addrs in ramses_tx) explicitly
    keeps HGI_DEV_ADDR subject to the block_list, and the device-registry
    filter must match that policy — the placeholder exemption covers
    enforce_known_list and _unwanted only, not the block_list.

    :returns: None
    """
    placeholder_id = HGI_DEV_ADDR.id
    real_hgi_id = cast(DeviceIdT, "18:123456")

    device_filter = DeviceFilter(
        include=[placeholder_id],
        exclude=[placeholder_id],
        unwanted=[],
        enforce_known_list=True,
        hgi_id_provider=lambda: real_hgi_id,
    )

    # MUST raise — the block_list check is not exempted for the placeholder
    with pytest.raises(DeviceNotFoundError, match="blocked device_id"):
        device_filter.check_filter_lists(placeholder_id)
