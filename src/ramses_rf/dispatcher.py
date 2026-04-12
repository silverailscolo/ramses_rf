#!/usr/bin/env python3
"""RAMSES RF - Decode/process a message (payload into JSON)."""

# TODO:
# - fix dispatching - what devices (some are Addr) are sent packets, esp. 1FC9s

from __future__ import annotations

import contextlib
import logging
from datetime import timedelta as td
from typing import TYPE_CHECKING, Final

from ramses_tx import ALL_DEV_ADDR, CODES_BY_DEV_SLUG, Message
from ramses_tx.ramses import (
    CODES_OF_HEAT_DOMAIN,
    CODES_OF_HEAT_DOMAIN_ONLY,
    CODES_OF_HVAC_DOMAIN_ONLY,
)

from . import exceptions as exc
from .const import (
    DEV_TYPE_MAP,
    DONT_CREATE_ENTITIES,
    DONT_UPDATE_ENTITIES,
    I_,
    RP,
    RQ,
    SZ_DEVICES,
    SZ_OFFER,
    SZ_PHASE,
    W_,
    Code,
    DevType,
)
from .device import Device, Fakeable

if TYPE_CHECKING:
    from .gateway import Gateway

#
# NOTE: All debug flags should be False for deployment to end-users
_DBG_FORCE_LOG_MESSAGES: Final[bool] = False  # useful for dev/test
_DBG_INCREASE_LOG_LEVELS: Final[bool] = (
    False  # set True for developer-friendly log spam
)

_LOGGER = logging.getLogger(__name__)


__all__ = [
    "detect_array_fragment",
    "instantiate_devices",
    "process_msg",
    "route_payload",
    "validate_addresses",
    "validate_slugs",
]


MSG_FORMAT_18 = "|| {:18s} | {:18s} | {:2s} | {:16s} | {:^4s} || {}"

_TD_SECONDS_003 = td(seconds=3)


def _log_message(gwy: Gateway, msg: Message) -> None:
    """Log msg according to src, code, log.debug setting.

    :param gwy: The gateway handling the message.
    :type gwy: Gateway
    :param msg: the Message being processed.
    :type msg: Message
    """
    if _DBG_FORCE_LOG_MESSAGES:
        _LOGGER.warning(msg)
    elif msg.src != gwy.hgi or (msg.code != Code._PUZZ and msg.verb != RQ):
        _LOGGER.info(msg)
    elif msg.src != gwy.hgi or msg.verb != RQ:
        _LOGGER.info(msg)
    elif _LOGGER.getEffectiveLevel() == logging.DEBUG:
        _LOGGER.info(msg)


def validate_addresses(gwy: Gateway, msg: Message) -> bool:
    """Validate the packet's address set for basic structural rules.

    This is Stage 1 of the processing pipeline. It evaluates the raw addressing
    metadata. If the addresses violate domain-specific rules, an exception is
    raised and caught by the pipeline executor.

    :param gwy: The gateway handling the message.
    :type gwy: Gateway
    :param msg: The message containing source/destination addresses.
    :type msg: Message
    :raises exc.PacketAddrSetInvalid: If the address pair is invalid.
    :return: True if the pipeline should proceed, False if processing
             is configured to halt before entity creation.
    :rtype: bool
    """
    # TODO: needs work: doesn't take into account device's (non-HVAC) class
    if (
        msg.src.id != msg.dst.id
        and msg.src.type == msg.dst.type
        and msg.src.type in DEV_TYPE_MAP.HEAT_DEVICES  # could still be HVAC domain
    ):
        # .I --- 18:013393 18:000730 --:------ 0001 005 00FFFF0200     # invalid
        # .I --- 01:078710 --:------ 01:144246 1F09 003 FF04B5         # invalid
        # .I --- 29:151550 29:237552 --:------ 22F3 007 00023C03040000 # valid? HVAC
        if msg.code in CODES_OF_HEAT_DOMAIN_ONLY:
            raise exc.PacketAddrSetInvalid(
                f"Invalid addr pair: {msg.src!r}/{msg.dst!r}"
            )
        elif msg.code in CODES_OF_HEAT_DOMAIN:
            _LOGGER.warning(
                f"{msg!r} < Invalid addr pair: {msg.src!r}/{msg.dst!r}, is it HVAC?"
            )
        elif msg.code not in CODES_OF_HVAC_DOMAIN_ONLY:
            _LOGGER.info(
                f"{msg!r} < Invalid addr pair: {msg.src!r}/{msg.dst!r}, is it HVAC?"
            )

    # TODO: any use in creating a device only if the payload is valid?
    return gwy.config.reduce_processing < DONT_CREATE_ENTITIES


