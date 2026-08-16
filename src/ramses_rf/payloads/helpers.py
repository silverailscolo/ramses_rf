"""RAMSES RF - Payload Dataclass Helpers.

This module provides helper utilities and shared serialization converters
used by payload dataclasses and system entities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ramses_rf.const import (
    SZ_DEVICE_CLASS,
    SZ_DEVICE_ID,
    SZ_DOMAIN_INDEX,
    SZ_FAULT_STATE,
    SZ_FAULT_TYPE,
    SZ_LOG_INDEX,
    SZ_TIMESTAMP,
)
from ramses_tx.address import hex_id_to_dev_id
from ramses_tx.const import (
    FAULT_DEVICE_CLASS,
    FAULT_STATE,
    FAULT_TYPE,
    FaultDeviceClass,
    FaultState,
    FaultType,
)
from ramses_tx.helpers import hex_to_dts

if TYPE_CHECKING:
    from ramses_tx.typing import PayDictT


def parse_fault_log_entry(
    payload: str,
) -> PayDictT.FAULT_LOG_ENTRY | PayDictT.FAULT_LOG_ENTRY_NULL:
    """Return the fault log entry dictionary from a raw hex string payload.

    :param payload: The 44-character raw hex string payload.
    :type payload: str
    :return: A typed dictionary representing the fault log entry or null entry.
    :rtype: PayDictT.FAULT_LOG_ENTRY | PayDictT.FAULT_LOG_ENTRY_NULL
    """
    assert len(payload) == 44

    # NOTE: the log_index will increment as the entry moves down the log, hence '_log_index'
    log_index_str: str = payload[4:6]

    # these are only useful for I_, not RP
    if (timestamp := hex_to_dts(payload[18:30])) is None:
        return {f"_{SZ_LOG_INDEX}": log_index_str}  # type: ignore[return-value]

    result: PayDictT.FAULT_LOG_ENTRY = {
        f"_{SZ_LOG_INDEX}": log_index_str,  # type: ignore[misc]
        SZ_TIMESTAMP: timestamp,
        SZ_FAULT_STATE: FAULT_STATE.get(payload[2:4], FaultState.UNKNOWN),
        SZ_FAULT_TYPE: FAULT_TYPE.get(payload[8:10], FaultType.UNKNOWN),
        SZ_DOMAIN_INDEX: payload[10:12],
        SZ_DEVICE_CLASS: FAULT_DEVICE_CLASS.get(
            payload[12:14], FaultDeviceClass.UNKNOWN
        ),
        SZ_DEVICE_ID: hex_id_to_dev_id(payload[38:]),
        "_unknown_3": payload[6:8],  # B0 ?priority
        "_unknown_7": payload[14:18],  # 0000
        "_unknown_15": payload[30:38],  # FFFF7000/1/2
    }

    return result
