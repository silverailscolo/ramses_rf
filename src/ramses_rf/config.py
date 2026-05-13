#!/usr/bin/env python3
"""RAMSES RF - Gateway Configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from ramses_tx.config import EngineConfig


@dataclass
class GatewayConfig:
    """Configuration parameters for the Ramses Gateway.

    :param disable_discovery: Disable device discovery, defaults to False.
    :type disable_discovery: bool
    :param enable_eavesdrop: Enable eavesdropping mode, defaults to False.
    :type enable_eavesdrop: bool
    :param reduce_processing: Level of reduced processing, defaults to 0.
    :type reduce_processing: int
    :param max_zones: Maximum number of zones allowed, defaults to 12.
    :type max_zones: int
    :param use_aliases: Mapping of aliases for device IDs.
    :type use_aliases: dict[str, str]
    :param enforce_strict_handling: Enforce strict handling of packets.
    :type enforce_strict_handling: bool
    :param use_native_ot: Preference for using native OpenTherm.
    :type use_native_ot: Literal["always", "prefer", "avoid", "never"] | None
    :param schema: Dictionary representing the schema.
    :type schema: dict[str, Any]
    :param debug_mode: If True, set the logger to debug mode.
    :type debug_mode: bool
    :param gateway_timeout: Custom timeout threshold in minutes.
    :type gateway_timeout: int | None
    :param database_path: Target disk path for the SQLite DB.
    :type database_path: str | None
    :param engine: Typed configuration object for the Transport layer.
    :type engine: EngineConfig
    """

    disable_discovery: bool = False
    enable_eavesdrop: bool = False
    reduce_processing: int = 0
    max_zones: int = 12
    use_aliases: dict[str, str] = field(default_factory=dict)
    enforce_strict_handling: bool = False
    use_native_ot: Literal["always", "prefer", "avoid", "never"] | None = None

    schema: dict[str, Any] = field(default_factory=dict)
    debug_mode: bool = False
    gateway_timeout: int | None = None
    database_path: str | None = "ramses.db"

    # Transport layer configuration encapsulated perfectly
    engine: EngineConfig = field(default_factory=EngineConfig)
