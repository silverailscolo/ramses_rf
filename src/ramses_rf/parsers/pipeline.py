"""RAMSES RF - Payload decoding pipeline.

This module provides the Chain of Responsibility pipeline for decoding
RAMSES RF payloads.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from ramses_rf.protocol.ramses import RQ_IDX_COMPLEX
from ramses_tx import exceptions as exc
from ramses_tx.const import I_, RP, RQ, W_, Code
from ramses_tx.helpers import hex_to_temp

from .registry import get_parser

if TYPE_CHECKING:
    from ramses_rf.messages import Message

_LOGGER = logging.getLogger(__name__)
_INFORM_DEV_MSG = "Support the development of ramses_rf by reporting this packet"


def parser_heartbeat(payload: str, msg: Message) -> dict[str, Any]:
    """Parse a 1-byte heartbeat packet (payload '00').

    :param payload: The raw hex payload (expected '00').
    :type payload: str
    :param msg: The message object containing context.
    :type msg: Message
    :return: A dictionary identifying the packet as a heartbeat.
    :rtype: dict[str, Any]
    """
    return {"heartbeat": True}


def parser_unknown(payload: str, msg: Message) -> dict[str, Any]:
    """Apply a generic parser for unrecognized packet codes.

    :param payload: The raw hex payload
    :type payload: str
    :param msg: The message object containing context
    :type msg: Message
    :return: A dictionary containing the raw payload and code information
    :rtype: dict[str, Any]
    """
    # TODO: it may be useful to generically search payloads for hex_ids

    # These are generic parsers
    if msg.len == 2 and payload[:2] == "00":
        return {
            "_payload": payload,
            "_value": {"00": False, "C8": True}.get(payload[2:], int(payload[2:], 16)),
        }

    if msg.len == 3 and payload[:2] == "00":
        return {
            "_payload": payload,
            "_value": hex_to_temp(payload[2:]),
        }

    return {
        "_payload": payload,
        "_unknown_code": msg.code,
        "_parse_error": "No parser available for this packet type",
    }


class PayloadDecoder(ABC):
    """Abstract base class for the payload decoder chain."""

    def __init__(self) -> None:
        """Initialize the base decoder state."""
        self._next_decoder: PayloadDecoder | None = None

    def set_next(self, decoder: PayloadDecoder) -> PayloadDecoder:
        """Set the next decoder in the chain.

        :param decoder: The next decoder
        :type decoder: PayloadDecoder
        :return: The next decoder
        :rtype: PayloadDecoder
        """
        self._next_decoder = decoder
        return decoder

    @abstractmethod
    def decode(
        self, msg: Message, payload_str: str, payload_len: int
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        """Decode the payload. Returns None to bypass index merging.

        :param msg: The message context
        :type msg: Message
        :param payload_str: The raw payload string
        :type payload_str: str
        :param payload_len: The payload length
        :type payload_len: int
        :return: The decoded result or None to trigger early bypass
        :rtype: dict[str, Any] | list[dict[str, Any]] | None
        """
        if self._next_decoder:
            return self._next_decoder.decode(msg, payload_str, payload_len)
        return {}


class HeartbeatDecoder(PayloadDecoder):
    """Decoder that intercepts 1-byte '00' heartbeats."""

    def decode(
        self, msg: Message, payload_str: str, payload_len: int
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        """Intercept and decode heartbeat payloads.

        :param msg: The message context
        :type msg: Message
        :param payload_str: The raw payload string
        :type payload_str: str
        :param payload_len: The payload length
        :type payload_len: int
        :return: The decoded result
        :rtype: dict[str, Any] | list[dict[str, Any]] | None
        """
        if not msg._has_payload and (msg.verb == RQ and msg.code not in RQ_IDX_COMPLEX):
            return None

        if payload_len == 1 and payload_str == "00" and msg.code != Code._1FC9:
            try:
                parser = get_parser(msg.code) or parser_unknown
                result = parser(payload_str, msg)
                if result == {}:
                    return None
            except (
                exc.ParserBaseError,
                IndexError,
                KeyError,
                TypeError,
                ValueError,
            ) as err:
                _LOGGER.debug(
                    "Parser for code %s failed, falling back to heartbeat: %s",
                    msg.code,
                    err,
                )
            return parser_heartbeat(payload_str, msg)

        if self._next_decoder:
            return self._next_decoder.decode(msg, payload_str, payload_len)
        return {}


class StandardParserDecoder(PayloadDecoder):
    """Decoder routing payload to the appropriate 4-digit code parser."""

    def decode(
        self, msg: Message, payload_str: str, payload_len: int
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        """Route payload to the relevant parser function.

        :param msg: The message context
        :type msg: Message
        :param payload_str: The raw payload string
        :type payload_str: str
        :param payload_len: The payload length
        :type payload_len: int
        :return: The decoded result
        :rtype: dict[str, Any] | list[dict[str, Any]] | None
        """
        try:
            parser = get_parser(msg.code) or parser_unknown
            result = parser(payload_str, msg)
            if isinstance(result, dict) and msg.seqn and msg.seqn.isnumeric():
                result["seqx_num"] = msg.seqn
            # Narrowing to strictly list or dict
            if isinstance(result, list):
                return result
            if isinstance(result, dict):
                return result
            return {}
        except AssertionError as err:
            _LOGGER.warning(
                f"{msg!r} < {_INFORM_DEV_MSG} ({err}). "
                f"This packet could not be parsed completely."
            )
            err_result = {
                "_payload": payload_str,
                "_parse_error": f"AssertionError: {err}",
                "_unknown_code": msg.code,
            }
            if msg.seqn and msg.seqn.isnumeric():
                err_result["seqx_num"] = msg.seqn
            return err_result


class PayloadDecoderPipeline:
    """The Chain of Responsibility pipeline for decoding RAMSES payloads."""

    def __init__(self) -> None:
        """Initialize the decoder pipeline."""
        self.head = HeartbeatDecoder()
        self.head.set_next(StandardParserDecoder())

    def decode_payload(self, msg: Message) -> Any:
        """Decode the raw payload using the decoder chain.

        :param msg: A Message object containing packet data
        :type msg: Message
        :return: A dict of key:value pairs or a list of such dicts
        :rtype: dict[str, Any] | list[dict[str, Any]] | None
        """
        payload_str: str = msg._dto.raw_payload
        payload_len: int = msg.len

        return self.head.decode(msg, payload_str, payload_len)


def re_compile_re_match(regex: str, string: str) -> bool:
    """Check if the provided string matches the regex pattern.

    :param regex: The regex pattern string
    :type regex: str
    :param string: The text payload to test
    :type string: str
    :return: True if matched, False otherwise
    :rtype: bool
    """
    return bool(re.compile(regex).match(string))


def _check_msg_payload(msg: Message, payload: str) -> None:
    """Validate a packet's payload against its verb/code pair.

    :param msg: The message object being validated
    :type msg: Message
    :param payload: The raw hex payload string
    :type payload: str
    :raises PacketInvalid: If the code or verb/code pair is unknown.
    :raises PacketPayloadInvalid: If payload doesn't match expected regex.
    """
    try:
        # Force packet evaluation via string representation
        _ = repr(msg)
    except Exception as err:
        raise exc.PacketPayloadInvalid(
            f"Packet formatting/evaluation failed: {err}"
        ) from err

    if msg.verb not in (RQ, RP, I_, W_):
        raise exc.PacketInvalid(f"Unknown verb/code pair: {msg.verb}/{msg.code}")
