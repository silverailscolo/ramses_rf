"""RAMSES RF - Payload Parsers Package.

This package provides strictly-typed, domain-specific parsers and a
robust decoding pipeline for RAMSES RF radio packets.
"""

from .pipeline import PayloadDecoderPipeline
from .registry import get_parser, register_parser

__all__ = [
    "PayloadDecoderPipeline",
    "get_parser",
    "register_parser",
]
