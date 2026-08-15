#!/usr/bin/env python3
"""RAMSES RF - Decode/process a message (payload into JSON)."""

from __future__ import annotations

# TODO:
# - fix dispatching - what devices (some are Addr) are sent packets, esp. 1FC9s
import logging
from datetime import timedelta as td
from typing import TYPE_CHECKING, Final

from . import exceptions as exc
from .const import I_, RQ, Code
from .messages import Message
from .state_projector import (
    _get_dhw_zone_from_msg,
    _resolve_logical_targets,
    _route_2411_to_fan,
    _update_demand_state,
    _update_dhw_state,
    _update_faultlog_state,
    _update_hvac_state,
    _update_schedule_state,
    _update_system_state,
    _update_temperature_state,
    process_state_updates,
)
from .validators import instantiate_devices, validate_addresses, validate_slugs

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
    "_get_dhw_zone_from_msg",
    "_resolve_logical_targets",
    "_route_2411_to_fan",
    "_update_demand_state",
    "_update_dhw_state",
    "_update_faultlog_state",
    "_update_hvac_state",
    "_update_schedule_state",
    "_update_system_state",
    "_update_temperature_state",
    "detect_array_fragment",
    "instantiate_devices",
    "process_msg",
    "validate_addresses",
    "validate_slugs",
]


MSG_FORMAT_18 = "|| {:18s} | {:18s} | {:2s} | {:16s} | {:^4s} || {}"

_TD_SECONDS_003 = td(seconds=3)


def _log_message(gateway: Gateway, msg: Message) -> None:
    """Log msg according to src, code, log.debug setting.

    :param gateway: The gateway handling the message.
    :type gateway: Gateway
    :param msg: the Message being processed.
    :type msg: Message
    """
    if _DBG_FORCE_LOG_MESSAGES:
        _LOGGER.warning(msg)
    elif msg.src != gateway.hgi or (msg.code != Code._PUZZ and msg.verb != RQ):
        _LOGGER.info(msg)
    elif msg.src != gateway.hgi or msg.verb != RQ:
        _LOGGER.info(msg)
    elif _LOGGER.getEffectiveLevel() == logging.DEBUG:
        _LOGGER.info(msg)


async def _cqrs_ingestion_engine(gateway: Gateway, msg: Message) -> None:
    """Parallel ingestion engine to populate immutable CQRS read-models."""
    await process_state_updates(gateway, msg)


async def process_msg(gateway: Gateway, msg: Message) -> None:
    """Decode the packet payload and route it through the message pipeline.

    This executor acts as a Chain of Responsibility, routing the message
    through sequential, mathematically isolated validation and dispatch stages.

    :param gateway: The gateway instance handling the routing.
    :type gateway: Gateway
    :param msg: The processed message to route.
    :type msg: Message
    """
    # All methods require msg with a valid payload, except instantiate_devices(),
    # which requires a valid payload only for 000C.
    try:
        if cm := getattr(gateway, "conversation_manager", None):
            cm.process_msg(msg)

        if not validate_addresses(gateway, msg):
            _log_message(gateway, msg)
            return

        if not instantiate_devices(gateway, msg):
            return

        if not validate_slugs(gateway, msg):
            _log_message(gateway, msg)
            return

        await _cqrs_ingestion_engine(gateway, msg)

    except (AssertionError, exc.RamsesException, NotImplementedError) as err:
        (_LOGGER.error if _DBG_INCREASE_LOG_LEVELS else _LOGGER.warning)(
            "%s < %s(%s)", msg, err.__class__.__name__, err
        )

    except (AttributeError, LookupError, TypeError, ValueError) as err:
        if getattr(gateway.config, "enforce_strict_handling", False):
            raise
        _LOGGER.warning(
            "%s < %s(%s)", msg, err.__class__.__name__, err, exc_info=True
        )

    else:
        _log_message(gateway, msg)
        if gateway.message_store:
            gateway.message_store.add(msg)
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