def instantiate_devices(gwy: Gateway, msg: Message) -> bool:
    """Ensure the source and destination devices exist in the registry.

    This is Stage 2 of the processing pipeline. It attempts to discover or
    map the addresses to actual Device objects. If a required device cannot be
    found, it logs a warning and halts the pipeline.

    :param gwy: The gateway containing the device registry.
    :type gwy: Gateway
    :param msg: The message to inject discovered devices into.
    :type msg: Message
    :return: True if devices were mapped/created successfully, False otherwise.
    :rtype: bool
    """
    try:
        # FIXME: changing Address to Devices is messy: ? Protocol for same method signatures
        # prefer Devices but can continue with Addresses if required...
        msg.src = gwy.device_registry.device_by_id.get(msg.src.id, msg.src)
        msg.dst = gwy.device_registry.device_by_id.get(msg.dst.id, msg.dst)

        # Devices need to know their controller, ?and their location ('parent' domain)
        # NB: only addrs processed here, packet metadata is processed elsewhere

        # Determining bindings to a controller:
        #  - configury; As per any schema                                                   # codespell:ignore configury
        #  - discovery: If in 000C pkt, or pkt *to* device where src is a controller
        #  - eavesdrop: If pkt *from* device where dst is a controller

        # Determining location in a schema (domain/DHW/zone):
        #  - configury; As per any schema                                                   # codespell:ignore configury
        #  - discovery: If in 000C pkt - unable for 10: & 00: (TRVs)
        #  - discovery: from packet fingerprint, excl. payloads (only for 10:)
        #  - eavesdrop: from packet fingerprint, incl. payloads

        if not isinstance(msg.src, Device):  # type: ignore[unreachable]
            # may: DeviceNotFoundError, but don't suppress
            msg.src = gwy.device_registry.get_device(msg.src.id)
            if msg.dst.id == msg.src.id:
                msg.dst = msg.src
                return True

        if not gwy.config.enable_eavesdrop:
            return True

        if not isinstance(msg.dst, Device) and msg.src != gwy.hgi:  # type: ignore[unreachable]
            with contextlib.suppress(exc.DeviceNotFoundError):
                msg.dst = gwy.device_registry.get_device(msg.dst.id)

    except exc.DeviceNotFoundError as err:
        (_LOGGER.error if _DBG_INCREASE_LOG_LEVELS else _LOGGER.warning)(
            "%s < %s(%s)", msg._pkt, err.__class__.__name__, err
        )
        return False

    return True


def validate_slugs(gwy: Gateway, msg: Message) -> bool:
    """Validate the device classes against the transmitted code/verb.

    This is Stage 3 of the processing pipeline. It verifies whether the
    source is permitted to Tx this payload, and if the destination is
    permitted to Rx it, based on protocol schemas.

    :param gwy: The gateway handling the message.
    :type gwy: Gateway
    :param msg: The message containing the verb and code to validate.
    :type msg: Message
    :raises exc.PacketInvalid: If either slug cannot process the verb/code.
    :return: True if slugs are valid, False if processing limits dictate halting.
    :rtype: bool
    """
    # 1. Check Source Slug
    slug = getattr(msg.src, "_SLUG", None)
    if slug not in (None, DevType.HGI, DevType.DEV, DevType.HEA, DevType.HVC):
        # TODO: use DEV_TYPE_MAP.PROMOTABLE_SLUGS
        if slug not in CODES_BY_DEV_SLUG:
            raise exc.PacketInvalid(f"{msg!r} < Unknown src slug ({slug}), is it HVAC?")

        if msg.code not in CODES_BY_DEV_SLUG[slug]:
            raise exc.PacketInvalid(f"{msg!r} < Unexpected code for src ({slug}) to Tx")

        if msg.verb not in CODES_BY_DEV_SLUG[slug][msg.code]:
            raise exc.PacketInvalid(
                f"{msg!r} < Unexpected verb/code for src ({slug}) to Tx"
            )

    # 2. Check Destination Slug
    if (
        msg.src._SLUG != DevType.HGI  # avoid: msg.src.id != gwy.hgi.id
        and msg.verb != I_
        and msg.dst != msg.src
    ):
        # HGI80 can do what it likes
        # receiving an I_ isn't currently in the schema & so can't yet be tested
        slug = getattr(msg.dst, "_SLUG", None)
        if slug not in (None, DevType.HGI, DevType.DEV, DevType.HEA, DevType.HVC):
            if slug not in CODES_BY_DEV_SLUG:
                raise exc.PacketInvalid(
                    f"{msg!r} < Unknown dst slug ({slug}), is it HVAC?"
                )

            if f"{slug}/{msg.verb}/{msg.code}" not in (f"CTL/{RQ}/{Code._3EF1}",):
                # HACK: an exception-to-the-rule that need sorting
                if msg.code not in CODES_BY_DEV_SLUG[slug]:
                    raise exc.PacketInvalid(
                        f"{msg!r} < Unexpected code for dst ({slug}) to Rx"
                    )

                if f"{msg.verb}/{msg.code}" not in (f"{W_}/{Code._0001}",):
                    # HACK: an exception-to-the-rule that need sorting
                    if f"{slug}/{msg.verb}/{msg.code}" not in (
                        f"{DevType.BDR}/{RQ}/{Code._3EF0}",
                    ):
                        # HACK: an exception-to-the-rule that need sorting
                        if {RQ: RP, RP: RQ, W_: I_}[msg.verb] not in CODES_BY_DEV_SLUG[
                            slug
                        ][msg.code]:
                            raise exc.PacketInvalid(
                                f"{msg!r} < Unexpected verb/code for dst ({slug}) to Rx"
                            )

    return gwy.config.reduce_processing < DONT_UPDATE_ENTITIES


