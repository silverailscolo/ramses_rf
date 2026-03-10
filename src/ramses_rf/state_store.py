#!/usr/bin/env python3
"""RAMSES RF - State Storage and Database Query Component.

This module provides the StateStore component, which manages database
interactions and state querying for an entity, replacing the legacy
_MessageDB inheritance model.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
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

from ramses_tx.ramses import CODES_SCHEMA

from . import exceptions as exc
from .const import SZ_DOMAIN_ID, SZ_NAME, SZ_ZONE_IDX

if TYPE_CHECKING:
    from ramses_tx.typing import HeaderT

    from .database import MessageIndex
    from .interfaces import DeviceInterface, GatewayInterface

_LOGGER = logging.getLogger(__name__)

# Constants for slicing the device ID
_ID_SLICE = 9


class StateStore:
    """Manages database interactions and state queries for an entity.

    This class is intended to be composed into Entity classes rather than
    inherited. It delegates heavy lifting to the Gateway's MessageIndex.
    """

    def __init__(self, entity: DeviceInterface, gwy: GatewayInterface) -> None:
        """Initialize the StateStore.

        :param entity: The device or entity this store represents.
        :type entity: DeviceInterface
        :param gwy: The gateway orchestrator providing database access.
        :type gwy: GatewayInterface
        """
        self._entity = entity
        self._gwy = gwy

        # Legacy dictionaries (Deprecated since 0.52.1)
        self._msgs_: dict[Code, Message] = {}
        if not self._gwy.msg_db:
            self._msgz_: dict[Code, dict[VerbT, dict[bool | str | None, Message]]] = {}

    async def _msg_list(self) -> list[Message]:
        """Return a flattened list of all messages logged on this device.

        :returns: A list of messages.
        :rtype: list[Message]
        """
        if self._gwy.msg_db:
            msg_list_qry: list[Message] = []
            code_list = await self._msg_dev_qry()
            if code_list:
                msgs_dict = await self._msgs()
                for code in code_list:
                    if code in msgs_dict:
                        msg_list_qry.append(msgs_dict[code])
                    else:
                        _LOGGER.debug(
                            "_msg_list could not fetch self._msgs[%s] for %s",
                            code,
                            self._entity.id,
                        )
            return msg_list_qry

        msgz_dict = await self._msgz()
        return [
            msg
            for code in msgz_dict.values()
            for ctx in code.values()
            for msg in ctx.values()
        ]

    def _add_record(
        self,
        dev_id: str,
        code: Code | None = None,
        verb: str = " I",
        payload: str = "00",
    ) -> None:
        """Add a (dummy) record to the central SQLite MessageIndex.

        :param dev_id: The device ID to record against.
        :type dev_id: str
        :param code: The message code, defaults to None.
        :type code: Code | None, optional
        :param verb: The verb type, defaults to " I".
        :type verb: str, optional
        :param payload: The payload string, defaults to "00".
        :type payload: str, optional
        """
        if self._gwy.msg_db:
            self._gwy.msg_db.add_record(
                dev_id, code=str(code), verb=verb, payload=payload
            )

    async def _delete_msg(self, msg: Message) -> None:
        """Remove the msg from all state databases.

        :param msg: The message to delete.
        :type msg: Message
        """
        if self._gwy.msg_db:
            await cast("MessageIndex", self._gwy.msg_db).rem(msg)

        entities: list[Any] = []
        if hasattr(msg.src, "tcs"):
            entities = [msg.src]
            tcs = getattr(msg.src, "tcs", None)
            if tcs:
                entities.append(tcs)
                if getattr(tcs, "dhw", None):
                    entities.append(tcs.dhw)
                if getattr(tcs, "zones", None):
                    entities.extend(tcs.zones)

        for obj in entities:
            if hasattr(obj, "state_store"):
                store = obj.state_store
                if msg.code in store._msgs_ and store._msgs_[msg.code] == msg:
                    del store._msgs_[msg.code]
                if not self._gwy.msg_db:
                    with contextlib.suppress(KeyError):
                        del store._msgz_[msg.code][msg.verb][msg._pkt._ctx]

    async def _get_msg_by_hdr(self, hdr: HeaderT) -> Message | None:
        """Return a msg, if any, that matches a given header.

        :param hdr: The header string to match.
        :type hdr: HeaderT
        :returns: The matching Message, or None.
        :rtype: Message | None
        :raises DatabaseQueryError: If the retrieved header does not match.
        """
        if self._gwy.msg_db:
            msgs = await self._gwy.msg_db.get(hdr=hdr)
            if msgs:
                if msgs[0]._pkt._hdr != hdr:
                    raise exc.DatabaseQueryError(
                        f"Header mismatch: {msgs[0]._pkt._hdr} != {hdr}"
                    )
                return msgs[0]
            return None

        code_str, verb_str, _, *args = hdr.split("|")
        code = Code(code_str)
        verb = VerbT(verb_str)
        msgz_dict = await self._msgz()

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

    async def _msg_flag(self, code: Code, key: str, idx: int) -> bool | None:
        """Get the boolean value of a specific flag within a message payload.

        :param code: Filter messages by Code.
        :type code: Code
        :param key: The payload keyword containing the flags.
        :type key: str
        :param idx: The index of the flag to retrieve.
        :type idx: int
        :returns: The flag value, or None if the message/key is missing.
        :rtype: bool | None
        """
        if flags := await self._msg_value(code, key=key):
            return bool(flags[idx])
        return None

    async def _msg_value(
        self, code: Code | tuple[Code, ...] | Message, *args: Any, **kwargs: Any
    ) -> Any:
        """Get the value for a Code from the database or from a Message.

        :param code: Filter messages by Code, a tuple of codes, or a Message.
        :type code: Code | tuple[Code, ...] | Message
        :param args: Optional Message arguments.
        :type args: Any
        :param kwargs: Optional keyword filters.
        :type kwargs: Any
        :returns: A dictionary containing key: value pairs, or a list.
        :rtype: Any
        """
        if isinstance(code, (str, tuple)):
            return await self._msg_value_code(code, *args, **kwargs)

        assert isinstance(code, Message), f"Invalid format: _msg_value({code})"
        return self._msg_value_msg(code, *args, **kwargs)

    async def _msg_value_code(
        self,
        code: Code | tuple[Code, ...],
        verb: VerbT | None = None,
        key: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Query the index for the most recent key: value pairs.

        :param code: Filter messages by Code or a tuple of Codes.
        :type code: Code | tuple[Code, ...]
        :param verb: Filter by verb, defaults to None.
        :type verb: VerbT | None, optional
        :param key: Value keyword to retrieve, defaults to None.
        :type key: str | None, optional
        :param kwargs: Extra filters.
        :type kwargs: Any
        :returns: A dictionary containing key: value pairs, or a list.
        :rtype: Any
        """
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
                if self._gwy.msg_db:
                    cd = await self._msg_qry_by_code_key(code, key, **kwargs, verb=verb)
                    msg = (await self._msgs()).get(cd) if cd else None
                else:
                    msgz_dict = await self._msgz()
                    msgs = msgz_dict[cast("Code", code)][verb]
                    msg = max(msgs.values()) if msgs else None
            except KeyError:
                msg = None
        elif isinstance(code, tuple):
            msgs_dict = await self._msgs()
            msgs_list = [m for m in msgs_dict.values() if m.code in code]
            msg = max(msgs_list) if msgs_list else None
        else:
            msgs_dict = await self._msgs()
            msg = msgs_dict.get(code)

        return self._msg_value_msg(msg, key=key, **kwargs)

    def _msg_value_msg(
        self,
        msg: Message | None,
        key: str | None = "*",
        zone_idx: str | None = None,
        domain_id: str | None = None,
    ) -> Any:
        """Get all or a specific key with its values from a Message.

        :param msg: The Message to inspect.
        :type msg: Message | None
        :param key: The key to filter on, defaults to "*".
        :type key: str | None, optional
        :param zone_idx: The zone to filter on, defaults to None.
        :type zone_idx: str | None, optional
        :param domain_id: The domain to filter on, defaults to None.
        :type domain_id: str | None, optional
        :returns: A dictionary containing key: value pairs, or a list.
        :rtype: Any
        """
        if msg is None:
            return None
        elif msg._expired:
            # Note: relies on the gateway loop to manage tasks
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
        """Retrieve a list of Code keys involving this device.

        :returns: A list of Codes or None.
        :rtype: list[Code] | None
        """
        if not self._gwy.msg_db:
            raise NotImplementedError("Missing MessageIndex")

        res: list[Code] = []
        entity_id = self._entity.id

        if len(entity_id) == 9:
            sql = """
                SELECT code from messages WHERE
                verb in (' I', 'RP')
                AND (src = ? OR dst = ?)
                AND ctx LIKE ?
            """
            _ctx_qry = "%"
        elif entity_id[_ID_SLICE:] == "_HW":
            sql = """
                SELECT code from messages WHERE
                verb in (' I', 'RP')
                AND (src = ? OR dst = ?)
                AND (ctx IN ('FC', 'FA', 'F9', 'FA') OR plk LIKE ?)
            """
            _ctx_qry = "%dhw_idx%"
        else:
            sql = """
                SELECT code from messages WHERE
                verb in (' I', 'RP')
                AND (src = ? OR dst = ?)
                AND ctx LIKE ?
            """
            _ctx_qry = f"%{entity_id[_ID_SLICE + 1 :]}%"

        for rec in await self._gwy.msg_db.qry_field(
            sql, (entity_id[:_ID_SLICE], entity_id[:_ID_SLICE], _ctx_qry)
        ):
            res.append(Code(str(rec[0])))
        return res

    async def _msg_qry_by_code_key(
        self,
        code: Code | tuple[Code, ...] | None = None,
        key: str | None = None,
        **kwargs: Any,
    ) -> Code | None:
        """Retrieve the most current Code involving this device.

        :param code: A message Code or tuple of Codes, defaults to None.
        :type code: Code | tuple[Code, ...] | None, optional
        :param key: Message keyword to fetch, defaults to None.
        :type key: str | None, optional
        :param kwargs: Optional filters like verb.
        :type kwargs: Any
        :returns: The Code of the most recent query result message or None.
        :rtype: Code | None
        """
        if not self._gwy.msg_db:
            raise NotImplementedError("Missing MessageIndex")

        code_qry: str = "= "
        if code is None:
            code_qry = "LIKE '%'"
        elif isinstance(code, tuple):
            for cd in code:
                code_qry += f"'{str(cd)}' OR code = '"
            code_qry = code_qry[:-13]
        else:
            code_qry += str(code)

        if kwargs.get("verb") and kwargs["verb"] in (" I", "RP"):
            vb = f"('{str(kwargs['verb'])}',)"
        else:
            vb = "(' I', 'RP',)"

        ctx_qry = "%"
        if kwargs.get("zone_idx"):
            ctx_qry = f"%{kwargs['zone_idx']}%"
        elif kwargs.get("dhw_idx"):
            ctx_qry = f"%{kwargs['dhw_idx']}%"
        key_qry = "%" if key is None else f"%{key}%"

        sql = """
            SELECT dtm, code from messages WHERE
            verb in ?
            AND (src = ? OR dst = ?)
            AND (code ?)
            AND (ctx LIKE ?)
            AND (plk LIKE ?)
        """
        latest: dt = dt(0, 0, 0)
        res = None

        entity_id = self._entity.id
        for rec in await self._gwy.msg_db.qry_field(
            sql,
            (
                vb,
                entity_id[:_ID_SLICE],
                entity_id[:_ID_SLICE],
                code_qry,
                ctx_qry,
                key_qry,
            ),
        ):
            assert isinstance(rec[0], dt)
            if rec[0] > latest:
                res = Code(str(rec[1]))
                latest = rec[0]
        return res

    async def _msg_qry(self, sql: str) -> list[dict[str, Any]]:
        """Custom query for an entity's stored payloads.

        :param sql: Custom SQLite query on MessageIndex.
        :type sql: str
        :returns: A list of payload dicts.
        :rtype: list[dict[str, Any]]
        """
        res: list[dict[str, Any]] = []
        if sql and self._gwy.msg_db:
            entity_id = self._entity.id
            for rec in await self._gwy.msg_db.qry_field(
                sql, (entity_id[:_ID_SLICE], entity_id[:_ID_SLICE])
            ):
                msgs_dict = await self._msgs()
                _pl = msgs_dict[Code(str(rec[0]))].payload
                res.append(cast("dict[str, Any]", _pl))
        return res

    async def _msgs(self) -> dict[Code, Message]:
        """Get a flat dict of all I/RP messages logged.

        :returns: Flat dict of messages by Code.
        :rtype: dict[Code, Message]
        """
        if not self._gwy.msg_db:
            return self._msgs_

        entity_id = self._entity.id
        if len(entity_id) == 9:
            sql = """
                SELECT dtm, code from messages WHERE
                verb in (' I', 'RP')
                AND (src = ? OR dst = ?)
                AND ctx LIKE ?
            """
            _ctx_qry = "%"
        elif entity_id[_ID_SLICE:] == "_HW":
            sql = """
                SELECT dtm, code from messages WHERE
                verb in (' I', 'RP')
                AND (src = ? OR dst = ?)
                AND (ctx IN ('FC', 'FA', 'F9', 'FA') OR plk LIKE ?)
            """
            _ctx_qry = "%dhw_idx%"
        else:
            sql = """
                SELECT dtm, code from messages WHERE
                verb in (' I', 'RP')
                AND (src = ? OR dst = ?)
                AND ctx LIKE ?
            """
            _ctx_qry = f"%{entity_id[_ID_SLICE + 1 :]}%"

        _msg_dict = {
            Code(str(m.code)): m
            for m in await self._gwy.msg_db.qry(
                sql, (entity_id[:_ID_SLICE], entity_id[:_ID_SLICE], _ctx_qry)
            )
        }
        return _msg_dict

    async def _msgz(
        self,
    ) -> dict[Code, dict[VerbT, dict[bool | str | None, Message]]]:
        """Get a nested dict of all I/RP messages.

        :returns: Dict of messages nested by Code, Verb, Context.
        :rtype: dict[Code, dict[VerbT, dict[bool | str | None, Message]]]
        """
        if not self._gwy.msg_db:
            return self._msgz_

        msgs_1: dict[Code, dict[VerbT, dict[bool | str | None, Message]]] = {}
        msgs_dict = await self._msgs()

        for msg in msgs_dict.values():
            if msg.code not in msgs_1:
                msgs_1[msg.code] = {msg.verb: {msg._pkt._ctx: msg}}
            elif msg.verb not in msgs_1[msg.code]:
                msgs_1[msg.code][msg.verb] = {msg._pkt._ctx: msg}
            else:
                msgs_1[msg.code][msg.verb][msg._pkt._ctx] = msg

        return msgs_1

    def _handle_msg(self, msg: Message) -> None:
        """Update internal message stores with a new packet.

        :param msg: The message to index and store.
        :type msg: Message
        """
        if self._gwy.msg_db:
            self._gwy.msg_db.add(msg)
        else:
            if msg.code not in self._msgz_:
                self._msgz_[msg.code] = {msg.verb: {msg._pkt._ctx: msg}}
            elif msg.verb not in self._msgz_[msg.code]:
                self._msgz_[msg.code][msg.verb] = {msg._pkt._ctx: msg}
            else:
                self._msgz_[msg.code][msg.verb][msg._pkt._ctx] = msg

        if msg.verb in (I_, RP):
            self._msgs_[msg.code] = msg

    async def traits(self) -> dict[str, Any]:
        """Get the codes seen by the entity.

        :returns: A dictionary containing the list of sent codes.
        :rtype: dict[str, Any]
        """
        msgs_dict = await self._msgs()
        codes = {
            code: (CODES_SCHEMA[code][SZ_NAME] if code in CODES_SCHEMA else None)
            for code in sorted(msgs_dict)
            if msgs_dict[code].src.id == self._entity.id[:9]
        }
        return {"_sent": list(codes.keys())}
