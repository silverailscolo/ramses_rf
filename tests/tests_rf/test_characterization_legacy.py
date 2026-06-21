"""RAMSES RF - Legacy System Characterization Trace."""

import asyncio
import json
import logging
from pathlib import Path

import pytest

from ramses_rf.config import GatewayConfig
from ramses_rf.gateway import Gateway
from ramses_tx.const import SZ_READER_TASK

_LOGGER = logging.getLogger(__name__)

# --- MICRO-LOGS FOR CONTROLLED EXPERIMENTS ---
# Note: Added '000' dummy RSSI/sequence values after timestamps for parser compliance

HVAC_LOG = """
# A generic device sends a Fan speed packet (31D9)
2021-11-11T11:11:01.000 000 I --- 32:111111 --:------ 32:111111 31D9 003 000000
"""

TRV_CORRELATION_LOG = """
# 1. Controller announces it exists and has Zone 00
2021-11-11T11:11:01.000 000 I --- 01:123456 --:------ 01:123456 0005 004 00080000
# 2. Orphan TRV broadcasts its current temperature (20.0C)
2021-11-11T11:11:02.000 000 I --- 04:111111 --:------ 01:123456 30C9 003 0007D0
# 3. Controller syncs temperatures, confirming Zone 00 is 20.0C
2021-11-11T11:11:03.000 000 I --- 01:123456 --:------ 01:123456 30C9 003 0007D0
"""


async def run_and_trace(log_content: str, tmp_path: Path, test_name: str) -> dict:
    """Run the gateway and dump the final schema and known_list."""
    log_file = tmp_path / f"packet_{test_name}.log"
    log_file.write_text(log_content.strip())

    config = GatewayConfig(enable_eavesdrop=True)
    config.disable_discovery = True
    config.engine.input_file = str(log_file)

    gwy = Gateway(config=config)

    # Disable the new CQRS Dispatcher temporarily so we ONLY see legacy behavior
    if hasattr(gwy, "dispatcher"):
        gwy.dispatcher = None

    await gwy.start(start_discovery=False)

    try:
        # Wait for the legacy transport reader to finish
        if gwy._engine._transport:
            reader_task = gwy._engine._transport.get_extra_info(SZ_READER_TASK)
            if reader_task:
                await reader_task

        # Give legacy async tasks (like _eavesdrop_zone_sensors) time to fire
        await asyncio.sleep(0.1)

        _LOGGER.debug(f"\n{'=' * 50}\n--- {test_name.upper()} RESULTS ---")

        schema = await gwy.schema()
        _LOGGER.debug("\n--- FINAL LEGACY SCHEMA ---")
        _LOGGER.debug(json.dumps(schema, indent=2))

        known_list = await gwy.device_registry.known_list()
        _LOGGER.debug("\n--- FINAL LEGACY KNOWN_LIST (TRAITS) ---")
        _LOGGER.debug(json.dumps(known_list, indent=2))

        return schema

    finally:
        await gwy.stop()


@pytest.mark.asyncio
async def test_characterize_legacy_hvac(tmp_path: Path) -> None:
    """Trace exactly how legacy promotes an HVAC device."""
    await run_and_trace(HVAC_LOG, tmp_path, "hvac_promotion")


@pytest.mark.asyncio
async def test_characterize_legacy_trv(tmp_path: Path) -> None:
    """Run the TRV correlation log and observe final schema placement."""
    await run_and_trace(TRV_CORRELATION_LOG, tmp_path, "trv_correlation")
