"""RAMSES RF - Device Registry."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from ramses_rf.address import Address, is_valid_dev_id
from ramses_rf.config import GatewayConfig
from ramses_rf.const import SZ_DEVICES
from ramses_rf.device import DeviceHeat, DeviceHvac, Fakeable, device_factory
from ramses_rf.exceptions import (
    DeviceNotFaked,
    DeviceNotFoundError,
    SchemaInconsistentError,
)
from ramses_rf.interfaces import DeviceFilterInterface, GatewayInterface
from ramses_rf.models import DeviceTraits
from ramses_rf.schemas import SCH_TRAITS, SZ_ALIAS, SZ_CLASS, SZ_FAKED
from ramses_rf.typing import DeviceIdT, DeviceListT, DeviceTraitsT

if TYPE_CHECKING:
    from ramses_rf.device import Device
    from ramses_rf.gateway import Gateway
    from ramses_rf.messages import Message
    from ramses_rf.system import Evohome
    from ramses_rf.topology import Parent

_LOGGER = logging.getLogger(__name__)


class DeviceRegistry:
    """Service to manage the registry of known devices."""

    def __init__(
        self,
        gateway: GatewayInterface,
        device_filter: DeviceFilterInterface,
        config: GatewayConfig,
    ) -> None:
        """Initialize the DeviceRegistry.

        :param gateway: The Gateway instance for retrieving configuration.
        :type gateway: GatewayInterface
        :param device_filter: The injected filter for validating devices.
        :type device_filter: DeviceFilterInterface
        :param config: The gateway configuration object.
        :type config: GatewayConfig
        """
        self._gateway = gateway
        self._device_filter = device_filter
        self._config = config
        self.devices: list[Device] = []
        self.device_by_id: dict[DeviceIdT, Device] = {}

    def _add_device(self, dev: Device) -> None:
        """Add a device to the registry.

        :param dev: The device instance to add.
        :type dev: Device
        :raises SchemaInconsistentError: If the device already exists in
            the registry.
        """
        if dev.id in self.device_by_id:
            raise SchemaInconsistentError(f"Device already exists: {dev.id}")

        self.devices.append(dev)
        self.device_by_id[dev.id] = dev

    def get_device(
        self,
        device_id: DeviceIdT,
        *,
        msg: Message | None = None,
        parent: Parent | None = None,
        child_id: str | None = None,
        is_sensor: bool | None = None,
    ) -> Device:
        """Return a device, creating it if it does not already exist.

        :param device_id: The unique identifier for the device.
        :type device_id: DeviceIdT
        :param msg: An optional initial message for the device to process.
        :type msg: Message | None
        :param parent: The parent entity of this device, if any.
        :type parent: Parent | None
        :param child_id: Specific ID of the child component if applicable.
        :type child_id: str | None
        :param is_sensor: Indicates if this device is treated as a sensor.
        :type is_sensor: bool | None
        :returns: The existing or newly created device instance.
        :rtype: Device
        :raises DeviceNotFoundError: If device ID is blocked or unknown.
        """
        try:
            self._device_filter.check_filter_lists(device_id)
        except DeviceNotFoundError:
            # have to allow for GWY not being in known_list...
            if device_id != self._config.hgi_id:
                raise

        dev = self.device_by_id.get(device_id)

        if not dev:
            # voluptuous bug workaround:
            # https://github.com/alecthomas/voluptuous/pull/524
            _traits_raw: dict[str, Any] = dict(
                self._config.known_list.get(device_id, {})
            )
            _traits_raw.pop("commands", None)

            traits_dict: dict[str, Any] = SCH_TRAITS(
                self._config.known_list.get(device_id, {})
            )
            traits = DeviceTraits.from_dict(traits_dict)

            dev = device_factory(
                cast("Gateway", self._gateway),
                Address(device_id),
                msg=msg,
                traits=traits,
            )

            if traits.faked:
                if isinstance(dev, Fakeable):
                    dev._make_fake()
                else:
                    _LOGGER.warning(f"The device is not fakeable: {dev}")

        if parent or child_id:
            dev.set_parent(parent, child_id=child_id, is_sensor=is_sensor)

        return dev

    async def fake_device(
        self,
        device_id: DeviceIdT,
        create_device: bool = False,
    ) -> Device | Fakeable:
        """Create a faked device.

        :param device_id: The unique identifier for the device to fake.
        :type device_id: DeviceIdT
        :param create_device: Allow creation if the device does not exist.
        :type create_device: bool
        :returns: The instantiated faked device.
        :rtype: Device | Fakeable
        :raises SchemaInconsistentError: If the provided device ID is invalid.
        :raises DeviceNotFoundError: If the device isn't found or allowed.
        :raises DeviceNotFaked: If the device cannot be faked.
        """
        if not is_valid_dev_id(device_id):
            raise SchemaInconsistentError(f"The device id is not valid: {device_id}")

        known_list = await self.known_list()

        if not create_device and device_id not in self.device_by_id:
            raise DeviceNotFoundError(f"The device id does not exist: {device_id}")
        elif create_device and device_id not in known_list:
            raise DeviceNotFoundError(
                f"The device id is not in the known_list: {device_id}"
            )

        if (dev := self.get_device(device_id)) and isinstance(dev, Fakeable):
            dev._make_fake()
            return cast("Device | Fakeable", dev)

        raise DeviceNotFaked(f"The device is not fakeable: {device_id}")

    async def known_list(self) -> DeviceListT:
        """Return the working known_list (a superset of the provided
        known_list).

        :returns: A dictionary mapping device IDs to their traits.
        :rtype: DeviceListT
        """
        result: dict[str, Any] = {k: v for k, v in self._config.known_list.items()}
        for d in self.devices:
            if (
                not self._config.engine.enforce_known_list
                or d.id in self._config.mac_filter_list
            ):
                traits = await d.traits()
                result[d.id] = cast(
                    DeviceTraitsT,
                    {k: traits.get(k) for k in (SZ_CLASS, SZ_ALIAS, SZ_FAKED)},
                )
        return cast(DeviceListT, result)

    async def params(self) -> dict[str, Any]:
        """Return the parameters for all devices.

        :returns: A dictionary containing parameters for all devices.
        :rtype: dict[str, Any]
        """
        return {SZ_DEVICES: {d.id: await d.params() for d in sorted(self.devices)}}

    async def status(self) -> dict[str, Any]:
        """Return the status for all devices.

        :returns: A dictionary containing device statuses.
        :rtype: dict[str, Any]
        """
        return {SZ_DEVICES: {d.id: await d.status() for d in sorted(self.devices)}}

    @property
    def system_by_id(self) -> dict[DeviceIdT, Evohome]:
        """Return a mapping of device IDs to their associated Evohome systems.

        :returns: Dictionary mapping device ID to Evohome system.
        :rtype: dict[DeviceIdT, Evohome]
        """
        return {
            d.id: d.tcs
            for d in self.devices
            if hasattr(d, "tcs") and getattr(d.tcs, "id", None) == d.id
        }

    @property
    def systems(self) -> list[Evohome]:
        """Return a list of all identified Evohome systems.

        :returns: A list of Evohome instances.
        :rtype: list[Evohome]
        """
        return list(self.system_by_id.values())

    async def get_heat_orphans(self) -> list[DeviceIdT]:
        """Return a list of IDs for orphaned heat devices.

        :returns: A list of device IDs.
        :rtype: list[DeviceIdT]
        """
        orphans = []
        for d in self.devices:
            if (
                not getattr(d, "tcs", None)
                and isinstance(d, DeviceHeat)
                and await d._is_present()
            ):
                orphans.append(d.id)
        return sorted(orphans)

    async def get_hvac_orphans(self) -> list[DeviceIdT]:
        """Return a list of IDs for orphaned HVAC devices.

        :returns: A list of device IDs.
        :rtype: list[DeviceIdT]
        """
        orphans = []
        for d in self.devices:
            if isinstance(d, DeviceHvac) and await d._is_present():
                orphans.append(d.id)
        return sorted(orphans)
