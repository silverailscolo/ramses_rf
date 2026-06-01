#!/usr/bin/env python3
"""RAMSES RF - a RAMSES-II protocol decoder & analyser.

Base for all devices.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from datetime import UTC, datetime as dt, timedelta as td
from typing import TYPE_CHECKING, Any, cast

from ramses_rf.address import Address
from ramses_rf.binding_fsm import BindingManager, Vendor
from ramses_rf.const import (
    DEV_TYPE_MAP,
    GATEWAY_MESSAGE_TIMEOUT,
    HEARTBEAT_TIMEOUT_DEFAULT,
    SZ_OEM_CODE,
    DevType,
)
from ramses_rf.entity import Entity, class_by_attr
from ramses_rf.exceptions import DeviceNotFaked, SchemaInconsistentError
from ramses_rf.schemas import SZ_ALIAS, SZ_CLASS, SZ_FAKED
from ramses_rf.topology import Child
from ramses_tx import Command, Packet, Priority, QosParams
from ramses_tx.typing import PayloadT

from ..messages import Message
from ..protocol.ramses import CODES_BY_DEV_SLUG

from ramses_rf.const import (  # noqa: F401, isort: skip, pylint: disable=unused-import
    I_,
    RP,
    RQ,
    W_,
    Code,
)

if TYPE_CHECKING:
    from ramses_rf import Gateway
    from ramses_rf.models import DeviceTraits
    from ramses_rf.system import Zone
    from ramses_tx.const import IndexT
    from ramses_tx.typing import DeviceIdT


BIND_WAITING_TIMEOUT = 300  # how long to wait, listening for an offer
BIND_REQUEST_TIMEOUT = 5  # how long to wait for an accept after sending an offer
BIND_CONFIRM_TIMEOUT = 5  # how long to wait for a confirm after sending an accept


_LOGGER = logging.getLogger(__name__)


class DeviceBase(Entity):
    """The Device base class - can also be used for unknown device types."""

    _SLUG: str = DevType.DEV
    _STATE_ATTR: str = None

    _binding_manager: BindingManager | None = None

    def __init__(
        self,
        gwy: Gateway,
        dev_addr: Address,
        *,
        traits: DeviceTraits | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(gwy, **kwargs)

        # FIXME: gwy.message_store entities must know their parent device ID
        # and their own idx
        self._z_id = dev_addr.id  # the responsible device is itself
        self._z_idx = None  # depends upon its location in the schema

        self.id: DeviceIdT = dev_addr.id

        self.addr = dev_addr
        self.type = dev_addr.type  # DEX  # TODO: remove this attr? use SLUG?

        self._scheme: Vendor | None = traits.scheme if traits else None
        self._last_msg_dtm: dt | None = None

    def __str__(self) -> str:
        if self._STATE_ATTR and hasattr(self, self._STATE_ATTR):
            state: float | None = getattr(self, self._STATE_ATTR)
            return f"{self.id} ({self._SLUG}): {state}"
        return f"{self.id} ({self._SLUG})"

    def __lt__(self, other: object) -> bool:
        if not hasattr(other, "id"):
            return NotImplemented
        return self.id < other.id  # type: ignore[no-any-return]

    @property
    def heartbeat_timeout(self) -> td:
        """Return the timeout after which the device is considered unavailable.

        :return: The timeout duration before going unavailable.
        :rtype: td
        """
        return HEARTBEAT_TIMEOUT_DEFAULT

    @property
    def is_available(self) -> bool:
        """Return True if the device is available based on its heartbeat.

        :return: Availability status based on the latest message timestamp.
        :rtype: bool
        """
        if self._last_msg_dtm is None:
            return True  # Assume available until we receive baseline telemetry

        if self._last_msg_dtm.tzinfo is not None:
            now = dt.now(UTC).astimezone(self._last_msg_dtm.tzinfo)
        else:
            now = dt.now()

        return (now - self._last_msg_dtm) <= self.heartbeat_timeout

    def _update_traits(self, traits: DeviceTraits) -> None:
        """Update a device with new schema attributes.

        :param traits: The traits to apply (e.g., alias, class, faked)
        :raises DeviceNotFaked: If the device is not fakeable but 'faked' is set.
        """

        if traits.faked:  # class & alias are done elsewhere
            if not isinstance(self, Fakeable):
                raise DeviceNotFaked(
                    f"Device is not fakeable: {self} (traits={traits})"
                )
            self._make_fake()

        self._scheme = traits.scheme

    @classmethod
    def create_from_schema(
        cls, gwy: Gateway, dev_addr: Address, *, traits: DeviceTraits | None = None
    ) -> DeviceBase:
        """Create a device (for a GWY) and set its schema attrs (aka traits).

        All devices have traits, but also controllers (CTL, UFC) have a system schema.

        The appropriate Device class should have been determined by a factory.
        Schema attrs include: class (SLUG), alias & faked.
        """

        dev = cls(gwy, dev_addr, traits=traits)
        if traits:
            dev._update_traits(traits)
        return dev

    def _setup_discovery_cmds(self) -> None:
        pass

    def _send_cmd(self, cmd: Command, **kwargs: Any) -> asyncio.Task | None:
        if (
            isinstance(self, BatteryState)
            and not self.is_faked
            and cmd.dst.id == self.id
        ):
            _LOGGER.info(f"{cmd} < Sending inadvisable for {self} (it has a battery)")

        return super()._send_cmd(cmd, **kwargs)

    def _handle_msg(self, msg: Message) -> None:
        super()._handle_msg(msg)
        self._last_msg_dtm = getattr(msg, "dtm", None)

    async def has_battery(self) -> None | bool:  # 1060
        """Return True if the device is battery powered (excludes battery-backup)."""
        if self._gwy.message_store:
            code_list = await self.entity_state._msg_dev_qry()
            return isinstance(self, BatteryState) or (
                code_list is not None and Code._1060 in code_list
            )  # TODO(eb): clean up next line Q1 2026
        msgs = await self.entity_state.get_message_log_flat()
        return isinstance(self, BatteryState) or Code._1060 in msgs

    @property
    def is_faked(self) -> bool:
        """Return True if the device is faked."""

        return bool(self._binding_manager)  # isinstance(self, Fakeable) and...

    @property
    def _is_binding(self) -> bool:
        """Return True if the (faked) device is actively binding."""

        return self._binding_manager and self._binding_manager.is_binding is True

    async def _is_present(self) -> bool:
        """Try to exclude ghost devices (as caused by corrupt packet
        addresses).
        """
        msgs = await self.entity_state.get_message_log_flat()
        return any(
            m.src == self for m in msgs.values() if not getattr(m, "_expired", False)
        )  # TODO: needs addressing

    async def schema(self) -> dict[str, Any]:
        """Return the fixed attributes of the device."""
        return {}  # SZ_CLASS: DEV_TYPE_MAP[self._SLUG]}

    async def params(self) -> dict[str, Any]:
        """Return the configurable attributes of the device."""
        return {}

    async def status(self) -> dict[str, Any]:
        """Return the state attributes of the device."""
        return {}

    async def traits(self) -> dict[str, Any]:
        """Get the traits of the device."""

        result = await self.entity_state.traits()

        known_dev = self._gwy.config.known_list.get(self.id)

        result.update(
            {
                SZ_CLASS: DEV_TYPE_MAP[self._SLUG],
                SZ_ALIAS: known_dev.get(SZ_ALIAS) if known_dev else None,
                SZ_FAKED: self.is_faked,
            }
        )

        result["_bind"] = await self.entity_state.get_value(Code._1FC9)
        return result


class BatteryState(DeviceBase):  # 1060
    BATTERY_LOW = "battery_low"  # boolean
    BATTERY_STATE = "battery_state"  # percentage (0.0-1.0)

    async def battery_low(self) -> None | bool:  # 1060
        if self.is_faked:
            return False
        return cast(
            bool | None,
            await self.entity_state.get_value(Code._1060, key=self.BATTERY_LOW),
        )

    async def battery_state(self) -> dict[str, Any] | None:  # 1060
        if self.is_faked:
            return None
        return cast(
            dict[str, Any] | None, await self.entity_state.get_value(Code._1060)
        )

    async def status(self) -> dict[str, Any]:
        base_status = await super().status()
        return {
            **base_status,
            self.BATTERY_STATE: await self.battery_state(),
        }


class DeviceInfo(DeviceBase):  # 10E0
    def _setup_discovery_cmds(self) -> None:
        super()._setup_discovery_cmds()

        if self._SLUG not in CODES_BY_DEV_SLUG or RP in CODES_BY_DEV_SLUG[
            self._SLUG
        ].get(Code._10E0, {}):
            cmd = Command.from_attrs(RQ, self.id, Code._10E0, PayloadT("00"))
            self.discovery.add_cmd(cmd, 60 * 60 * 24)

    async def device_info(self) -> dict[str, Any] | None:  # 10E0
        return cast(
            dict[str, Any] | None, await self.entity_state.get_value(Code._10E0)
        )

    async def traits(self) -> dict[str, Any]:
        """Return the traits of the device."""

        result = await super().traits()
        msgs = await self.entity_state.get_message_log_flat()

        if Code._10E0 in msgs or Code._10E0 in CODES_BY_DEV_SLUG.get(self._SLUG, []):
            result.update({"_info": await self.device_info()})

        return result


class Fakeable(DeviceBase):
    """There are two types of Faking: impersonation (of real devices) and full-faking.

    Impersonation of physical devices simply means sending packets on their behalf. This
    is straight-forward for sensors & remotes (they do not usually receive pkts).

    Faked (virtual) devices must have any packet addressed to them sent to their
    handle_msg() method by the dispatcher. Impersonated devices will simply pick up
    such packets via RF.
    """

    def __init__(
        self,
        gwy: Gateway,
        *args: Any,
        traits: DeviceTraits | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(gwy, *args, traits=traits, **kwargs)

        self._binding_manager: BindingManager | None = None

        if self.id in gwy.config.known_list and gwy.config.known_list[self.id].get(
            SZ_FAKED
        ):
            self._make_fake()

        if traits and traits.faked:
            self._make_fake()

    def _make_fake(self) -> None:
        if self._binding_manager:
            return

        self._binding_manager = BindingManager(self, self._async_send_cmd)
        if self.id not in self._gwy.config.known_list:
            self._gwy.config.known_list[self.id] = {}
        self._gwy.config.known_list[self.id][SZ_FAKED] = True  # TODO: remove this
        _LOGGER.info(f"Faking now enabled for: {self}")

    async def _async_send_cmd(
        self,
        cmd: Command,
        priority: Priority | None = None,
        qos: QosParams | None = None,
    ) -> Packet | None:
        """Wrapper to CC: any relevant Commands to the binding Context."""

        if self._binding_manager and self._binding_manager.is_binding:
            # cmd.code in (Code._1FC9, Code._10E0)
            self._binding_manager.sent_cmd(cmd)  # other codes needed for edge cases

        return await super()._async_send_cmd(cmd, priority=priority, qos=qos)

    def _handle_msg(self, msg: Message) -> None:
        """Wrapper to CC: any relevant Packets to the binding Context."""

        super()._handle_msg(msg)

        if self._binding_manager and self._binding_manager.is_binding:
            # msg.code in (Code._1FC9, Code._10E0)
            self._binding_manager.rcvd_msg(
                msg
            )  # maybe other codes needed for edge cases

    async def _wait_for_binding_request(
        self,
        accept_codes: Iterable[Code],
        /,
        *,
        idx: IndexT = "00",
        require_ratify: bool = False,
    ) -> tuple[Packet, Packet, Packet, Packet | None]:
        """Listen for a binding and return the Offer packets.

        :param accept_codes: The codes allowed for this binding
        :type accept_codes: Iterable[Code]
        :param idx: The index to bind to, defaults to "00"
        :type idx: IndexT
        :param require_ratify: Whether a ratification step is required, defaults to False
        :type require_ratify: bool
        :return: A tuple of the four binding transaction packets
        :rtype: tuple[Packet, Packet, Packet, Packet | None]
        """

        if not self._binding_manager:
            raise DeviceNotFaked(f"{self}: Faking not enabled")

        msgs = await self._binding_manager.wait_for_binding_request(
            accept_codes, idx=idx, require_ratify=require_ratify
        )
        return msgs

    async def wait_for_binding_request(
        self,
        accept_codes: Iterable[Code],
        /,
        *,
        idx: IndexT = "00",
        require_ratify: bool = False,
    ) -> tuple[Packet, Packet, Packet, Packet | None]:
        raise NotImplementedError

    async def _initiate_binding_process(
        self,
        offer_codes: Code | Iterable[Code],
        /,
        *,
        confirm_code: Code | None = None,
        ratify_cmd: Command | None = None,
    ) -> tuple[Packet, Packet, Packet, Packet | None]:
        """Start a binding and return the Accept, or raise an exception."""
        # confirm_code can be FFFF.

        if not self._binding_manager:
            raise DeviceNotFaked(f"{self}: Faking not enabled")

        if isinstance(offer_codes, str):
            codes: tuple[Code, ...] = (offer_codes,)
        else:
            codes = tuple(offer_codes)

        msgs = await self._binding_manager.initiate_binding_process(
            codes, confirm_code=confirm_code, ratify_cmd=ratify_cmd
        )
        return msgs

    async def initiate_binding_process(self) -> Packet:
        raise NotImplementedError

    async def oem_code(self) -> str | None:
        """Return the OEM code (a 2-char ascii str) for this device, if there is one."""
        traits = await self.traits()
        if not traits.get(SZ_OEM_CODE):
            return cast(
                str | None,
                await self.entity_state.get_value(Code._10E0, key=SZ_OEM_CODE),
            )
        return cast(str | None, traits.get(SZ_OEM_CODE))


class Device(Child, DeviceBase):
    """The base class for all devices."""

    def __init__(
        self,
        gwy: Gateway,
        dev_addr: Address,
        *,
        traits: DeviceTraits | None = None,
        **kwargs: Any,
    ) -> None:
        _LOGGER.debug("Creating a Device: %s (%s)", dev_addr.id, self.__class__)
        super().__init__(gwy, dev_addr, traits=traits, **kwargs)

        gwy.device_registry._add_device(self)


class HgiGateway(Device):  # HGI (18:)
    """The HGI80 base class."""

    _SLUG: str = DevType.HGI

    def __init__(
        self, *args: Any, traits: DeviceTraits | None = None, **kwargs: Any
    ) -> None:
        super().__init__(*args, traits=traits, **kwargs)

        self.ctl = None  # FIXME: a mess
        self._child_id = "gw"  # TODO
        self.tcs = None

    @property
    def message_timeout(self) -> td:
        """Return the dynamic timeout threshold for the gateway."""
        # Safely extract the custom timeout from the GatewayConfig
        custom_timeout = getattr(self._gwy.config, "gateway_timeout", None)

        if custom_timeout is not None:
            return td(minutes=int(custom_timeout))

        return GATEWAY_MESSAGE_TIMEOUT

    async def is_active(self) -> bool:
        """Return True if the gateway has received messages recently."""
        msg: Message | None = getattr(self._gwy._engine, "_this_msg", None)

        if not msg or not hasattr(msg, "dtm"):
            return False

        dtm: dt = msg.dtm
        now = dt.now(UTC).astimezone(dtm.tzinfo) if dtm.tzinfo is not None else dt.now()

        # Compare against our new dynamic property
        return bool((now - dtm) < self.message_timeout)


class DeviceHeat(Device):  # Heat domain: Honeywell CH/DHW or compatible
    """The base class for the heat domain (Honeywell CH/DHW-compatible devices).

    Includes UFH and heatpumps (which can also cool).
    """

    _SLUG: str = DevType.HEA  # shouldn't be any of these instantiated

    def __init__(
        self,
        gwy: Gateway,
        dev_addr: Address,
        *,
        traits: DeviceTraits | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(gwy, dev_addr, traits=traits, **kwargs)

        self.ctl = None
        self.tcs = None
        self._child_id = None  # domain_id, or zone_idx

        self._iz_controller: None | bool | Message = None

    def _make_tcs_controller(
        self, *, msg: Message | None = None, **schema: Any
    ) -> None:  # CH/DHW
        """Attach a TCS (create/update as required) after passing it any msg."""

        if self.type not in DEV_TYPE_MAP.CONTROLLERS:  # potentially can be controllers
            raise SchemaInconsistentError(
                f"Invalid device type to be a controller: {self}"
            )

        self._iz_controller = self._iz_controller or msg or True

    @property
    def _is_controller(self) -> None | bool:
        if self._iz_controller is not None:
            return bool(self._iz_controller)  # True, False, or msg

        if self.ctl is not None:  # TODO: messy
            return self.ctl is self

        return False

    @property
    def zone(self) -> Zone | None:
        """Return the device's parent zone, if known."""

        return self._parent


class DeviceHvac(Device):  # HVAC domain: ventilation, PIV, MV/HR
    """The Device base class for the HVAC domain (ventilation, PIV, MV/HR)."""

    _SLUG: str = DevType.HVC  # these may be instantiated, and promoted later on

    def __init__(
        self,
        gwy: Gateway,
        dev_addr: Address,
        *,
        traits: DeviceTraits | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(gwy, dev_addr, traits=traits, **kwargs)

        self._child_id = "hv"  # TODO: domain_id/deprecate


# e.g. {"HGI": HgiGateway}
BASE_CLASS_BY_SLUG: dict[str, type[Device]] = class_by_attr(__name__, "_SLUG")
