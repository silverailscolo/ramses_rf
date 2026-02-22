#!/usr/bin/env python3
"""RAMSES RF - a RAMSES-II protocol decoder & analyser.

Decode/process a packet (packet that was received).
"""

from __future__ import annotations

from datetime import datetime as dt, timedelta as td

from .command import Command
from .const import I_, RP, RQ, W_, Code
from .exceptions import PacketInvalid
from .frame import Frame
from .logger import getLogger  # overridden logger.getLogger
from .opentherm import PARAMS_DATA_IDS, SCHEMA_DATA_IDS, STATUS_DATA_IDS
from .ramses import CODES_SCHEMA, SZ_LIFESPAN

# these trade memory for speed
_TD_SECS_000 = td(seconds=0)
_TD_SECS_003 = td(seconds=3)
_TD_SECS_360 = td(seconds=360)
_TD_MINS_005 = td(minutes=5)
_TD_MINS_060 = td(minutes=60)
_TD_MINS_360 = td(minutes=360)
_TD_DAYS_001 = td(minutes=60 * 24)


PKT_LOGGER = getLogger(f"{__name__}_log", pkt_log=True)


class Packet(Frame):
    """The Packet class (pkts that were received); will trap/log invalid pkts.

    They have a datetime (when received) an RSSI, and other meta-fields.
    """

    _dtm: dt
    _rssi: str

    def __init__(
        self,
        dtm: dt,
        frame: str,
        /,
        *,
        comment: str = "",
        err_msg: str = "",
        raw_frame: bytes | str = "",
    ) -> None:
        """Create a packet from a raw frame string.

        :param dtm: The timestamp when the packet was received
        :type dtm: dt
        :param frame: The raw frame string, typically including RSSI
        :type frame: str
        :param comment: Optional comment extracted from the log line
        :type comment: str
        :param err_msg: Optional error message from the packet parser
        :type err_msg: str
        :param raw_frame: Original raw byte/string frame before parsing
        :type raw_frame: bytes | str
        :raises PacketInvalid: If the frame content is malformed.
        """
        self._dtm = dtm
        self._rssi = frame[0:3]

        self.comment: str = comment
        self.error_text: str = err_msg
        self.raw_frame: bytes | str = raw_frame

        # Intercept null packets before the strict Frame regex validation explodes
        if not frame[4:].strip() and self.comment:
            raise PacketInvalid("Null packet")

        super().__init__(frame[4:])  # remove RSSI

        self._lifespan: bool | td = pkt_lifespan(self) or False

        self._validate(strict_checking=False)

    def _validate(self, *, strict_checking: bool = False) -> None:
        """Validate the packet, and parse the addresses if so (will log all packets).

        Raise an exception InvalidPacketError (InvalidAddrSetError) if it is not valid.
        """
        try:
            if self.error_text:
                raise PacketInvalid(self.error_text)

            super()._validate(strict_checking=strict_checking)  # no RSSI

            PKT_LOGGER.info("", extra=self.__dict__)  # the packet.log line

        except PacketInvalid as err:  # incl. InvalidAddrSetError
            if self._frame or self.error_text:
                PKT_LOGGER.warning("%s", err, extra=self.__dict__)
            raise err

    def __repr__(self) -> str:
        """Return an unambiguous string representation of this object."""
        # e.g.: RQ --- 18:000730 01:145038 --:------ 000A 002 0800  # 000A|RQ|01:145038|08
        try:
            hdr = f" # {self._hdr}{f' ({self._ctx})' if self._ctx else ''}"
        except (PacketInvalid, NotImplementedError):
            hdr = ""
        try:
            dtm_str = self.dtm.isoformat(timespec="microseconds")
        except AttributeError:
            dtm_str = dt.min.isoformat(timespec="microseconds")
        return f"{dtm_str} ... {self}{hdr}"

    def __str__(self) -> str:
        """Return a brief readable string representation of this object aka 'header'."""
        # e.g.: 000A|RQ|01:145038|08
        return super().__repr__()  # TODO: self._hdr

    @property
    def dtm(self) -> dt:
        """Return the datetime when the packet was received."""
        return self._dtm

    @property
    def rssi(self) -> str:
        """Return the received signal strength indicator (RSSI)."""
        return self._rssi

    @staticmethod
    def _partition(pkt_line: str) -> tuple[str, str, str]:  # map[str]
        """Partition a packet line into its three parts.

        Format: packet[ < parser-hint: ...][ * evofw3-err_msg][ # evofw3-comment]
        """
        fragment, _, comment = pkt_line.partition("#")
        fragment, _, err_msg = fragment.partition("*")
        pkt_str, _, _ = fragment.partition("<")  # discard any parser hints

        # We explicitly cast back to a strictly typed tuple
        parts = tuple(map(str.strip, (pkt_str, err_msg, comment)))
        return parts[0], parts[1], parts[2]

    @classmethod
    def _from_cmd(cls, cmd: Command, dtm: dt | None = None) -> Packet:
        """Create a Packet from a Command."""
        if dtm is None:
            dtm = dt.now()
        return cls.from_port(dtm, f"... {cmd._frame}")

    @classmethod
    def from_dict(cls, dtm: str, pkt_line: str) -> Packet:
        """Create a packet from a saved state (a curated dict)."""
        frame, _, comment = cls._partition(pkt_line)
        return cls(dt.fromisoformat(dtm), frame, comment=comment)

    @classmethod
    def from_file(cls, dtm: str, pkt_line: str) -> Packet:
        """Create a packet from a log file line."""
        frame, err_msg, comment = cls._partition(pkt_line)
        if not frame:
            raise ValueError(f"null frame: >>>{frame}<<<")
        return cls(dt.fromisoformat(dtm), frame, err_msg=err_msg, comment=comment)

    @classmethod
    def from_port(cls, dtm: dt, pkt_line: str, raw_line: bytes | str = "") -> Packet:
        """Create a packet from a USB port (HGI80, evofw3)."""
        frame, err_msg, comment = cls._partition(pkt_line)
        if not frame:
            raise ValueError(f"null frame: >>>{frame}<<<")
        return cls(dtm, frame, err_msg=err_msg, comment=comment, raw_frame=raw_line)