def route_payload(gwy: Gateway, msg: Message) -> None:
    """Determine target entities and deliver the payload to them.

    This is the final stage (Stage 4) of the pipeline. It routes messages to
    the source device (for internal state updates) and constructs a list of
    destination devices based on binding offers, eavesdropping rules, and
    faked device states.

    :param gwy: The gateway handling the message routing.
    :type gwy: Gateway
    :param msg: The fully validated message to be dispatched.
    :type msg: Message
    """
    # NOTE: here, msgs are routed only to devices: routing to other entities (i.e.
    # systems, zones, circuits) is done by those devices (e.g. UFC to UfhCircuit)

    if isinstance(msg.src, Device):  # type: ignore[unreachable]
        gwy._engine._loop.call_soon(msg.src._handle_msg, msg)  # type: ignore[unreachable]

    # TODO: only be for fully-faked (not Fakable) dst (it picks up via RF if not)

    if (
        msg.code == Code._1FC9
        and isinstance(msg.payload, dict)  # 1. Ensure it's a dict (not bytes)
        and msg.payload.get(SZ_PHASE) == SZ_OFFER  # 2. Safely check for key
    ):
        devices = [
            d for d in gwy.device_registry.devices if d != msg.src and d._is_binding
        ]

    elif msg.dst == ALL_DEV_ADDR:  # some offers use dst=63:, so after 1FC9 offer
        devices = [
            d for d in gwy.device_registry.devices if d != msg.src and d.is_faked
        ]

    elif msg.dst is not msg.src and isinstance(msg.dst, Fakeable):  # type: ignore[unreachable]
        # to eavesdrop pkts from other devices, but relevant to this device
        # dont: msg.dst._handle_msg(msg)
        devices = [msg.dst]  # type: ignore[unreachable]

    # TODO: this may not be required...
    elif hasattr(msg.src, SZ_DEVICES):  # FIXME: use isinstance()
        # elif isinstance(msg.src, Controller):
        # .I --- 22:060293 --:------ 22:060293 0008 002 000C
        # .I --- 01:054173 --:------ 01:054173 0008 002 03AA
        # needed for (e.g.) faked relays: each device decides if the pkt is useful
        devices = msg.src.devices

    else:
        devices = []

    for d in devices:  # FIXME: some may be Addresses?
        gwy._engine._loop.call_soon(d._handle_msg, msg)


async def process_msg(gwy: Gateway, msg: Message) -> None:
    """Decode the packet payload and route it through the message pipeline.

    This executor acts as a Chain of Responsibility, routing the message
    through sequential, mathematically isolated validation and dispatch stages.

    :param gwy: The gateway instance handling the routing.
    :type gwy: Gateway
    :param msg: The processed message to route.
    :type msg: Message
    """
    # All methods require msg with a valid payload, except instantiate_devices(),
    # which requires a valid payload only for 000C.
    try:
        if not validate_addresses(gwy, msg):
            _log_message(gwy, msg)
            return

        if not instantiate_devices(gwy, msg):
            return

        if not validate_slugs(gwy, msg):
            _log_message(gwy, msg)
            return

        route_payload(gwy, msg)

    except (AssertionError, exc.RamsesException, NotImplementedError) as err:
        (_LOGGER.error if _DBG_INCREASE_LOG_LEVELS else _LOGGER.warning)(
            "%s < %s(%s)", msg._pkt, err.__class__.__name__, err
        )

    except (AttributeError, LookupError, TypeError, ValueError) as err:
        if getattr(gwy.config, "enforce_strict_handling", False):
            raise
        _LOGGER.warning(
            "%s < %s(%s)", msg._pkt, err.__class__.__name__, err, exc_info=True
        )

    else:
        _log_message(gwy, msg)
        if gwy.message_store:
            gwy.message_store.add(msg)
            # why add it? enable for evohome


# TODO: this needs cleaning up (e.g. handle intervening packet)
def detect_array_fragment(this: Message, prev: Message) -> bool:  # _PayloadT
    """Return True if this pkt is the latter half of an array.

    :param this: The current message being evaluated.
    :type this: Message
    :param prev: The previously received message.
    :type prev: Message
    :return: True if the packet is part of a merged array, False otherwise.
    :rtype: bool
    """
    # This will work, even if the 2nd pkt._is_array == False as 1st == True
    # .I --- 01:158182 --:------ 01:158182 000A 048 001201F409C4011101F409C40...
    # .I --- 01:158182 --:------ 01:158182 000A 006 081001F409C4

    return bool(
        prev._has_array
        and this.code in (Code._000A, Code._22C9)  # TODO: not a complete list
        and this.code == prev.code
        and this.verb == prev.verb == I_
        and this.src == prev.src
        and this.dtm < prev.dtm + _TD_SECONDS_003
    )
