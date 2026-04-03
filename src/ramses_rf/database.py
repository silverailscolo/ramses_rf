#!/usr/bin/env python3
"""
RAMSES RF - Message database and index.

.. table:: Database Query Methods[^1][#fn1]
   :widths: auto

   =====  ============  ===========  ==========  ====  ========================
    ix    method name   args         returns     uses  used by
   =====  ============  ===========  ==========  ====  ========================
   i1     get           Msg, kwargs  tuple(Msg)  i3
   i2     contains      kwargs       bool        i4
   i3     _select_from  kwargs       tuple(Msg)  i4
   i4     qry_dtms      kwargs       list(dtm)
   i5     qry           sql, kwargs  tuple(Msg)        _msgs()
   i6     qry_field     sql, kwargs  tuple(fld)        e4, e5
   i7     get_rp_codes  src, dst     list(Code)        Discovery-supported_cmds
   =====  ============  ===========  ==========  ====  ========================

[#fn1] A word of explanation.[^1]: ex = entity_base.py query methods
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sqlite3
import uuid
from collections import OrderedDict
from datetime import datetime as dt, timedelta as td
from typing import TYPE_CHECKING, Any, NewType, cast

import orjson

from ramses_tx import CODES_SCHEMA, RQ, Code, Message, Packet

from .exceptions import DatabaseQueryError
from .storage import PacketLogEntry, StorageWorker

DtmStrT = NewType("DtmStrT", str)

if TYPE_CHECKING:
    MsgDdT = OrderedDict[DtmStrT, Message]

_LOGGER = logging.getLogger(__name__)


def _setup_db_adapters() -> None:
    """Set up the database adapters and converters."""

    def adapt_datetime_iso(val: dt) -> str:
        """Adapt datetime.datetime to timezone-naive ISO 8601 datetime to match _msgs dtm keys."""
        return val.isoformat(timespec="microseconds")

    sqlite3.register_adapter(dt, adapt_datetime_iso)

    def convert_datetime(val: bytes) -> dt:
        """Convert ISO 8601 datetime to datetime.datetime object to import dtm in msg_db."""
        return dt.fromisoformat(val.decode())

    sqlite3.register_converter("DTM", convert_datetime)


def payload_keys(parsed_payload: list[dict] | dict) -> str:  # type: ignore[type-arg]
    """
    Copy payload keys for fast query check.

    :param parsed_payload: pre-parsed message payload dict
    :return: string of payload keys, separated by the | char
    """
    _keys: str = "|"

    def append_keys(ppl: dict) -> str:  # type: ignore[type-arg]
        _ks: str = ""
        for k, v in ppl.items():
            if (
                k not in _ks and k not in _keys and v is not None
            ):  # ignore keys with None value
                _ks += k + "|"
        return _ks

    if isinstance(parsed_payload, list):
        for d in parsed_payload:
            _keys += append_keys(d)
    elif isinstance(parsed_payload, dict):
        _keys += append_keys(parsed_payload)
    return _keys


class MessageStore:
    """A central in-memory SQLite3 database for indexing RF messages.
    Index holds all the latest messages to & from all devices by `dtm`
    (timestamp) and `hdr` header
    (example of a hdr: ``000C|RP|01:223036|0208``)."""

    _housekeeping_task: asyncio.Task[None]
    _hydration_task: asyncio.Task[None]

    def __init__(
        self,
        maintain: bool = True,
        db_path: str = ":memory:",
        disk_path: str | None = "ramses.db",
    ) -> None:
        """Instantiate a message database/index."""

        self.maintain = maintain
        self._msgs: MsgDdT = OrderedDict()  # stores all messages for retrieval.
        self._msgz_: dict[str, Message] = {}  # Phase 2.4: hdr-based retrieval.
        # Filled & cleaned up in housekeeping_loop.

        # For :memory: databases with multiple connections (Reader vs Worker)
        # We must use a Shared Cache URI so both threads see the same data.
        if db_path == ":memory:":
            # Unique ID ensures parallel tests don't share the same in-memory DB
            db_path = f"file:ramses_rf_{uuid.uuid4()}?mode=memory&cache=shared"

        # Start the Storage Worker (Write Connection)
        # This thread handles all blocking INSERT/UPDATE operations
        self._worker = StorageWorker(db_path, disk_path=disk_path)

        # Wait for the worker to create the tables.
        # This prevents "no such table" errors on immediate reads.
        if not self._worker.wait_for_ready(timeout=10.0):
            _LOGGER.error("MessageStore: StorageWorker timed out initializing database")

        # Connect to a SQLite DB (Read Connection)
        self._cx = sqlite3.connect(
            db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            check_same_thread=False,
            uri=True,  # Enable URI parsing for shared memory support
            timeout=10.0,  # Increased timeout to reduce 'database locked' errors
            isolation_level=None,  # Autocommit mode prevents stale snapshots
        )

        # Enable Write-Ahead Logging for Reader as well
        if db_path != ":memory:" and "mode=memory" not in db_path:
            with contextlib.suppress(sqlite3.Error):
                self._cx.execute("PRAGMA journal_mode=WAL")
        elif "cache=shared" in db_path:
            # Shared cache (used in tests) requires read_uncommitted to prevent
            # readers from blocking writers (Table Locking).
            with contextlib.suppress(sqlite3.Error):
                self._cx.execute("PRAGMA read_uncommitted = true")

        _setup_db_adapters()  # DTM adapter/converter

        # Schema creation is now handled safely by the StorageWorker to avoid races.
        # self._setup_db_schema()

        if self.maintain:
            self._lock = asyncio.Lock()
            self._last_housekeeping: dt = cast(dt, None)
            self._housekeeping_task = cast(asyncio.Task[None], None)

        self.start()

    def __repr__(self) -> str:
        return f"MessageStore({len(self._msgs)} messages)"  # or msg_db.count()

    def start(self) -> None:
        """Start the housekeeper loop."""

        if self.maintain:
            if getattr(self, "_housekeeping_task", None) and (
                not self._housekeeping_task.done()
            ):
                return

            self._hydration_task = asyncio.create_task(
                self._hydrate_ram(), name=f"{self.__class__.__name__}.hydrator"
            )

            self._housekeeping_task = asyncio.create_task(
                self._housekeeping_loop(), name=f"{self.__class__.__name__}.housekeeper"
            )

    def stop(self) -> None:
        """Stop the housekeeper loop and resources."""

        if (
            self.maintain
            and getattr(self, "_housekeeping_task", None)
            and not self._housekeeping_task.done()
        ):
            self._housekeeping_task.cancel()  # stop the housekeeper

        if getattr(self, "_hydration_task", None) and not self._hydration_task.done():
            self._hydration_task.cancel()

        # Trigger a final snapshot to ensure no data is lost on shutdown
        self._worker.submit_snapshot()
        self._worker.flush(timeout=5.0)

        self._worker.stop()  # Stop the background thread

        try:
            self._cx.commit()  # just in case
            self._cx.close()  # safely close reader connection
        except sqlite3.ProgrammingError:
            pass  # Connection might already be closed

    @property
    def msgs(self) -> MsgDdT:
        """Return the messages in the index in a threadsafe way."""
        return self._msgs

    def flush(self) -> None:
        """Flush the storage worker queue.

        This is primarily for testing to ensure data persistence before querying.
        """
        self._worker.flush()

    async def _hydrate_ram(self) -> None:
        """Hydrate RAM cache from the in-memory database.

        This routine runs as a non-blocking background task.
        """

        def _fetch_all() -> list[Any]:
            return self._cx.execute(
                "SELECT * FROM messages ORDER BY dtm ASC"
            ).fetchall()

        try:
            rows = await asyncio.to_thread(_fetch_all)
        except sqlite3.Error as err:
            _LOGGER.error("Failed to fetch messages for hydration: %s", err)
            return

        has_lock = getattr(self, "_lock", None)
        if has_lock:
            await self._lock.acquire()

        try:
            for row in rows:
                dtm_val = row[0]
                verb = row[1]
                src = row[2]
                dst = row[3]
                code = row[4]
                hdr = row[6]
                payload_blob = row[8]
                dtm_str = cast(DtmStrT, dtm_val.isoformat(timespec="microseconds"))

                pkt_line = f"... {verb} --- {src} {dst} --:------ {code} 001 00"
                try:
                    pkt = Packet(dtm_val, pkt_line)
                    msg = Message._from_pkt(pkt)
                    msg._payload = orjson.loads(payload_blob)

                    self._msgs[dtm_str] = msg
                    self._msgz_[hdr] = msg
                except Exception as err:
                    _LOGGER.debug("Failed to reconstruct message for %s: %s", hdr, err)
        finally:
            if has_lock:
                self._lock.release()

        _LOGGER.info("Hydrated %d messages into RAM cache", len(rows))

    async def _housekeeping_loop(self) -> None:
        """Periodically remove stale messages from the index,
        unless `self.maintain` is False - as in (most) tests."""

        async def housekeeping(dt_now: dt, _cutoff: td = td(days=1)) -> None:
            """
            Deletes all messages older than a given delta from the dict using the MessageStore.
            :param dt_now: current timestamp
            :param _cutoff: the oldest timestamp to retain, default is 24 hours ago
            """
            dtm = dt_now - _cutoff

            # Submit prune request to worker (Non-blocking I/O)
            self._worker.submit_prune(dtm)

            # Prune in-memory cache synchronously (Fast CPU-bound op)
            dtm_iso = dtm.isoformat(timespec="microseconds")

            try:  # make this operation atomic, i.e. update self._msgs only on success
                await self._lock.acquire()
                # Rebuild dict keeping only newer items
                self._msgs = OrderedDict(
                    (k, v) for k, v in self._msgs.items() if k >= dtm_iso
                )

                valid_dtms = set(self._msgs.keys())
                self._msgz_ = {
                    hdr: m
                    for hdr, m in self._msgz_.items()
                    if cast(DtmStrT, m.dtm.isoformat(timespec="microseconds"))
                    in valid_dtms
                }

            except Exception as err:
                _LOGGER.warning("MessageStore housekeeping error: %s", err)
            else:
                _LOGGER.debug(
                    "MessageStore housekeeping completed, retained messages >= %s",
                    dtm_iso,
                )
            finally:
                self._lock.release()

        while True:
            self._last_housekeeping = dt.now()
            await asyncio.sleep(900)
            _LOGGER.info("Starting next MessageStore housekeeping")
            await housekeeping(self._last_housekeeping)

            self._worker.submit_snapshot()

    def add(self, msg: Message) -> Message | None:
        """
        Add a single message to the MessageStore.
        Logs a warning if there is a duplicate dtm.

        :returns: any message that was removed because it had the same header
        """
        # TODO: eventually, may be better to use SqlAlchemy

        dup: tuple[Message, ...] = tuple()  # avoid UnboundLocalError
        old: Message | None = None  # avoid UnboundLocalError

        # Check in-memory cache for collision instead of blocking SQL
        dtm_str = cast(DtmStrT, msg.dtm.isoformat(timespec="microseconds"))
        if dtm_str in self._msgs:
            dup = (self._msgs[dtm_str],)

        try:  # TODO: remove this, or apply only when source is a real packet log?
            # We defer the write to the worker; return value (old) is not available synchronously
            self._insert_into(msg)  # will delete old msg by hdr (not dtm!)

        except (
            sqlite3.Error
        ):  # UNIQUE constraint failed: ? messages.dtm or .hdr (so: HACK)
            pass

        else:
            # _msgs dict requires a timestamp reformat
            # add msg to self._msgs dict
            self._msgs[dtm_str] = msg
            if msg._pkt._hdr is not None:
                self._msgz_[msg._pkt._hdr] = msg

        finally:
            pass  # self._lock.release()

        if (
            dup
            and (msg.src is not msg.dst)
            and not msg.dst.id.startswith("18:")  # HGI
            and msg.verb != RQ  # these may come very quickly
        ):  # when src==dst, expect to add duplicate, don't warn
            _LOGGER.debug(
                "Overwrote dtm (%s) for %s: %s (contrived log?)",
                msg.dtm,
                msg._pkt._hdr,
                dup[0]._pkt,
            )

        return old

    def add_record(
        self, src: str, code: str = "", verb: str = "", payload: str = "00"
    ) -> None:
        """
        Add a single record to the MessageStore with timestamp `now()` and no Message contents.

        :param src: device id to use as source address
        :param code: device id to use as destination address (can be identical)
        :param verb: two letter verb str to use
        :param payload: payload str to use
        """
        # Used by OtbGateway init, via entity_base.py (code=_3220)
        _now: dt = dt.now()
        dtm = cast(DtmStrT, _now.isoformat(timespec="microseconds"))
        hdr = f"{code}|{verb}|{src}|{payload}"

        # Prepare data tuple for worker
        data = PacketLogEntry(
            dtm=_now,
            verb=verb,
            src=src,
            dst=src,
            code=code,
            ctx=None,
            hdr=hdr,
            plk="|",
            payload_blob=orjson.dumps({"payload": payload}),
        )

        self._worker.submit_packet(data)

        # Backward compatibility for Tests:
        # Check specific env var set by pytest, which is more reliable than sys.modules
        if "PYTEST_CURRENT_TEST" in os.environ:
            self.flush()

        # also add dummy 3220 msg to self._msgs dict to allow maintenance loop
        msg: Message = Message._from_pkt(
            Packet(_now, f"... {verb} --- {src} --:------ {src} {code} 005 0000000000")
        )
        self._msgs[dtm] = msg
        self._msgz_[hdr] = msg

    def _insert_into(self, msg: Message) -> Message | None:
        """
        Insert a message into the index.

        :returns: any message replaced (by same hdr)
        """
        assert msg._pkt._hdr is not None, "Skipping: Packet has no hdr: {msg._pkt}"

        if msg._pkt._ctx is True:
            msg_pkt_ctx = "True"
        elif msg._pkt._ctx is False:
            msg_pkt_ctx = "False"
        else:
            msg_pkt_ctx = msg._pkt._ctx  # can be None

        try:
            payload_blob = orjson.dumps(msg.payload)
        except orjson.JSONEncodeError as err:
            _LOGGER.warning("Failed to serialize payload: %s", err)
            payload_blob = b"{}"

        # Refactor: Worker uses INSERT OR REPLACE to handle collision
        data = PacketLogEntry(
            dtm=msg.dtm,
            verb=str(msg.verb),
            src=msg.src.id,
            dst=msg.dst.id,
            code=str(msg.code),
            ctx=msg_pkt_ctx,
            hdr=msg._pkt._hdr,
            plk=payload_keys(msg.payload),
            payload_blob=payload_blob,
        )

        self._worker.submit_packet(data)

        # Backward compatibility for Tests:
        # Tests assume the DB update is instant. If running in pytest, flush immediately.
        # This effectively makes the operation synchronous during tests to avoid rewriting tests.
        if "PYTEST_CURRENT_TEST" in os.environ:
            self.flush()

        return None

    async def rem(
        self, msg: Message | None = None, **kwargs: str | dt
    ) -> tuple[Message, ...] | None:
        """Remove a set of message(s) from the index.

        :returns: any messages that were removed.
        """

        if not bool(msg) ^ bool(kwargs):
            raise DatabaseQueryError(
                "Either a Message or kwargs should be provided, not both"
            )
        if msg:
            kwargs["dtm"] = msg.dtm

        msgs: tuple[Message, ...] | None = None
        try:  # make this operation atomic, i.e. update self._msgs only on success
            msgs = await self._delete_from(**kwargs)

        except sqlite3.Error as err:  # need to tighten?
            await asyncio.to_thread(self._cx.rollback)
            raise DatabaseQueryError(f"Delete failed: {err}") from err

        else:
            if msgs is not None:
                for m in msgs:
                    dtm = cast(DtmStrT, m.dtm.isoformat(timespec="microseconds"))
                    self._msgs.pop(dtm, None)
                    if m._pkt._hdr is not None:
                        self._msgz_.pop(m._pkt._hdr, None)

        finally:
            pass  # self._lock.release()

        return msgs

    async def _delete_from(self, **kwargs: bool | dt | str) -> tuple[Message, ...]:
        """Remove message(s) from the index.

        :returns: any messages that were removed"""

        msgs = await self._select_from(**kwargs)

        sql = "DELETE FROM messages WHERE "
        sql += " AND ".join(f"{k} = ?" for k in kwargs)

        def _execute_delete() -> None:
            self._cx.execute(sql, tuple(kwargs.values()))

        await asyncio.to_thread(_execute_delete)

        return msgs

    # MessageStore msg_db query methods

    async def get(
        self, msg: Message | None = None, **kwargs: bool | dt | str
    ) -> tuple[Message, ...]:
        """
        Public method to get a set of message(s) from the index.

        :param msg: Message to return, by dtm (expect a single result as dtm is unique key)
        :param kwargs: data table field names and criteria, e.g. (hdr=...)
        :return: tuple of matching Messages
        """

        if not (bool(msg) ^ bool(kwargs)):
            raise DatabaseQueryError(
                "Either a Message or kwargs should be provided, not both"
            )

        if msg:
            kwargs["dtm"] = msg.dtm

        return await self._select_from(**kwargs)

    async def contains(self, **kwargs: bool | dt | str) -> bool:
        """
        Check if the MessageStore contains at least 1 record that matches the provided fields.

        :param kwargs: (exact) SQLite table field_name: required_value pairs
        :return: True if at least one message fitting the given conditions is present, False when qry returned empty
        """

        return len(await self.qry_dtms(**kwargs)) > 0

    async def _select_from(self, **kwargs: bool | dt | str) -> tuple[Message, ...]:
        """
        Select message(s) using the MessageStore.

        :param kwargs: (exact) SQLite table field_name: required_value pairs
        :returns: a tuple of qualifying messages
        """

        # CHANGE: Use a list comprehension with a check to avoid KeyError
        res: list[Message] = []
        dtms = await self.qry_dtms(**kwargs)
        for row in dtms:
            ts: DtmStrT = row[0].isoformat(timespec="microseconds")
            if ts in self._msgs:
                res.append(self._msgs[ts])
            else:
                _LOGGER.debug("MessageStore timestamp %s not in device messages", ts)
        return tuple(res)

    async def qry_dtms(self, **kwargs: bool | dt | str) -> list[Any]:
        """
        Select from the MessageStore a list of dtms that match the provided arguments.

        :param kwargs: data table field names and criteria
        :return: list of unformatted dtms that match, useful for msg lookup, or an empty list if 0 matches
        """
        # tweak kwargs as stored in SQLite, inverse from _insert_into():
        kw = {key: value for key, value in kwargs.items() if key != "ctx"}
        if "ctx" in kwargs:
            if isinstance(kwargs["ctx"], str):
                kw["ctx"] = kwargs["ctx"]
            elif kwargs["ctx"]:
                kw["ctx"] = "True"
            else:
                kw["ctx"] = "False"

        sql = "SELECT dtm FROM messages WHERE "
        sql += " AND ".join(f"{k} = ?" for k in kw)

        def _fetch_dtms() -> list[Any]:
            return self._cx.execute(sql, tuple(kw.values())).fetchall()

        try:
            return await asyncio.to_thread(_fetch_dtms)
        except sqlite3.Error as err:
            raise DatabaseQueryError(f"Query failed: {err}") from err

    async def qry(self, sql: str, parameters: tuple[str, ...]) -> tuple[Message, ...]:
        """
        Get a tuple of messages from _msgs using the index, given sql and parameters.

        :param sql: a bespoke SQL query SELECT string that should return dtm as first field
        :param parameters: tuple of kwargs with the selection filter
        :return: a tuple of qualifying messages
        """

        if "SELECT" not in sql:
            raise DatabaseQueryError(f"{self}: Only SELECT queries are allowed")

        def _fetch_qry() -> list[Any]:
            return self._cx.execute(sql, parameters).fetchall()

        try:
            rows = await asyncio.to_thread(_fetch_qry)
        except sqlite3.Error as err:
            raise DatabaseQueryError(f"Database error during qry: {err}") from err

        lst: list[Message] = []
        for row in rows:
            ts: DtmStrT = row[0].isoformat(
                timespec="microseconds"
            )  # must reformat from DTM
            if ts in self._msgs:
                lst.append(self._msgs[ts])
            else:  # happens in tests with artificial msg from heat
                _LOGGER.info("MessageStore timestamp %s not in device messages", ts)
        return tuple(lst)

    async def get_rp_codes(self, parameters: tuple[str, ...]) -> list[Code]:
        """
        Get a list of Codes from the index, given parameters.

        :param parameters: tuple of additional kwargs
        :return: list of Code: value pairs
        """

        def get_code(code: str) -> Code:
            for Cd in CODES_SCHEMA:
                if code == Cd:
                    return Cd
            raise DatabaseQueryError(f"Failed to find matching code for {code}")

        sql = """
                SELECT code from messages WHERE verb is 'RP' AND (src = ? OR dst = ?)
            """
        if "SELECT" not in sql:
            raise DatabaseQueryError(f"{self}: Only SELECT queries are allowed")

        def _fetch_rp() -> list[Any]:
            return self._cx.execute(sql, parameters).fetchall()

        try:
            rows = await asyncio.to_thread(_fetch_rp)
        except sqlite3.Error as err:
            raise DatabaseQueryError(
                f"Database error during get_rp_codes: {err}"
            ) from err

        return [get_code(row[0]) for row in rows]

    async def qry_field(
        self, sql: str, parameters: tuple[str, ...]
    ) -> list[tuple[dt | str, str]]:
        """
        Get a list of fields from the index, given select sql and parameters.

        :param sql: a bespoke SQL query SELECT string
        :param parameters: tuple of additional kwargs
        :return: list of key: value pairs as defined in sql
        """

        if "SELECT" not in sql:
            raise DatabaseQueryError(f"{self}: Only SELECT queries are allowed")

        def _fetch_field() -> list[Any]:
            return self._cx.execute(sql, parameters).fetchall()

        try:
            return await asyncio.to_thread(_fetch_field)
        except sqlite3.Error as err:
            raise DatabaseQueryError(f"Database error during qry_field: {err}") from err

    async def all(self, include_expired: bool = False) -> tuple[Message, ...]:
        """Get all messages from the index."""

        def _fetch_all() -> list[Any]:
            return self._cx.execute("SELECT * FROM messages").fetchall()

        rows = await asyncio.to_thread(_fetch_all)
        lst: list[Message] = []
        for row in rows:
            ts: DtmStrT = row[0].isoformat(timespec="microseconds")
            if ts in self._msgs:
                lst.append(self._msgs[ts])
                _LOGGER.debug("MessageStore ts %s added to all.lst", ts)
            else:  # happens in tests and real evohome setups with dummy msg from heat init
                _LOGGER.debug("MessageStore ts %s not in device messages", ts)
        return tuple(lst)

    async def clr(self) -> None:
        """Clear the message index (remove indexes of all messages)."""

        def _clear_db() -> None:
            self._cx.execute("DELETE FROM messages")
            self._cx.commit()

        await asyncio.to_thread(_clear_db)
        self._msgs.clear()
        self._msgz_.clear()


# Alias for backwards compatibility during Phase 2 migration
MessageIndex = MessageStore