# TODO: remove None as a possible return value
def pkt_lifespan(pkt: Packet) -> td:  # import OtbGateway??
    """Return the lifespan of a packet before it expires.

    :param pkt: The packet instance to evaluate
    :type pkt: Packet
    :return: The duration the packet's data remains valid
    :rtype: td
    """
    if pkt.verb in (RQ, W_):
        return _TD_SECS_000

    if pkt.code in (Code._0005, Code._000C):
        return _TD_DAYS_001

    if pkt.code == Code._0006:
        return _TD_MINS_060

    if pkt.code == Code._0404:  # 0404 tombstoned by incremented 0006
        return _TD_DAYS_001

    if pkt.code == Code._000A and pkt._has_array:
        return _TD_MINS_060  # sends I /1h

    if pkt.code == Code._10E0:  # but: what if valid pkt with a corrupt src_id
        return _TD_DAYS_001

    if pkt.code == Code._1F09:  # sends I /sync_cycle
        # can't do better than 300s with reading the payload
        return _TD_SECS_360 if pkt.verb == I_ else _TD_SECS_000

    if pkt.code == Code._1FC9 and pkt.verb == RP:
        return _TD_DAYS_001  # TODO: check other verbs, they seem variable

    if pkt.code in (Code._2309, Code._30C9) and pkt._has_array:  # sends I /sync_cycle
        return _TD_SECS_360

    if pkt.code == Code._3220:  # FIXME: 2.1 means we can miss two packets
        # if pkt.payload[4:6] in WRITE_MSG_IDS:  #  and Write-Data:  # TODO
        #     return _TD_SECS_003 * 2.1
        if int(pkt.payload[4:6], 16) in SCHEMA_DATA_IDS:
            return _TD_MINS_360 * 2.1
        if int(pkt.payload[4:6], 16) in PARAMS_DATA_IDS:
            return _TD_MINS_060 * 2.1
        if int(pkt.payload[4:6], 16) in STATUS_DATA_IDS:
            return _TD_MINS_005 * 2.1
        return _TD_MINS_005 * 2.1

    # if pkt.code in (Code._3B00, Code._3EF0, ):  # TODO: 0008, 3EF0, 3EF1
    #     return td(minutes=6.7)  # TODO: WIP

    if (code := CODES_SCHEMA.get(pkt.code)) and SZ_LIFESPAN in code:
        result: bool | td | None = CODES_SCHEMA[pkt.code][SZ_LIFESPAN]
        return result if isinstance(result, td) else _TD_MINS_060

    return _TD_MINS_060  # applies to lots of HVAC packets
