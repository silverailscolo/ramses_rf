#!/usr/bin/env python3
"""RAMSES RF - State Storage and Database Query Component.

This module provides the EntityState component, which manages database
interactions and state querying for an entity, replacing the legacy
_MessageDB inheritance model.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime as dt
from typing import TYPE_CHECKING, Any, cast

from ramses_tx import Message

from ramses_tx.const import (  # noqa: F401, isort: skip, pylint: disable=unused-import
    I_,
    RP,
    RQ,
    Code,
    VerbT,
)
from ramses_tx.address import ALL_DEVICE_ID
from ramses_tx.ramses import CODES_SCHEMA

from . import exceptions as exc
from .const import SZ_DOMAIN_ID, SZ_NAME, SZ_ZONE_IDX

if TYPE_CHECKING:
    from ramses_tx.typing import HeaderT

    from .interfaces import DeviceInterface, GatewayInterface
    from .message_store import MessageStore

_LOGGER = logging.getLogger(__name__)

# Constants for slicing the device ID
_ID_SLICE = 9


class EntityState:
    """Manages database interactions and state queries for an entity.

    This class acts as a stateless facade. It delegates all heavy lifting
    and data storage to the Gateway's central MessageStore RAM cache.
    """

    def __init__(self, entity: DeviceInterface, gwy: GatewayInterface) -> None:
        """Initialize the EntityState."""
        self._entity = entity
        self._gwy = gwy

    def _is_relevant_msg(self, msg: Message) -> bool:
        """Check if a central MessageStore packet is relevant to this entity."""
        return bool(
            msg.src.id == self._entity.id[:_ID_SLICE]
            or (msg.dst.id == self._entity.id[:_ID_SLICE] and msg.verb != RQ)
            or (msg.dst.id == ALL_DEVICE_ID and msg.code == Code._1FC9)
        )

    async def get_all_messages(self) -> list[Message]:
        """Return a flattened list of all messages logged on this device."""
        msgz_dict = await self._get_state_cache_nested()
        return [
            msg
            for code in msgz_dict.values()
            for ctx in code.values()
            for msg in ctx.values()
        ]

    _msg_list = get_all_messages

    def _add_record(
        self,
        dev_id: str,
        code: Code | None = None,
        verb: str = " I",
        payload: str = "00",
    ) -> None:
        """Add a (dummy) record to the central SQLite MessageIndex."""
        if self._gwy.message_store:
            self._gwy.message_store.add_record(
                dev_id, code=str(code), verb=verb, payload=payload
            )

    async def _delete_msg(self, msg: Message) -> None:
        """Remove the msg from the central state databases."""
        if self._gwy.message_store:
            await cast("MessageStore", self._gwy.message_store).rem(msg)

    async def _get_msg_by_hdr(self, hdr: HeaderT) -> Message | None:
        """Return a msg, if any, that matches a given header."""
        if self._gwy.message_store:
            msgs = await self._gwy.message_store.get(hdr=hdr)
            if msgs:
                if msgs[0]._pkt._hdr != hdr:
                    raise exc.DatabaseQueryError(
                        f"Header mismatch: {msgs[0]._pkt._hdr} != {hdr}"
                    )
                return cast("Message", msgs[0])
            return None

        code_str, verb_str, _, *args = hdr.split("|")
        code = Code(code_str)
        verb = VerbT(verb_str)
        msgz_dict = await self._get_state_cache_nested()

        try:
            if args and (ctx := args[0]):
                msg = msgz_dict[code][verb][ctx]
            elif False in msgz_dict[code][verb]:
                msg = msgz_dict[code][verb][False]
            elif None in msgz_dict[code][verb]:
                msg = msgz_dict[code][verb][None]
            else:
                return None
        except KeyError:
            return None

        if msg._pkt._hdr != hdr:
            raise exc.DatabaseQueryError(f"Header mismatch: {msg._pkt._hdr} != {hdr}")
        return msg

    async def get_flag(self, code: Code, key: str, idx: int) -> bool | None:
        """Get the boolean value of a specific flag within a message payload."""
        if flags := await self.get_value(code, key=key):
            return bool(flags[idx])
        return None

    _msg_flag = get_flag

    async def get_value(
        self, code: Code | tuple[Code, ...] | Message, *args: Any, **kwargs: Any
    ) -> Any:
        """Get the value for a Code from the database or from a Message."""
        if isinstance(code, (str, tuple)):
            return await self._msg_value_code(code, *args, **kwargs)

        assert isinstance(code, Message), f"Invalid format: get_value({code})"
        return self._msg_value_msg(code, *args, **kwargs)

    _msg_value = get_value

    async def _msg_value_code(
        self,
        code: Code | tuple[Code, ...],
        verb: VerbT | None = None,
        key: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Query the index for the most recent key: value pairs."""
        assert not isinstance(code, tuple) or verb is None, (
            f"Unsupported: using a tuple ({code}) with a verb ({verb})"
        )

        if verb:
            if verb == VerbT("RQ"):
                assert not isinstance(code, tuple), (
                    f"Unsupported: using a keyword ({key}) with verb RQ"
                )
                key = None
            try:
                cd = await self.find_latest_code(code, key, **kwargs, verb=verb)
                msg = (await self._get_message_log_flat()).get(cd) if cd else None
            except KeyError:
                msg = None
        elif isinstance(code, tuple):
            msgs_dict = await self._get_message_log_flat()
            msgs_list = [m for m in msgs_dict.values() if m.code in code]
            msg = max(msgs_list) if msgs_list else None
        else:
            msgs_dict = await self._get_message_log_flat()
            msg = msgs_dict.get(code)

        return self._msg_value_msg(msg, key=key, **kwargs)

    def _msg_value_msg(
        self,
        msg: Message | None,
        key: str | None = "*",
        zone_idx: str | None = None,
        domain_id: str | None = None,
    ) -> Any:
        """Get all or a specific key with its values from a Message."""
        if msg is None:
            return None
        elif msg._expired:
            loop = getattr(self._gwy, "_loop", asyncio.get_running_loop())
            loop.create_task(self._delete_msg(msg))

        if msg.code == Code._1FC9:
            return [x[1] for x in msg.payload]

        idx: str | None = None
        val: str | None = None

        if domain_id:
            idx, val = SZ_DOMAIN_ID, domain_id
        elif zone_idx:
            idx, val = SZ_ZONE_IDX, zone_idx

        if isinstance(msg.payload, dict):
            msg_dict = msg.payload
            if idx and idx != SZ_DOMAIN_ID and msg_dict.get(idx) != val:
                return None
        elif idx:
            msg_dict = {
                k: v for d in msg.payload for k, v in d.items() if d.get(idx) == val
            }
            if not msg_dict:
                return None
        else:
            if not msg.payload:
                return None
            if isinstance(msg.payload, list) and (key == "*" or not key):
                return msg.payload
            msg_dict = msg.payload[0]

        if key == "*" or not key:
            return {
                k: v
                for k, v in msg_dict.items()
                if k not in ("dhw_idx", SZ_DOMAIN_ID, SZ_ZONE_IDX) and k[:1] != "_"
            }
        return msg_dict.get(key)

    async def _msg_dev_qry(self) -> list[Code] | None:
        """Retrieve a list of Code keys involving this device."""
        res: set[Code] = set()
        entity_id = self._entity.id
        is_dhw = entity_id[_ID_SLICE:] == "_HW"
        is_zone = len(entity_id) > 9 and not is_dhw
        zone_idx = entity_id[_ID_SLICE + 1 :] if is_zone else None

        nested_cache = await self._get_state_cache_nested()

        for code, verbs in nested_cache.items():
            for verb, ctxs in verbs.items():
                if verb not in (I_, RP):
                    continue
                for ctx, msg in ctxs.items():
                    if is_dhw:
                        in_dict = isinstance(msg.payload, dict)
                        in_list = isinstance(msg.payload, list)
                        if (
                            ctx in ("FC", "FA", "F9", "FA")
                            or (in_dict and "dhw_idx" in msg.payload)
                            or (
                                in_list
                                and any(
                                    isinstance(d, dict) and "dhw_idx" in d
                                    for d in msg.payload
                                )
                            )
                        ):
                            res.add(code)
                    elif is_zone:
                        in_dict = isinstance(msg.payload, dict)
                        in_list = isinstance(msg.payload, list)
                        if (
                            ctx == zone_idx
                            or (
                                in_dict and str(msg.payload.get("zone_idx")) == zone_idx
                            )
                            or (
                                in_list
                                and any(
                                    isinstance(d, dict)
                                    and str(d.get("zone_idx")) == zone_idx
                                    for d in msg.payload
                                )
                            )
                        ):
                            res.add(code)
                    else:
                        res.add(code)
        return list(res)

    async def find_latest_code(
        self,
        code: Code | tuple[Code, ...] | None = None,
        key: str | None = None,
        **kwargs: Any,
    ) -> Code | None:
        """Retrieve the most current Code involving this device."""
        latest: dt = dt.min
        res: Code | None = None

        entity_id = self._entity.id
        is_dhw = entity_id[_ID_SLICE:] == "_HW"
        is_zone = len(entity_id) > 9 and not is_dhw
        zone_idx = kwargs.get(
            "zone_idx", entity_id[_ID_SLICE + 1 :] if is_zone else None
        )
        dhw_idx = kwargs.get("dhw_idx")

        allowed_verbs = (
            (kwargs.get("verb"),)
            if kwargs.get("verb") in (" I", "RP")
            else (" I", "RP")
        )

        nested_cache = await self._get_state_cache_nested()

        for cd, verbs in nested_cache.items():
            if code is not None:
                if isinstance(code, tuple) and cd not in code:
                    continue
                elif not isinstance(code, tuple) and cd != code:
                    continue

            for verb, ctxs in verbs.items():
                if verb not in allowed_verbs:
                    continue

                for ctx, msg in ctxs.items():
                    if zone_idx is not None:
                        in_dict = isinstance(msg.payload, dict)
                        in_list = isinstance(msg.payload, list)
                        if not (
                            str(ctx) == str(zone_idx)
                            or (
                                in_dict
                                and str(msg.payload.get("zone_idx")) == str(zone_idx)
                            )
                            or (
                                in_list
                                and any(
                                    isinstance(d, dict)
                                    and str(d.get("zone_idx")) == str(zone_idx)
                                    for d in msg.payload
                                )
                            )
                        ):
                            continue

                    if dhw_idx is not None:
                        in_dict = isinstance(msg.payload, dict)
                        in_list = isinstance(msg.payload, list)
                        if not (
                            str(ctx) == str(dhw_idx)
                            or ctx in ("FC", "FA", "F9", "FA")
                            or (in_dict and "dhw_idx" in msg.payload)
                            or (
                                in_list
                                and any(
                                    isinstance(d, dict) and "dhw_idx" in d
                                    for d in msg.payload
                                )
                            )
                        ):
                            continue

                    if key is not None:
                        if isinstance(msg.payload, dict):
                            if key not in msg.payload:
                                continue
                        elif isinstance(msg.payload, list):
                            if not any(
                                isinstance(d, dict) and key in d for d in msg.payload
                            ):
                                continue
                        else:
                            continue

                    if msg.dtm > latest:
                        latest = msg.dtm
                        res = cd
        return res

    _msg_qry_by_code_key = find_latest_code

    async def _msg_qry(self, sql: str) -> list[dict[str, Any]]:
        """Custom query for an entity's stored payloads."""
        _LOGGER.warning(
            "Legacy _msg_qry (SQL) called. Returning empty in CQRS architecture."
        )
        return []

    @property
    def _msgs_(self) -> dict[Code, Message]:
        """Legacy compatibility property for synchronous access."""
        _msg_dict: dict[Code, Message] = {}

        # Build from _msgz_ to guarantee strict zone_idx isolation
        for code, verbs in self._msgz_.items():
            for verb, ctxs in verbs.items():
                if verb not in (I_, RP):
                    continue
                for _, msg in ctxs.items():
                    if code not in _msg_dict or msg.dtm > _msg_dict[code].dtm:
                        _msg_dict[code] = msg

        return _msg_dict

    async def _msgs(self) -> dict[Code, Message]:
        """Dynamically build a flat dict of all I/RP messages logged for this entity."""
        return await self._get_message_log_flat()

    @property
    def _msgz_(self) -> dict[Code, dict[VerbT, dict[bool | str | None, Message]]]:
        """Legacy compatibility property for synchronous access to nested states."""
        msgs_1: Any = defaultdict(lambda: defaultdict(dict))

        if self._gwy.message_store is None:
            return msgs_1

        entity_id = self._entity.id
        is_dhw = entity_id[_ID_SLICE:] == "_HW"
        is_zone = len(entity_id) > 9 and not is_dhw
        zone_idx = entity_id[_ID_SLICE + 1 :] if is_zone else None

        for msg in self._gwy.message_store.log_by_dtm:
            if not self._is_relevant_msg(msg):
                continue

            code = msg.code
            verb = msg.verb
            ctx = msg._pkt._ctx

            if is_dhw:
                in_dict = isinstance(msg.payload, dict)
                in_list = isinstance(msg.payload, list)
                if (
                    ctx in ("FC", "FA", "F9", "FA")
                    or (in_dict and "dhw_idx" in msg.payload)
                    or (
                        in_list
                        and any(
                            isinstance(d, dict) and "dhw_idx" in d for d in msg.payload
                        )
                    )
                ):
                    msgs_1[code][verb][ctx] = msg
            elif is_zone:
                in_dict = isinstance(msg.payload, dict)
                in_list = isinstance(msg.payload, list)
                if (
                    ctx == zone_idx
                    or (in_dict and str(msg.payload.get("zone_idx")) == zone_idx)
                    or (
                        in_list
                        and any(
                            isinstance(d, dict) and str(d.get("zone_idx")) == zone_idx
                            for d in msg.payload
                        )
                    )
                ):
                    msgs_1[code][verb][ctx] = msg
            else:
                msgs_1[code][verb][ctx] = msg

        return msgs_1

    async def _msgz(self) -> dict[Code, dict[VerbT, dict[bool | str | None, Message]]]:
        """Dynamically build a nested dict of all I/RP messages for this entity."""
        return await self._get_state_cache_nested()

    async def _get_message_log_flat(self) -> dict[Code, Message]:
        """Dynamically build a flat dict of all I/RP messages logged for this entity."""
        return self._msgs_

    async def _get_state_cache_nested(
        self,
    ) -> dict[Code, dict[VerbT, dict[bool | str | None, Message]]]:
        """Dynamically build a nested dict of all I/RP messages for this entity."""
        return self._msgz_

    def _handle_msg(self, msg: Message) -> None:
        """Deprecated: The proxy no longer caches its own packets."""
        pass

    async def traits(self) -> dict[str, Any]:
        """Get the codes seen by the entity."""
        msgs_dict = await self._get_message_log_flat()
        codes = {
            code: (CODES_SCHEMA[code][SZ_NAME] if code in CODES_SCHEMA else None)
            for code in sorted(msgs_dict)
            if msgs_dict[code].src.id == self._entity.id[:9]
        }
        return {"_sent": list(codes.keys())}
