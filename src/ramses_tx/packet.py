#!/usr/bin/env python3
"""RAMSES RF - a RAMSES-II protocol decoder & analyser.

Decode/process a packet (packet that was received).
"""

from __future__ import annotations

import contextlib
from dataclasses import asdict, dataclass
from datetime import datetime as dt, timedelta as td
from typing import Any

from .command import Command
from .const import I_, RP, RQ, W_, Code, VerbT
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


@dataclass
class DeviceAddress:
    """Represents a split RAMSES-RF device address.

    :param device_type: The 2-digit device type, or None if '--'.
    :type device_type: int | None
    :param device_id: The 6-digit device ID, or None if '------'.
    :type device_id: int | None
    """

    device_type: int | None
    device_id: int | None

    @property
    def is_no_device(self) -> bool:
        """Checks if the address represents 'no device' (--:------)."""
        return self.device_type is None and self.device_id is None

    @property
    def is_null_device(self) -> bool:
        """Checks if the address represents the 'null device'."""
        return self.device_type == 63 and self.device_id == 262142

    def __str__(self) -> str:
        """Reconstructs the address string, preserving leading zeros."""
        if self.is_no_device:
            return "--:------"

        # Safe fallback for Mypy type-checking if only one part is None
        d_type = self.device_type if self.device_type is not None else 0
        d_id = self.device_id if self.device_id is not None else 0

        return f"{d_type:02d}:{d_id:06d}"

    @classmethod
    def from_string(cls, addr_str: str) -> DeviceAddress | None:
        """Parse a standard address string into a DeviceAddress object."""
        if not addr_str or addr_str == "--:------":
            return cls(None, None)
        try:
            parts = addr_str.split(":")
            return cls(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            return None


@dataclass
class PacketDTO:
    """The optimized DTO for RAMSES-RF packets.

    :param dtm: Timezone-aware timestamp of the packet capture.
    :type dtm: dt
    :param rssi: Signal strength indicator, or None if '---'.
    :type rssi: int | None
    :param verb: The strongly-typed packet verb.
    :type verb: VerbT
    :param seqn: The sequence number as a string, or None if '---'.
    :type seqn: str | None
    :param addr1: Address 1 (Usually Source), split into type and ID.
    :type addr1: DeviceAddress | None
    :param addr2: Address 2, split into type and ID.
    :type addr2: DeviceAddress | None
    :param addr3: Address 3 (Usually Dest), split into type and ID.
    :type addr3: DeviceAddress | None
    :param code: The hex command code as a string (e.g., "30C9").
    :type code: str
    :param payload_length: The integer byte length of the payload.
    :type payload_length: int | None
    :param raw_payload: The raw hexadecimal payload string.
    :type raw_payload: str
    :param parsed_payload: The dictionary/list parsed by the library.
    :type parsed_payload: dict[str, Any] | list[Any] | None
    :param is_multipart: True if this packet is part of a larger array.
    :type is_multipart: bool
    :param frame: The full raw packet string for exact reconstruction.
    :type frame: str
    """

    dtm: dt
    rssi: int | None
    verb: VerbT
    seqn: str | None
    addr1: DeviceAddress | None
    addr2: DeviceAddress | None
    addr3: DeviceAddress | None
    code: str
    payload_length: int | None
    raw_payload: str
    parsed_payload: dict[str, Any] | list[Any] | None
    is_multipart: bool
    frame: str

    @property
    def generated_comment(self) -> str:
        """Dynamically regenerates the standard log comment to save memory.

        :return: A formatted comment string (e.g., "1060| I|01:145038").
        :rtype: str
        """
        addr_str = str(self.addr1) if self.addr1 else ""
        return f"{self.code}|{self.verb.value}|{addr_str}"


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
            if getattr(self, "_frame", "") or self.error_text:
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

    def to_dto(
        self, parsed_payload: dict[str, Any] | list[Any] | None = None
    ) -> PacketDTO:
        """Serialize the packet to a structured DTO object."""
        try:
            verb_val = VerbT(self.verb)
        except ValueError:
            verb_val = VerbT.I_

        dtm = self.dtm
        if dtm.tzinfo is None:
            dtm = dtm.astimezone()

        rssi_str = self.rssi.strip()
        rssi = int(rssi_str) if rssi_str and rssi_str != "..." else None

        frame = getattr(self, "_frame", "")
        parts = frame.split()

        code = getattr(self, "code", "")
        seqn = getattr(self, "_seqn", None)
        raw_payload = ""
        payload_length = getattr(self, "_len", None)

        addr1 = addr2 = addr3 = None

        if len(parts) >= 7:
            code = parts[-3]
            with contextlib.suppress(ValueError):
                payload_length = int(parts[-2], 16)
            raw_payload = parts[-1]

            # The addresses are reliably positioned relative to the end of the frame
            addr3 = DeviceAddress.from_string(parts[-4])
            addr2 = DeviceAddress.from_string(parts[-5])
            addr1 = DeviceAddress.from_string(parts[-6])

            if len(parts) >= 8 and parts[1] != "---":
                seqn = parts[1]

        return PacketDTO(
            dtm=dtm,
            rssi=rssi,
            verb=verb_val,
            seqn=seqn,
            addr1=addr1,
            addr2=addr2,
            addr3=addr3,
            code=code,
            payload_length=payload_length,
            raw_payload=raw_payload,
            parsed_payload=parsed_payload,
            is_multipart=getattr(self, "_has_array", False),
            frame=frame,
        )

    def to_dict(
        self, parsed_payload: dict[str, Any] | list[Any] | None = None
    ) -> dict[str, Any]:
        """Serialize the packet to a structured dictionary."""
        dto = self.to_dto(parsed_payload=parsed_payload)
        data = asdict(dto)
        data["dtm"] = data["dtm"].isoformat(timespec="microseconds")
        data["verb"] = dto.verb.value
        return data

    @classmethod
    def from_dict(cls, dtm: str, state: dict[str, Any] | str) -> Packet:
        """Create a packet from a saved state (a curated dict)."""
        if isinstance(state, str):
            frame_str, _, comment_str = cls._partition(state)
            return cls(dt.fromisoformat(dtm), frame_str, comment=comment_str)

        # Safely extract RSSI, fallback to "...", and guarantee exactly 3 chars
        rssi_val = state.get("rssi")
        rssi = f"{int(rssi_val):03d}" if rssi_val is not None else "..."

        frame = f"{rssi[:3].ljust(3)} {state.get('frame', '')}"
        return cls(
            dt.fromisoformat(dtm),
            frame,
        )

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
        if int(pkt.payload[4:6], 16) in SCHEMA_DATA_IDS:
            return _TD_MINS_360 * 2.1
        if int(pkt.payload[4:6], 16) in PARAMS_DATA_IDS:
            return _TD_MINS_060 * 2.1
        if int(pkt.payload[4:6], 16) in STATUS_DATA_IDS:
            return _TD_MINS_005 * 2.1
        return _TD_MINS_005 * 2.1

    if (code := CODES_SCHEMA.get(pkt.code)) and SZ_LIFESPAN in code:
        result: bool | td | None = CODES_SCHEMA[pkt.code][SZ_LIFESPAN]
        if isinstance(result, td):
            return result

    return _TD_MINS_060  # applies to lots of HVAC packets
