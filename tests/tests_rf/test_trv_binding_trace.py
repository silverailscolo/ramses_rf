#!/usr/bin/env python3
"""RAMSES RF - Isolated tracing test for TRV Implicit Binding."""

import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from ramses_rf.config import GatewayConfig
from ramses_rf.gateway import Gateway

_LOGGER = logging.getLogger(__name__)

# A micro-log containing only the two TRVs in question.
MINI_PACKET_LOG = """
2021-11-11T11:11:01.001111 ...  I --- 04:111111 --:------ 01:123456 1060 003 01FF01
2021-11-11T11:11:02.002222 ...  I --- 04:222222 --:------ 01:123456 12B0 003 020000
"""


@pytest.mark.asyncio
async def test_trace_trv_implicit_binding(tmp_path: Path) -> None:
    """Trace the execution path of TRV telemetry to diagnose orphan bugs."""

    # Arrange
    log_file = tmp_path / "packet.log"
    log_file.write_text(MINI_PACKET_LOG.strip())

    config = GatewayConfig(enable_eavesdrop=True)
    config.disable_discovery = True
    config.engine.input_file = str(log_file)

    gwy = Gateway(config=config)

    with (
        patch(
            "ramses_rf.systems.tcs.MultiZone._handle_msg",
            wraps=gwy.tcs._handle_msg if getattr(gwy, "tcs", None) else None,  # type: ignore[union-attr]
        ) as mock_mz_handle,
        patch("ramses_rf.systems.zones.Zone._handle_msg") as mock_z_handle,
        patch(
            "ramses_rf.device.registry.DeviceRegistry.get_device",
            wraps=gwy.device_registry.get_device,
        ) as mock_get_device,
    ):
        # Act
        await gwy.start(start_discovery=False)

        try:
            actual_schema = await gwy.schema()

            # Use _LOGGER.debug instead of print
            _LOGGER.debug("--- EXECUTION TRACE ---")
            _LOGGER.debug(
                "1. MultiZone._handle_msg called %s times.", mock_mz_handle.call_count
            )
            _LOGGER.debug(
                "2. Zone._handle_msg called %s times.", mock_z_handle.call_count
            )
            _LOGGER.debug(
                "3. DeviceRegistry.get_device called %s times.",
                mock_get_device.call_count,
            )

            for call in mock_get_device.call_args_list:
                args, kwargs = call
                _LOGGER.debug(" -> get_device(%s, kwargs=%s)", args[0], kwargs)

            _LOGGER.debug("--- FINAL SCHEMA ---")
            _LOGGER.debug("\n%s", json.dumps(actual_schema, indent=4))

            # Assert
            assert "04:111111" not in actual_schema.get("orphans_heat", [])
            assert "04:222222" not in actual_schema.get("orphans_heat", [])

        finally:
            await gwy.stop()
