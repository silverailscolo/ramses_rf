"""RAMSES RF - Asynchronous CQRS State Ingestion Engine.

Consumes messages from the central dispatcher queues and translates decoded
telemetry payloads into frozen, observable StateUpdatedEvents.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
import uuid
from typing import Any, Final

from ramses_rf.const import (
    SZ_AIR_QUALITY,
    SZ_AIR_QUALITY_BASIS,
    SZ_BYPASS_MODE,
    SZ_BYPASS_POSITION,
    SZ_BYPASS_STATE,
    SZ_CH_ACTIVE,
    SZ_CH_ENABLED,
    SZ_CO2_LEVEL,
    SZ_DHW_ACTIVE,
    SZ_EXHAUST_FAN_SPEED,
    SZ_EXHAUST_FLOW,
    SZ_EXHAUST_TEMP,
    SZ_FAN_INFO,
    SZ_FAN_MODE,
    SZ_FAN_RATE,
    SZ_FLAME_ACTIVE,
    SZ_INDOOR_HUMIDITY,
    SZ_INDOOR_TEMP,
    SZ_OUTDOOR_HUMIDITY,
    SZ_OUTDOOR_TEMP,
    SZ_POST_HEAT,
    SZ_PRE_HEAT,
    SZ_PRESENCE_DETECTED,
    SZ_REMAINING_MINS,
    SZ_REQ_REASON,
    SZ_SPEED_CAPABILITIES,
    SZ_SUPPLY_FAN_SPEED,
    SZ_SUPPLY_FLOW,
    SZ_SUPPLY_TEMP,
    SZ_TEMPERATURE,
    Code,
)
from ramses_rf.messages import Message
from ramses_rf.models import StateUpdatedEvent
from ramses_rf.protocol.opentherm import OtDataId

# --- Translation Maps (Static Constant Blocks) ---

RAMSES_HEATING_MAP: Final[dict[Code, tuple[str, str]]] = {
    Code._3200: (SZ_TEMPERATURE, "boiler_output_temp"),
    Code._3210: (SZ_TEMPERATURE, "boiler_return_temp"),
    Code._22D9: ("setpoint", "boiler_setpoint"),
    Code._1081: ("setpoint", "ch_max_setpoint"),
    Code._1300: ("pressure", "ch_water_pressure"),
    Code._12F0: ("dhw_flow_rate", "dhw_flow_rate"),
    Code._10A0: ("setpoint", "dhw_setpoint"),
    Code._1260: ("temperature", "dhw_temp"),
    Code._1290: ("temperature", "outside_temp"),
}

OPENTHERM_FIELD_MAP: Final[dict[OtDataId, str]] = {
    OtDataId.BOILER_OUTPUT_TEMP: "boiler_output_temp",
    OtDataId.BOILER_RETURN_TEMP: "boiler_return_temp",
    OtDataId.CONTROL_SETPOINT: "boiler_setpoint",
    OtDataId.CH_MAX_SETPOINT: "ch_max_setpoint",
    OtDataId.CH_WATER_PRESSURE: "ch_water_pressure",
    OtDataId.DHW_FLOW_RATE: "dhw_flow_rate",
    OtDataId.DHW_SETPOINT: "dhw_setpoint",
    OtDataId.DHW_TEMP: "dhw_temp",
    OtDataId.OEM_CODE: "oem_code",
    OtDataId.OUTSIDE_TEMP: "outside_temp",
    OtDataId.REL_MODULATION_LEVEL: "rel_modulation_level",
    OtDataId._0E: "max_rel_modulation",
    OtDataId.BURNER_HOURS: "burner_hours",
    OtDataId.BURNER_STARTS: "burner_starts",
    OtDataId.BURNER_FAILED_STARTS: "burner_failed_starts",
    OtDataId.CH_PUMP_HOURS: "ch_pump_hours",
    OtDataId.CH_PUMP_STARTS: "ch_pump_starts",
    OtDataId.DHW_BURNER_HOURS: "dhw_burner_hours",
    OtDataId.DHW_BURNER_STARTS: "dhw_burner_starts",
    OtDataId.DHW_PUMP_HOURS: "dhw_pump_hours",
    OtDataId.DHW_PUMP_STARTS: "dhw_pump_starts",
    OtDataId.FLAME_LOW_SIGNALS: "flame_signal_low",
}

_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


class StateProjector:
    """Projector task that transforms incoming telemetry into immutable states."""

    def __init__(self, gwy: Any, ssot_queue: asyncio.Queue[Message]) -> None:
        """Initialize the state projector background worker.

        :param gwy: The active Gateway facade instance.
        :type gwy: Any
        :param ssot_queue: Single Source of Truth Queue from CentralDispatcher.
        :type ssot_queue: asyncio.Queue[Message]
        """
        self._gwy = gwy
        self._queue = ssot_queue
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the background consumer projector loop.

        :return: None
        :rtype: None
        """
        if self._task is None:
            self._task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        """Stop the background consumer projector loop cleanly.

        :return: None
        :rtype: None
        """
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _worker_loop(self) -> None:
        """Continuously pop messages from the queue for state processing.

        :return: None
        :rtype: None
        """
        while True:
            msg = await self._queue.get()
            try:
                self.process_message_state(msg)
            except Exception as err:
                _LOGGER.error("Failed to ingest state payload: %s", err)
            finally:
                self._queue.task_done()

    def process_message_state(self, msg: Message) -> None:
        """Route valid inbound message envelopes to their respective engines.

        :param msg: The message envelope containing raw telemetry.
        :type msg: Message
        :return: None
        :rtype: None
        """
        if getattr(msg, "verb", "") == "RQ" or not isinstance(
            msg.payload, (dict, list)
        ):
            return

        payloads = msg.payload if isinstance(msg.payload, list) else [msg.payload]

        registry = getattr(self._gwy, "device_registry", None)
        if not registry:
            return

        for p in payloads:
            if not isinstance(p, dict):
                continue

            # Hexagonal Boundary Enforcement: Route telemetry to the Source device
            src_dev = registry.device_by_id.get(msg.src.id)
            if src_dev:
                try:
                    self._update_opentherm_state(src_dev, p, msg)
                    self._update_hvac_state(src_dev, p, msg)
                except Exception as err:
                    _LOGGER.error(
                        "CQRS state extraction failed for src %s: %s", src_dev.id, err
                    )

            # Route to Destination Device (Aggregation)
            # Controller entities (like Fans and Boilers) must inherit the state
            # of the sensors transmitting directly to them to mimic legacy behavior.
            if msg.dst.id != "--:------" and msg.dst.id != msg.src.id:
                dst_dev = registry.device_by_id.get(msg.dst.id)
                if dst_dev:
                    try:
                        self._update_opentherm_state(dst_dev, p, msg)
                        self._update_hvac_state(dst_dev, p, msg)
                    except Exception as err:
                        _LOGGER.error(
                            "CQRS state extraction failed for dst %s: %s",
                            dst_dev.id,
                            err,
                        )

    def _update_opentherm_state(
        self, target: Any, p: dict[str, Any], msg: Message
    ) -> None:
        """Translate OpenTherm frames or parallel heating opcodes into OpenThermState.

        :param target: The target software twin entity to update.
        :type target: Any
        :param p: The parsed message payload dictionary.
        :type p: dict[str, Any]
        :param msg: The communication message envelope.
        :type msg: Message
        :return: None
        :rtype: None
        """
        if not hasattr(target, "opentherm_state"):
            return

        updates: dict[str, Any] = {}

        if msg.code == Code._3220:
            raw_id = p.get("msg_id")
            val = p.get("value")

            if raw_id is None:
                return

            try:
                msg_id = OtDataId(raw_id)
            except ValueError:
                return

            if (
                msg_id == OtDataId.STATUS
                and isinstance(val, (list, tuple))
                and len(val) >= 13
            ):
                updates.update(
                    {
                        "ch_enabled": bool(val[0]),
                        "dhw_enabled": bool(val[1]),
                        "cooling_enabled": bool(val[2]),
                        "otc_active": bool(val[3]),
                        "summer_mode": bool(val[5]),
                        "dhw_blocking": bool(val[6]),
                        "fault_present": bool(val[8]),
                        "ch_active": bool(val[9]),
                        "dhw_active": bool(val[10]),
                        "flame_active": bool(val[11]),
                        "cooling_active": bool(val[12]),
                    }
                )
            elif val is not None and msg_id in OPENTHERM_FIELD_MAP:
                updates[OPENTHERM_FIELD_MAP[msg_id]] = val
        else:
            if msg.code in RAMSES_HEATING_MAP:
                payload_key, state_field = RAMSES_HEATING_MAP[msg.code]
                if payload_key in p:
                    updates[state_field] = p[payload_key]
            elif msg.code in (Code._3EF0, Code._3EF1):
                for field_key in (
                    "rel_modulation_level",
                    "max_rel_modulation",
                    "ch_setpoint",
                    SZ_CH_ACTIVE,
                    SZ_CH_ENABLED,
                    SZ_DHW_ACTIVE,
                ):
                    if field_key in p:
                        updates[field_key] = p[field_key]
                if "flame_on" in p:
                    updates[SZ_FLAME_ACTIVE] = p["flame_on"]

        if not updates:
            return

        new_state = dataclasses.replace(target.opentherm_state, **updates)
        event = StateUpdatedEvent(
            entity_id=getattr(target, "id", "unknown"),
            state=new_state,
            correlation_id=getattr(msg, "correlation_id", uuid.uuid4()),
            causation_id=getattr(msg, "message_id", uuid.uuid4()),
        )
        target.apply_state_update(event)

    def _update_hvac_state(self, target: Any, p: dict[str, Any], msg: Message) -> None:
        """Translate complex multi-opcode ventilation payloads into HvacState.

        :param target: The target software twin entity to update.
        :type target: Any
        :param p: The parsed message payload dictionary.
        :type p: dict[str, Any]
        :param msg: The communication message envelope.
        :type msg: Message
        :return: None
        :rtype: None
        """
        if not hasattr(target, "hvac_state"):
            return

        updates: dict[str, Any] = {}

        fields = [
            SZ_CO2_LEVEL,
            SZ_AIR_QUALITY,
            SZ_AIR_QUALITY_BASIS,
            SZ_BYPASS_MODE,
            SZ_BYPASS_POSITION,
            SZ_BYPASS_STATE,
            SZ_EXHAUST_FAN_SPEED,
            SZ_EXHAUST_FLOW,
            SZ_EXHAUST_TEMP,
            SZ_FAN_RATE,
            SZ_FAN_MODE,
            SZ_FAN_INFO,
            SZ_INDOOR_HUMIDITY,
            SZ_INDOOR_TEMP,
            SZ_OUTDOOR_HUMIDITY,
            SZ_OUTDOOR_TEMP,
            SZ_POST_HEAT,
            SZ_PRE_HEAT,
            SZ_PRESENCE_DETECTED,
            SZ_REMAINING_MINS,
            SZ_SPEED_CAPABILITIES,
            SZ_SUPPLY_FAN_SPEED,
            SZ_SUPPLY_FLOW,
            SZ_SUPPLY_TEMP,
            SZ_TEMPERATURE,
            "dewpoint_temp",
        ]

        for f in fields:
            if f in p:
                updates[f] = p[f]

        if "remaining_days" in p:
            updates["filter_remaining_days"] = p["remaining_days"]
        if "remaining_percent" in p:
            updates["filter_remaining_percent"] = p["remaining_percent"]
        if "minutes" in p and msg.code == Code._22F3:
            updates["boost_timer_mins"] = p["minutes"]
        if "req_speed" in p:
            updates["request_fan_speed"] = p["req_speed"]
        if "req_reason" in p:
            updates[SZ_REQ_REASON] = p["req_reason"]

        if not updates:
            return

        new_state = dataclasses.replace(target.hvac_state, **updates)
        event = StateUpdatedEvent(
            entity_id=getattr(target, "id", "unknown"),
            state=new_state,
            correlation_id=getattr(msg, "correlation_id", uuid.uuid4()),
            causation_id=getattr(msg, "message_id", uuid.uuid4()),
        )
        target.apply_state_update(event)
